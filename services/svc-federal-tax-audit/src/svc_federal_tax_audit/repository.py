"""Audit inputs in private Storage and versioned PostgreSQL snapshots."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
import json
import uuid

from sqlalchemy import Boolean, Column, DateTime, JSON, MetaData, String, Table, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from supreme_common.fiscal_database import transaction
from supreme_common.object_storage import ObjectStorage

metadata = MetaData(schema='tax_audit')
files = Table('workspace_files', metadata,
    Column('organization_id', String(100), primary_key=True),
    Column('company_id', String(100), primary_key=True),
    Column('name', String(200), primary_key=True), Column('reference', String(1000), nullable=False))
snapshots = Table('audit_snapshots', metadata,
    Column('version_id', UUID(as_uuid=False), primary_key=True), Column('organization_id', String(100)),
    Column('company_id', String(100)), Column('periodo', String(20)), Column('is_active', Boolean),
    Column('snapshot_payload', JSON().with_variant(JSONB, 'postgresql')),
    Column('created_at', DateTime(timezone=True)))
outbox = Table('event_outbox', metadata,
    Column('organization_id', String(100), primary_key=True),
    Column('company_id', String(100), primary_key=True),
    Column('id', String(100), primary_key=True),
    Column('body', JSON().with_variant(JSONB, 'postgresql'), nullable=False))


def criteria(table, scope):
    return [table.c[k] == v for k, v in scope.items()]


def put_file(name: str, content: bytes) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Nome de documento inválido.')
    reference = ObjectStorage('tax-audit-workspaces').put(content)
    with transaction('tax_audit') as (db, scope):
        where = [*criteria(files, scope), files.c.name == name]
        if db.execute(select(files.c.name).where(*where)).first():
            db.execute(update(files).where(*where).values(reference=reference))
        else:
            db.execute(insert(files).values(**scope, name=name, reference=reference))


@contextmanager
def materialized_workspace():
    with transaction('tax_audit') as (db, scope):
        rows = db.execute(select(files.c.name, files.c.reference).where(*criteria(files, scope))).all()
    with TemporaryDirectory(prefix='supreme-audit-') as directory:
        root = Path(directory)
        for name, reference in rows:
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Documento fora do workspace.')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ObjectStorage('tax-audit-workspaces').get(reference))
        yield root


def save_snapshot(data: dict, event=None) -> None:
    with transaction('tax_audit') as (db, scope):
        db.execute(update(snapshots).where(*criteria(snapshots, scope), snapshots.c.is_active.is_(True)).values(is_active=False))
        db.execute(insert(snapshots).values(version_id=str(uuid.UUID(data['version'])), **scope,
            periodo='default', is_active=True, snapshot_payload=data, created_at=datetime.now(timezone.utc)))
        if event is not None:
            identity = [*criteria(outbox, scope), outbox.c.id == event.event_id]
            if db.execute(select(outbox.c.id).where(*identity)).first() is None:
                db.execute(insert(outbox).values(**scope, id=event.event_id, body=json.loads(event.model_dump_json())))


def drain() -> int:
    from supreme_common.fiscal_database import deliver_outbox
    return deliver_outbox('tax_audit', outbox, ('organization_id', 'company_id', 'id'))


async def run() -> None:
    import asyncio
    import logging
    from supreme_common.fiscal_database import enabled
    while True:
        try:
            if enabled('tax_audit'):
                await asyncio.to_thread(drain)
        except Exception:
            logging.getLogger(__name__).error('Outbox de auditoria pendente; entrega será repetida.')
        await asyncio.sleep(1)


def read_snapshot() -> dict | None:
    with transaction('tax_audit') as (db, scope):
        return db.execute(select(snapshots.c.snapshot_payload).where(*criteria(snapshots, scope),
            snapshots.c.is_active.is_(True)).order_by(snapshots.c.created_at.desc()).limit(1)).scalar_one_or_none()
