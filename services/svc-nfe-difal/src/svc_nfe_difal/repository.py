"""Tenant-owned NF-e catalog and expiring session repository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import uuid

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, JSON, MetaData, String, Table, delete, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from supreme_common.fiscal_database import transaction
from .core.fiscal_registration import FiscalRegistration, FiscalRegistrationService
from .core.ncm_comparison import load_fiscal_catalog_bytes, normalize_ncm

metadata = MetaData(schema='nfe')
catalog = Table('fiscal_catalog', metadata,
    Column('id', UUID(as_uuid=False), primary_key=True),
    Column('organization_id', String), Column('company_id', String),
    Column('ncm_code', String), Column('rule_payload', JSON().with_variant(JSONB, 'postgresql')))
sessions = Table('processing_sessions', metadata,
    Column('session_id', String, primary_key=True),
    Column('organization_id', String), Column('company_id', String),
    Column('summary_payload', JSON().with_variant(JSONB, 'postgresql')),
    Column('expires_at', DateTime(timezone=True)))
outbox = Table('event_outbox', metadata,
    Column('organization_id', String(100), primary_key=True),
    Column('company_id', String(100), primary_key=True),
    Column('id', String(100), primary_key=True),
    Column('body', JSON().with_variant(JSONB, 'postgresql'), nullable=False))


def criteria(table, scope):
    return [table.c[k] == v for k, v in scope.items()]


def session_key(key: str, scope: dict) -> str:
    from hashlib import sha256
    return sha256(json.dumps([scope, key], sort_keys=True).encode()).hexdigest()


def read_state(key: str) -> dict:
    with transaction('nfe') as (db, scope):
        now = datetime.now(timezone.utc)
        db.execute(delete(sessions).where(*criteria(sessions, scope), sessions.c.expires_at < now))
        return db.execute(select(sessions.c.summary_payload).where(*criteria(sessions, scope),
            sessions.c.session_id == session_key(key, scope))).scalar_one_or_none() or {}


def write_state(key: str, data: dict, event=None) -> None:
    with transaction('nfe') as (db, scope):
        now = datetime.now(timezone.utc)
        db.execute(delete(sessions).where(*criteria(sessions, scope), sessions.c.expires_at < now))
        key = session_key(key, scope)
        keys = db.execute(select(sessions.c.session_id).where(*criteria(sessions, scope))).scalars().all()
        if key not in keys and len(keys) >= 100:
            raise HTTPException(503, 'Limite de sessões ativas atingido.')
        values = dict(summary_payload=data, expires_at=now + timedelta(seconds=int(os.getenv('STATE_TTL_SECONDS', '7200'))))
        if key in keys:
            db.execute(update(sessions).where(*criteria(sessions, scope), sessions.c.session_id == key).values(**values))
        else:
            db.execute(insert(sessions).values(session_id=key, **scope, **values))
        if event is not None:
            identity = [*criteria(outbox, scope), outbox.c.id == event.event_id]
            if db.execute(select(outbox.c.id).where(*identity)).first() is None:
                db.execute(insert(outbox).values(**scope, id=event.event_id, body=json.loads(event.model_dump_json())))


def read_catalog():
    with transaction('nfe') as (db, scope):
        records = db.execute(select(catalog.c.rule_payload).where(*criteria(catalog, scope))).scalars().all()
    return load_fiscal_catalog_bytes(json.dumps(records, ensure_ascii=False).encode())


def replace_catalog(content: bytes) -> int:
    records = FiscalRegistrationService()._read_records(content)
    with transaction('nfe') as (db, scope):
        db.execute(delete(catalog).where(*criteria(catalog, scope)))
        for record in records:
            db.execute(insert(catalog).values(id=str(uuid.uuid4()), **scope,
                ncm_code=normalize_ncm(record['NCM']), rule_payload=record))
    return len(records)


def drain() -> int:
    from supreme_common.fiscal_database import deliver_outbox
    return deliver_outbox('nfe', outbox, ('organization_id', 'company_id', 'id'))


async def run() -> None:
    import asyncio
    import logging
    from supreme_common.fiscal_database import enabled
    while True:
        try:
            if enabled('nfe'):
                await asyncio.to_thread(drain)
        except Exception:
            logging.getLogger(__name__).error('Outbox NF-e pendente; entrega será repetida.')
        await asyncio.sleep(1)


def add_catalog(item: FiscalRegistration) -> int:
    service = FiscalRegistrationService()
    record = service._normalize_registration(item).to_json_dict()
    service._read_records(json.dumps([record], ensure_ascii=False).encode())
    with transaction('nfe') as (db, scope):
        keys = db.execute(select(catalog.c.ncm_code).where(*criteria(catalog, scope))).scalars().all()
        ncm = normalize_ncm(record['NCM'])
        if ncm in keys:
            raise ValueError(f'O NCM {ncm} já está cadastrado na base fiscal.')
        db.execute(insert(catalog).values(id=str(uuid.uuid4()), **scope, ncm_code=ncm, rule_payload=record))
        return len(keys) + 1
