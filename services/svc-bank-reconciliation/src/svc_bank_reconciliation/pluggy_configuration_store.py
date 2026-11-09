"""Company-owned Pluggy credentials, encrypted with tenant-bound AES-256-GCM."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import Column, Integer, LargeBinary, String
from sqlalchemy.orm import Session
from supreme_common.auth_context import context

from .database import Base

if TYPE_CHECKING:
    from .pluggy_client import PluggySettings


class PluggyConfiguration(Base):
    __tablename__ = "pluggy_configurations"

    organization_id = Column(String(100), primary_key=True)
    company_id = Column(String(100), primary_key=True)
    encrypted_credentials = Column(LargeBinary, nullable=False)
    updated_at = Column(String(40), nullable=False)
    updated_by = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


def encryption_key() -> bytes:
    try:
        key = bytes.fromhex(os.getenv("MASTER_ENCRYPTION_KEY", ""))
        if len(key) == 32:
            return key
    except ValueError:
        pass
    raise HTTPException(503, "Configure MASTER_ENCRYPTION_KEY no servidor para armazenar credenciais.")


def storage_available() -> bool:
    try:
        encryption_key()
        return True
    except HTTPException:
        return False


def configuration(db: Session) -> PluggyConfiguration | None:
    claims = context()
    return db.get(PluggyConfiguration, (claims["organization_id"], claims["company_id"]))


def associated_data() -> bytes:
    claims = context()
    return json.dumps(["pluggy", claims["organization_id"], claims["company_id"]]).encode()


def encrypt_settings(settings: PluggySettings) -> bytes:
    payload = json.dumps(
        {
            "client_id": settings.client_id.get_secret_value(),
            "client_secret": settings.client_secret.get_secret_value(),
            "allow_sandbox": settings.allow_sandbox,
        }
    ).encode()
    nonce = os.urandom(12)
    return nonce + AESGCM(encryption_key()).encrypt(nonce, payload, associated_data())


def saved_settings(row: PluggyConfiguration) -> PluggySettings:
    from .pluggy_client import PluggySettings

    key = encryption_key()
    try:
        data = row.encrypted_credentials
        raw = AESGCM(key).decrypt(data[:12], data[12:], associated_data())
        settings = PluggySettings.model_validate_json(raw)
    except (InvalidTag, ValueError, ValidationError):
        raise HTTPException(
            503, "Não foi possível abrir as credenciais. Verifique a chave do servidor."
        ) from None
    return settings


def effective_settings(db: Session) -> PluggySettings:
    from .pluggy_client import PluggySettings

    row = configuration(db)
    settings = saved_settings(row) if row else PluggySettings.from_environment()
    if settings.allow_sandbox and os.getenv("SUPREME_ENV") == "production":
        raise HTTPException(503, "Sandbox Pluggy não é permitido em produção.")
    return settings
