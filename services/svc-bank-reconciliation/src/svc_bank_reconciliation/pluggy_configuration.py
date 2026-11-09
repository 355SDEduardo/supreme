"""Administrative configuration API. Never returns credentials or provider tokens."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import or_
from sqlalchemy.orm import Session
from supreme_common.auth_context import context, require_role

from .database import get_db
from .open_finance import commit, scoped
from .open_finance_models import OpenFinanceConnection
from .pluggy_client import PluggyClient, PluggySettings
from .pluggy_configuration_store import (
    PluggyConfiguration,
    configuration,
    effective_settings,
    encrypt_settings,
    encryption_key,
    saved_settings,
    storage_available,
)


class PrivateValidationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                # FastAPI's default validation response can echo a submitted secret.
                raise HTTPException(
                    422, "Configuração inválida. Confira as credenciais e recarregue a tela."
                ) from None

        return private_handler


def administrator() -> None:
    require_role("super_admin", "supervisor")


router = APIRouter(
    prefix="/bank-accounts/open-finance/configuration",
    tags=["Configuração Pluggy"],
    dependencies=[Depends(administrator)],
    route_class=PrivateValidationRoute,
)


class ConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: SecretStr | None = Field(default=None, min_length=1, max_length=512)
    client_secret: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    allow_sandbox: bool = False
    revision: int = Field(ge=0)


class ConfigurationStatus(BaseModel):
    configured: bool
    source: Literal["none", "environment", "company"]
    client_id_masked: str | None = None
    allow_sandbox: bool = False
    sandbox_allowed: bool
    storage_available: bool
    revision: int = 0
    updated_at: str | None = None
    configuration_error: str | None = None


def status(db: Session) -> ConfigurationStatus:
    row = configuration(db)
    settings = None
    source = "none"
    error = None
    if row:
        settings, source = saved_settings(row), "company"
    elif os.getenv("PLUGGY_CLIENT_ID") or os.getenv("PLUGGY_CLIENT_SECRET"):
        source = "environment"
        try:
            settings = PluggySettings.from_environment()
        except HTTPException as exc:
            error = str(exc.detail)
    if settings and settings.allow_sandbox and os.getenv("SUPREME_ENV") == "production":
        error = "Sandbox não é permitido em produção. Salve a configuração com sandbox desativado."
    identifier = settings.client_id.get_secret_value() if settings else ""
    return ConfigurationStatus(
        configured=settings is not None,
        source=source,
        client_id_masked=("••••" + identifier[-4:] if len(identifier) > 4 else "••••") if settings else None,
        allow_sandbox=settings.allow_sandbox if settings else False,
        sandbox_allowed=os.getenv("SUPREME_ENV") != "production",
        storage_available=storage_available(),
        revision=row.version if row else 0,
        updated_at=row.updated_at if row else None,
        configuration_error=error,
    )


def check_revision(row: PluggyConfiguration | None, revision: int) -> None:
    if revision != (row.version if row else 0):
        raise HTTPException(409, "Configuração alterada por outro usuário. Recarregue antes de continuar.")


def active_connections(db: Session) -> bool:
    return (
        scoped(db, OpenFinanceConnection)
        .filter(
            OpenFinanceConnection.disconnected_at.is_(None),
            or_(
                OpenFinanceConnection.item_id.is_not(None),
                OpenFinanceConnection.expires_at > datetime.now(timezone.utc).isoformat(),
            ),
        )
        .first()
        is not None
    )


@router.get("", response_model=ConfigurationStatus)
def read_configuration(db: Session = Depends(get_db)) -> ConfigurationStatus:
    return status(db)


@router.put("", response_model=ConfigurationStatus)
async def save_configuration(
    payload: ConfigurationInput, db: Session = Depends(get_db)
) -> ConfigurationStatus:
    encryption_key()
    if payload.allow_sandbox and os.getenv("SUPREME_ENV") == "production":
        raise HTTPException(422, "Sandbox Pluggy não é permitido em produção.")
    row = configuration(db)
    check_revision(row, payload.revision)
    previous = None
    if row:
        previous = saved_settings(row)
    elif os.getenv("PLUGGY_CLIENT_ID") and os.getenv("PLUGGY_CLIENT_SECRET"):
        # Keep the previous application identity even if its sandbox option became invalid.
        previous = PluggySettings(
            client_id=os.environ["PLUGGY_CLIENT_ID"], client_secret=os.environ["PLUGGY_CLIENT_SECRET"]
        )
    identifier = payload.client_id or (previous.client_id if previous else None)
    secret = payload.client_secret or (previous.client_secret if previous else None)
    if (
        not identifier
        or not secret
        or not identifier.get_secret_value().strip()
        or not secret.get_secret_value().strip()
    ):
        raise HTTPException(422, "Informe Client ID e Client Secret da aplicação Pluggy.")
    changing_app = not previous or identifier != previous.client_id
    if changing_app and previous and payload.client_secret is None:
        raise HTTPException(422, "Informe também o Client Secret ao trocar o Client ID.")
    if changing_app and active_connections(db):
        raise HTTPException(
            409, "Desconecte os bancos e aguarde as sessões pendentes antes de trocar a aplicação Pluggy."
        )
    settings = PluggySettings(client_id=identifier, client_secret=secret, allow_sandbox=payload.allow_sandbox)
    # Authentication must succeed before replacing the last working credentials.
    await PluggyClient(settings).authenticate()
    if not row:
        claims = context()
        row = PluggyConfiguration(organization_id=claims["organization_id"], company_id=claims["company_id"])
        db.add(row)
    row.encrypted_credentials = encrypt_settings(settings)
    row.updated_at = datetime.now(timezone.utc).isoformat()
    row.updated_by = context()["sub"]
    commit(db)
    return status(db)


@router.post("/test")
async def test_configuration(db: Session = Depends(get_db)) -> dict[str, str]:
    # A fresh client checks the stored secret, rather than a still-valid cached API key.
    await PluggyClient(effective_settings(db)).authenticate()
    return {
        "message": "Autenticação confirmada pela Pluggy.",
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("", response_model=ConfigurationStatus)
def remove_configuration(revision: int = Query(ge=0), db: Session = Depends(get_db)) -> ConfigurationStatus:
    row = configuration(db)
    check_revision(row, revision)
    if row:
        if active_connections(db):
            raise HTTPException(
                409, "Desconecte os bancos e aguarde as sessões pendentes antes de remover a configuração."
            )
        # Validate the fallback before committing a removal that would return an error.
        if os.getenv("PLUGGY_CLIENT_ID") or os.getenv("PLUGGY_CLIENT_SECRET"):
            PluggySettings.from_environment()
        db.delete(row)
        commit(db)
    return status(db)
