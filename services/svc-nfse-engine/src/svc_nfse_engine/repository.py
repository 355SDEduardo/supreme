"""NFS-e transactional state, with the same contract for local and remote storage."""
from __future__ import annotations

from contextlib import contextmanager
import json

from sqlalchemy import Column, JSON, MetaData, String, Table, select, delete, insert, update
from sqlalchemy.dialects.postgresql import JSONB
from supreme_common import fiscal_database
from supreme_common.object_storage import ObjectStorage
from supreme_common.state import tenant_database
from supreme_common.events import make_event

FIELDS = {
    'artifacts': ('sha', 'filename', 'content'),
    'notes': ('key', 'sha', 'note', 'canonical', 'status'),
    'snapshots': ('version', 'body'), 'metadata': ('key', 'body'),
    'tombstones': ('key',), 'outbox': ('id', 'body'),
}
JSON_FIELDS = {'note', 'canonical', 'body'}
metadata = MetaData(schema='nfse')
tables = {}
for name, fields in FIELDS.items():
    tables[name] = Table('processed_notes' if name == 'notes' else name, metadata,
        Column('organization_id', String(100), primary_key=True),
        Column('company_id', String(100), primary_key=True),
        *[Column(field, JSON().with_variant(JSONB, 'postgresql') if field in JSON_FIELDS else String,
                 primary_key=index == 0, nullable=False) for index, field in enumerate(fields)])


class Store:
    def __init__(self, db, scope=None):
        self.db, self.scope = db, scope
        if scope is None:
            for name, fields in FIELDS.items():
                definition = ','.join(f'{field} ' + ('BLOB' if field == 'content' else 'TEXT') +
                                      (' PRIMARY KEY' if i == 0 else '') for i, field in enumerate(fields))
                db.execute(f'CREATE TABLE IF NOT EXISTS {name} ({definition})')

    def _where(self, table, filters):
        return [table.c[k] == v for k, v in {**self.scope, **filters}.items()]

    def rows(self, name: str, columns: tuple[str, ...], **filters) -> list[tuple]:
        assert name in FIELDS and set(columns).issubset(FIELDS[name]) and set(filters).issubset(FIELDS[name])
        if self.scope is None:
            query = f'SELECT {",".join(columns)} FROM {name}'
            if filters:
                query += ' WHERE ' + ' AND '.join(f'{k}=?' for k in filters)
            query += ' ORDER BY ' + ('rowid' if name == 'artifacts' else FIELDS[name][0])
            return self.db.execute(query, tuple(filters.values())).fetchall()
        table = tables[name]
        result = self.db.execute(select(*(table.c[c] for c in columns)).where(
            *self._where(table, filters)).order_by(table.c[FIELDS[name][0]])).all()
        return [tuple(ObjectStorage('nfse-xml').get(value) if field == 'content' else
                      json.dumps(value) if field in JSON_FIELDS else value
                      for field, value in zip(columns, row)) for row in result]

    def one(self, name: str, columns: tuple[str, ...], **filters):
        rows = self.rows(name, columns, **filters)
        return rows[0] if rows else None

    def delete(self, name: str, **filters) -> None:
        assert name in FIELDS and set(filters).issubset(FIELDS[name])
        if self.scope is None:
            query = f'DELETE FROM {name}' + (' WHERE ' + ' AND '.join(f'{k}=?' for k in filters) if filters else '')
            self.db.execute(query, tuple(filters.values()))
        else:
            table = tables[name]
            self.db.execute(delete(table).where(*self._where(table, filters)))

    def put(self, name: str, values: tuple, *, ignore: bool = False) -> None:
        fields = FIELDS[name]
        if self.scope is None:
            self.db.execute(f'INSERT OR {"IGNORE" if ignore else "REPLACE"} INTO {name} '
                            f'VALUES({",".join("?" for _ in fields)})', values)
            return
        table = tables[name]
        data = dict(zip(fields, values))
        key = {fields[0]: values[0]}
        exists = self.db.execute(select(table.c[fields[0]]).where(*self._where(table, key))).first()
        if exists and ignore:
            return
        for field in fields:
            if field in JSON_FIELDS:
                data[field] = json.loads(data[field])
            elif field == 'content':
                data[field] = ObjectStorage('nfse-xml').put(data[field])
        if exists:
            self.db.execute(update(table).where(*self._where(table, key)).values(**data))
        else:
            self.db.execute(insert(table).values(**self.scope, **data))

    def enqueue(self, kind: str, payload: dict, event_id: str) -> None:
        event = make_event(kind, payload, event_id)
        self.put('outbox', (event.event_id, event.model_dump_json()), ignore=True)


@contextmanager
def database():
    from .workspace import current_workspace
    if workspace := current_workspace.get():
        with workspace.database() as db:
            yield Store(db)
    elif fiscal_database.enabled('nfse'):
        with fiscal_database.transaction('nfse') as (db, scope):
            yield Store(db, scope)
    else:
        with tenant_database('nfse') as db:
            yield Store(db)


def drain(service: str = 'nfse') -> int:
    if not fiscal_database.enabled('nfse'):
        from supreme_common.sqlite_outbox import drain as local_drain
        local_drain(service)
        return 0
    return fiscal_database.deliver_outbox('nfse', tables['outbox'], ('organization_id', 'company_id', 'id'))


async def run(service: str = 'nfse') -> None:
    import asyncio
    import logging
    while True:
        try:
            await asyncio.to_thread(drain, service)
        except Exception:
            logging.getLogger(__name__).error('Outbox NFS-e pendente; entrega será repetida.')
        await asyncio.sleep(1)
