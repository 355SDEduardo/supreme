"""Connection/transaction infrastructure; each fiscal domain owns its tables."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from hashlib import sha256
import os

from sqlalchemy import create_engine, delete, select, text
from .auth_context import context
from .supabase_database import postgres_configuration


def enabled(schema: str) -> bool:
    return bool(os.getenv('SUPREME_DATABASE_MODE') == 'supabase' or
                os.getenv(f'SUPABASE_{schema.upper()}_DB_URL') or os.getenv('SUPABASE_DB_URL'))


def validate_storage_configuration(schema: str) -> None:
    """Remote fiscal files cannot be persisted to a process-local volume."""
    if not enabled(schema):
        return
    from fastapi import HTTPException
    from .object_storage import ObjectStorage, enabled as storage_enabled

    if not storage_enabled():
        raise RuntimeError('Banco fiscal remoto exige SUPREME_STORAGE_MODE=supabase para o Storage privado.')
    bucket = {'nfse': 'nfse-xml', 'tax_audit': 'tax-audit-workspaces'}[schema]
    try:
        ObjectStorage(bucket)  # Validates configuration only; never makes an HTTP request.
    except HTTPException:
        raise RuntimeError('Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY para o Storage privado.') from None


def tenant() -> dict[str, str]:
    claims = context()
    if not claims.get('company_id'):
        raise ValueError('Empresa obrigatória para persistência fiscal.')
    return {'organization_id': claims['organization_id'], 'company_id': claims['company_id']}


@lru_cache(maxsize=16)
def _engine(schema: str, url: str, mode: str, environment: str):
    target, options = postgres_configuration(url, schema)
    return create_engine(target, **options)


def engine(schema: str):
    url = os.getenv(f'SUPABASE_{schema.upper()}_DB_URL') or os.getenv('SUPABASE_DB_URL') or os.getenv('DATABASE_URL')
    if not url:
        raise ValueError(f'Configure SUPABASE_{schema.upper()}_DB_URL.')
    return _engine(schema, url, os.getenv('SUPABASE_POOL_MODE', 'auto'), os.getenv('SUPREME_ENV', ''))


@contextmanager
def transaction(schema: str):
    scope = tenant()
    with engine(schema).begin() as db:
        # Serialize compound changes per tenant across workers; released at commit/rollback.
        if db.dialect.name == 'postgresql':
            key = int.from_bytes(sha256((schema + ':' + scope['organization_id'] + ':' +
                                        scope['company_id']).encode()).digest()[:8], signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
        yield db, scope


def deliver_outbox(schema: str, table, key_columns: tuple[str, ...]) -> int:
    """Publish a durable batch. A failure rolls the deletion back so the batch can be repeated."""
    from .events import DomainEvent, publish_envelope

    delivered = 0
    with engine(schema).begin() as db:
        query = select(table).limit(100)
        if db.dialect.name == 'postgresql':
            query = query.with_for_update(skip_locked=True)
        for row in db.execute(query).mappings().all():
            body = row['body']
            event = DomainEvent.model_validate_json(body) if isinstance(body, str) else DomainEvent.model_validate(body)
            publish_envelope(event)
            db.execute(delete(table).where(*(table.c[column] == row[column] for column in key_columns)))
            delivered += 1
    return delivered
