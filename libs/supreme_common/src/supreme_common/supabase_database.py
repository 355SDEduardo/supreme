"""Explicit schema routing for the single PostgreSQL database hosted by Supabase."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

SERVICE_SCHEMAS = {
    "svc-security-iam": "iam",
    "svc-companies": "companies",
    "svc-obligations": "obligations",
    "svc-documents": "documents",
    "svc-bank-reconciliation": "reconciliation",
    "svc-finance-bpo": "finance",
    "svc-fiscal-gov": "fiscal_gov",
    "svc-client-portal": "portal",
    "svc-analytics-dre": "analytics",
    "svc-accounting-ai": "ai",
}


def postgres_configuration(raw_url: str, schema: str) -> tuple[URL, dict]:
    try:
        url = make_url(raw_url)
    except Exception:
        raise ValueError("URL PostgreSQL do Supabase inválida; confira a configuração privada.") from None
    if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("Supabase exige PostgreSQL com o driver psycopg v3.")
    url = url.set(drivername="postgresql+psycopg")
    if os.getenv("SUPREME_ENV") == "production":
        if (url.username or "").split(".")[0] != f"supreme_{schema}":
            raise ValueError("Use uma credencial exclusiva do serviço em produção.")
        if url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("Supabase em produção exige TLS (sslmode=require ou verify-full).")
    mode = os.getenv("SUPABASE_POOL_MODE", "auto")
    if mode == "auto":
        mode = "transaction" if url.port == 6543 else "session"
    if mode not in {"session", "transaction"}:
        raise ValueError("SUPABASE_POOL_MODE deve ser auto, session ou transaction.")
    options = {
        "pool_pre_ping": True,
        "hide_parameters": True,
        "connect_args": {"prepare_threshold": None, "connect_timeout": 10},
        "execution_options": {
            "schema_translate_map": {None: schema},
            "supreme_managed_schema": True,
        },
    }
    if mode == "transaction":
        options["poolclass"] = NullPool
    else:
        options.update(pool_size=2, max_overflow=1, pool_timeout=10, pool_recycle=300)
    return url, options


def engine_configuration(slug: str, explicit_url: str | None = None) -> tuple[URL, dict]:
    schema = SERVICE_SCHEMAS.get(slug)
    scoped = os.getenv(f"SUPABASE_{schema.upper()}_DB_URL", "") if schema else ""
    shared = os.getenv("SUPABASE_DB_URL", "")
    # Explicit SQLite remains available for disposable tests, never as a PostgreSQL bypass.
    explicit_local = False
    if explicit_url:
        try:
            explicit_local = make_url(explicit_url).get_backend_name() == "sqlite"
        except Exception:
            raise ValueError("URL de banco inválida; confira a configuração privada.") from None
    managed = not explicit_local and (scoped or shared or os.getenv("SUPREME_DATABASE_MODE") == "supabase")
    raw_url = explicit_url or scoped or shared or os.getenv("DATABASE_URL")
    if managed:
        if not schema:
            raise ValueError("Serviço sem schema Supabase cadastrado.")
        if not raw_url:
            raise ValueError("Configure a URL privada do serviço no Supabase.")
        return postgres_configuration(raw_url, schema)
    if not raw_url:
        path = Path(os.getenv("DB_ROOT_DIR", "./data/db"))
        path.mkdir(parents=True, exist_ok=True)
        raw_url = f"sqlite:///{(path / (slug + '.db')).as_posix()}"
    url = make_url(raw_url)
    return url, {
        "connect_args": {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {},
        "pool_pre_ping": True,
    }


def create_service_engine(slug: str, explicit_url: str | None = None) -> Engine:
    url, options = engine_configuration(slug, explicit_url)
    return create_engine(url, **options)
