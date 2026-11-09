"""Bounded HTTP adapter for the documented Pluggy data APIs (no payment APIs)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import OrderedDict
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, ValidationError
from supreme_common.auth_context import context
from sqlalchemy.orm import Session

from .database import get_db

API_URL = "https://api.pluggy.ai"
PRODUCTS = ["ACCOUNTS", "TRANSACTIONS"]
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_TRANSACTIONS = 20_000


class PluggySettings(BaseModel):
    client_id: SecretStr
    client_secret: SecretStr
    allow_sandbox: bool = False

    @classmethod
    def from_environment(cls) -> PluggySettings:
        try:
            settings = cls(
                client_id=os.getenv("PLUGGY_CLIENT_ID", ""),
                client_secret=os.getenv("PLUGGY_CLIENT_SECRET", ""),
                allow_sandbox=os.getenv("PLUGGY_ALLOW_SANDBOX", "false"),
            )
        except ValidationError:
            raise HTTPException(503, "Configuração da Pluggy inválida.") from None
        if not all(v.get_secret_value().strip() for v in (settings.client_id, settings.client_secret)):
            raise HTTPException(503, "Configure PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET neste serviço.")
        if settings.allow_sandbox and os.getenv("SUPREME_ENV") == "production":
            raise HTTPException(503, "Sandbox Pluggy não é permitido em produção.")
        return settings


class TokenResponse(BaseModel):
    apiKey: str = Field(min_length=1, max_length=32768)


class NumberedPage(BaseModel):
    page: int = Field(ge=1)
    totalPages: int = Field(ge=0, le=20)
    results: list[dict]


def invalid_response() -> HTTPException:
    return HTTPException(502, "Resposta inválida ou incompleta da Pluggy.")


class PluggyClient:
    def __init__(self, settings: PluggySettings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self._api_key = ""
        self._expires_at = 0.0
        self._auth_lock = asyncio.Lock()

    async def _send(self, method: str, path: str, *, api_key: str = "", **kwargs: object) -> dict:
        headers = {"Accept": "application/json", "X-Correlation-ID": context()["correlation_id"]}
        if api_key:
            headers["X-API-KEY"] = api_key
        try:
            async with httpx.AsyncClient(
                base_url=API_URL,
                timeout=httpx.Timeout(20, connect=5),
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                async with client.stream(method, path, headers=headers, **kwargs) as response:
                    # Never return or log provider bodies, credentials, tokens or banking PII on errors.
                    status = response.status_code
                    if status == 401:
                        raise HTTPException(503, "Autenticação da Pluggy indisponível.")
                    if status == 403:
                        raise HTTPException(503, "Operação não habilitada na Pluggy.")
                    if status == 404:
                        raise HTTPException(404, "Recurso não encontrado na Pluggy.")
                    if status == 429:
                        retry = response.headers.get("Retry-After", "60")
                        retry = retry if retry.isascii() and retry.isdigit() and len(retry) <= 5 else "60"
                        raise HTTPException(
                            429, "Limite de consultas à Pluggy atingido.", headers={"Retry-After": retry}
                        )
                    if not 200 <= status < 300:
                        raise HTTPException(502, "A Pluggy não concluiu a operação.")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise invalid_response()
        except httpx.TimeoutException:
            raise HTTPException(504, "Tempo limite de comunicação com a Pluggy.") from None
        except httpx.HTTPError:
            raise HTTPException(502, "Falha de comunicação com a Pluggy.") from None
        try:
            data = json.loads(raw, parse_float=Decimal)
        except (ValueError, UnicodeError, RecursionError):
            raise invalid_response() from None
        if not isinstance(data, dict):
            raise invalid_response()
        return data

    async def _key(self) -> str:
        async with self._auth_lock:
            if time.monotonic() >= self._expires_at:
                data = await self._send(
                    "POST",
                    "/auth",
                    json={
                        "clientId": self.settings.client_id.get_secret_value(),
                        "clientSecret": self.settings.client_secret.get_secret_value(),
                    },
                )
                try:
                    self._api_key = TokenResponse.model_validate(data).apiKey
                except ValidationError:
                    raise invalid_response() from None
                self._expires_at = time.monotonic() + 7100  # Documented TTL: 2 h; refresh early.
            return self._api_key

    async def request(self, method: str, path: str, **kwargs: object) -> dict:
        key = await self._key()
        try:
            return await self._send(method, path, api_key=key, **kwargs)
        except HTTPException as exc:
            # A revoked/expired key is discarded. Only GET is safely retried once.
            if exc.status_code != 503 or exc.detail != "Autenticação da Pluggy indisponível.":
                raise
            if self._api_key == key:
                self._expires_at = 0
            if method != "GET":
                raise
            return await self._send(method, path, api_key=await self._key(), **kwargs)

    async def authenticate(self) -> None:
        """Verify credentials without exposing the API key to callers."""
        await self._key()

    async def list_all(self, path: str, params: dict[str, object], *, limit: int) -> list[dict]:
        results = []
        for page in range(1, 21):
            data = await self.request("GET", path, params={**params, "page": page})
            try:
                data = NumberedPage.model_validate(data)
            except ValidationError:
                raise invalid_response() from None
            if data.page != page:
                raise invalid_response()
            results.extend(data.results)
            if len(results) > limit:
                raise HTTPException(422, "Quantidade de recursos da Pluggy excede o limite desta operação.")
            if page >= data.totalPages:
                return results
        raise invalid_response()

    async def transactions(self, account_id: str, date_from: str, date_to: str) -> list[dict]:
        params = {"accountId": account_id, "dateFrom": date_from, "dateTo": date_to}
        results, seen = [], set()
        for _ in range(40):
            data = await self.request("GET", "/v2/transactions", params=params)
            rows = data.get("results")
            if not isinstance(rows, list) or "next" not in data or len(rows) > 500:
                raise invalid_response()
            results.extend(rows)
            if len(results) > MAX_TRANSACTIONS:
                raise HTTPException(422, "Extrato excede 20.000 transações; reduza o período.")
            cursor = data["next"]
            if cursor is None:
                return results
            if not isinstance(cursor, str) or len(cursor) > 4096 or not cursor.startswith("?"):
                raise invalid_response()
            parts = urlsplit(cursor)
            query = parse_qs(parts.query, keep_blank_values=True)
            after = query.get("after", [])
            if (
                parts.scheme
                or parts.netloc
                or parts.path
                or parts.fragment
                or len(after) != 1
                or not after[0]
            ):
                raise invalid_response()
            # Treat `next` as a cursor, never as an arbitrary URL or authorization scope.
            for name in ("accountId", "dateFrom", "dateTo"):
                if name in query and query[name] != [params[name]]:
                    raise invalid_response()
            if after[0] in seen:
                raise invalid_response()
            seen.add(after[0])
            params["after"] = after[0]
        raise HTTPException(422, "Extrato excede o limite de páginas; reduza o período.")


async def get_pluggy(request: Request, db: Session = Depends(get_db)) -> PluggyClient:
    from .pluggy_configuration_store import effective_settings

    settings = effective_settings(db)
    claims = context()
    tenant = (claims["organization_id"], claims["company_id"])
    if not hasattr(request.app.state, "pluggy_clients"):
        request.app.state.pluggy_clients = OrderedDict()
    cache = request.app.state.pluggy_clients
    provider = cache.get(tenant)
    # Read persisted settings on every call: rotations also work across workers.
    if provider is None or provider.settings != settings:
        provider = cache[tenant] = PluggyClient(settings)
    cache.move_to_end(tenant)
    while len(cache) > 128:
        cache.popitem(last=False)
    return provider
