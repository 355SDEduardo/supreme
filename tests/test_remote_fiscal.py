"""Remote fiscal persistence, tenant isolation, expiry and recovery. No live Supabase."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, update
from supreme_common.auth_context import current_context
from supreme_common.events import make_event

BASE = {
    'sub': 'user-1', 'organization_id': 'org-a', 'company_id': 'company-a',
    'correlation_id': 'corr-remote', 'jti': 'jti-1', 'role': 'service', 'session_id': 'sess-1',
}


def registration(ncm):
    return {
        'NCM': ncm, 'Posição': '1', 'Subposição': '1', 'Subitem': '1', 'Estado': 'SP',
        'Alíquota Interna': '18', 'Base Reduzida': '0', 'Diferimento': '0', 'FCP': '0',
        'Isenção': '0', 'Não Incidência': '0', 'ST': 'Não', 'Suspensão': '0', 'MVA': '', 'CEST': '',
    }


class MemoryStorage:
    def __init__(self, objects):
        self.objects = objects

    def __call__(self, bucket, client=None):
        return self

    def put(self, content):
        digest = sha256(content).hexdigest()
        reference = f'supabase://memory/tenant/{digest}'
        if reference in self.objects and self.objects[reference] != content:
            raise HTTPException(502, 'Falha ao preservar objeto no Storage.')
        self.objects[reference] = bytes(content)
        return reference

    def get(self, reference):
        content = self.objects[reference]
        if sha256(content).hexdigest() != reference.rsplit('/', 1)[-1]:
            raise HTTPException(502, 'Integridade do objeto inválida.')
        return content


@pytest.fixture
def fiscal(monkeypatch):
    engine = create_engine('sqlite://', execution_options={
        'schema_translate_map': {'nfse': None, 'nfe': None, 'tax_audit': None}})
    from svc_nfse_engine.repository import metadata as nfse_metadata
    from svc_nfe_difal.repository import metadata as nfe_metadata
    from svc_federal_tax_audit.repository import metadata as audit_metadata
    for metadata in (nfse_metadata, nfe_metadata, audit_metadata):
        metadata.create_all(engine)
    import supreme_common.fiscal_database as database

    @contextmanager
    def transaction(schema):
        scope = database.tenant()
        with engine.begin() as db:
            yield db, scope

    monkeypatch.setattr(database, 'transaction', transaction)
    monkeypatch.setattr(database, 'engine', lambda schema: engine)
    monkeypatch.setattr(database, 'enabled', lambda schema: True)
    tokens = []

    def use(**overrides):
        if tokens:
            current_context.reset(tokens.pop())
        tokens.append(current_context.set({**BASE, **overrides}))

    use()
    try:
        yield engine, use
    finally:
        while tokens:
            current_context.reset(tokens.pop())


def test_nfe_sessions_are_isolated_and_expire(fiscal):
    from svc_nfe_difal.repository import read_state, sessions, write_state
    engine, use = fiscal
    write_state('alpha', {'nfes': [1]})
    use(company_id='company-b')
    assert read_state('alpha') == {}
    use(company_id='company-a')
    assert read_state('alpha') == {'nfes': [1]}
    with engine.begin() as db:
        db.execute(update(sessions).values(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    assert read_state('alpha') == {}


def test_expired_sessions_do_not_consume_the_active_limit(fiscal):
    from svc_nfe_difal.repository import sessions, write_state
    engine, _use = fiscal
    for number in range(100):
        write_state(f'session-{number}', {'n': number})
    with pytest.raises(HTTPException) as exc:
        write_state('session-extra', {'n': 'extra'})
    assert exc.value.status_code == 503
    with engine.begin() as db:
        db.execute(update(sessions).values(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    write_state('session-extra', {'n': 'extra'})


def test_catalog_replacement_rolls_back_and_stays_inside_the_company(fiscal, monkeypatch):
    from svc_nfe_difal import repository
    engine, use = fiscal
    repository.replace_catalog(json.dumps([registration('11111111')]).encode())
    use(company_id='company-b')
    assert repository.read_catalog() == {}
    repository.replace_catalog(json.dumps([registration('22222222')]).encode())
    use(company_id='company-a')
    assert '11111111' in repository.read_catalog()
    monkeypatch.setattr(repository.uuid, 'uuid4', lambda: uuid.UUID('00000000-0000-0000-0000-000000000001'))
    with pytest.raises(Exception):
        repository.replace_catalog(json.dumps([registration('33333333'), registration('44444444')]).encode())
    assert list(repository.read_catalog()) == ['11111111']
    use(company_id='company-b')
    assert list(repository.read_catalog()) == ['22222222']
    engine.dispose()


def test_snapshot_and_event_survive_partial_failure(fiscal, monkeypatch):
    from svc_federal_tax_audit import repository
    published = []

    def fail_publish(event):
        published.append(event.event_id)
        raise RuntimeError('journal indisponível')

    monkeypatch.setattr('supreme_common.events.publish_envelope', fail_publish)
    first = {'version': str(uuid.uuid4()), 'result': {'ok': True}}
    repository.save_snapshot(first)
    event = make_event('FederalTaxAuditCompleted', {'snapshot_version': 'next'}, event_id='event-next')
    real_insert = repository.insert

    def fail_outbox(table):
        if table is repository.outbox:
            raise RuntimeError('falha ao registrar evento')
        return real_insert(table)

    monkeypatch.setattr(repository, 'insert', fail_outbox)
    with pytest.raises(RuntimeError):
        repository.save_snapshot({'version': str(uuid.uuid4()), 'result': {'ok': False}}, event)
    assert repository.read_snapshot()['version'] == first['version']
    assert published == []
    monkeypatch.setattr(repository, 'insert', real_insert)
    second = {'version': str(uuid.uuid4()), 'result': {'ok': True}}
    saved = make_event('FederalTaxAuditCompleted', {'snapshot_version': second['version']}, event_id=second['version'])
    repository.save_snapshot(second, saved)
    with pytest.raises(RuntimeError):
        repository.drain()
    assert repository.read_snapshot()['version'] == second['version']
    published.clear()
    monkeypatch.setattr('supreme_common.events.publish_envelope', lambda event: published.append(event.event_id))
    assert repository.drain() == 1
    assert published == [second['version']]
    assert repository.drain() == 0


def test_audit_upload_is_isolated_and_retried_after_database_failure(fiscal, monkeypatch):
    from svc_federal_tax_audit import repository
    _engine, use = fiscal
    storage = MemoryStorage({})
    monkeypatch.setattr(repository, 'ObjectStorage', storage)
    real_insert = repository.insert
    state = {'fail': True}

    def fail_once(table):
        if state['fail'] and table is repository.files:
            state['fail'] = False
            raise RuntimeError('falha ao gravar referência')
        return real_insert(table)

    monkeypatch.setattr(repository, 'insert', fail_once)
    with pytest.raises(RuntimeError):
        repository.put_file('notas/Consolidado_NFSe.json', b'{"notas":[]}')
    monkeypatch.setattr(repository, 'insert', real_insert)
    repository.put_file('notas/Consolidado_NFSe.json', b'{"notas":[]}')
    use(company_id='company-b')
    with repository.materialized_workspace() as empty:
        assert list(empty.rglob('*')) == []
    use(company_id='company-a')
    with repository.materialized_workspace() as folder:
        assert (folder / 'notas' / 'Consolidado_NFSe.json').read_bytes() == b'{"notas":[]}'
    assert len(storage.objects) == 1


def test_nfse_artifact_and_outbox_recover_without_crossing_companies(fiscal, monkeypatch):
    from svc_nfse_engine.repository import database, drain
    _engine, use = fiscal
    storage = MemoryStorage({})
    monkeypatch.setattr('svc_nfse_engine.repository.ObjectStorage', storage)
    published = []

    def fail_publish(event):
        published.append(event.event_id)
        raise RuntimeError('journal indisponível')

    monkeypatch.setattr('supreme_common.events.publish_envelope', fail_publish)
    with database() as db:
        db.put('artifacts', ('a' * 64, 'nota.xml', b'<xml/>'))
        db.enqueue('NFSeBatchProcessed', {'snapshot_version': 'v1'}, event_id='v1')
    with pytest.raises(RuntimeError):
        drain()
    monkeypatch.setattr('supreme_common.events.publish_envelope', lambda event: published.append('ok:' + event.event_id))
    assert drain() == 1
    assert published == ['v1', 'ok:v1']
    use(company_id='company-b')
    with database() as db:
        assert db.rows('artifacts', ('content',)) == []
    use(company_id='company-a')
    with database() as db:
        assert db.rows('artifacts', ('filename', 'content')) == [('nota.xml', b'<xml/>')]

    class Unavailable:
        def __init__(self, bucket, client=None):
            pass

        def put(self, content):
            raise HTTPException(503, 'Storage indisponível; tente novamente.')

    monkeypatch.setattr('svc_nfse_engine.repository.ObjectStorage', Unavailable)
    with pytest.raises(HTTPException):
        with database() as db:
            db.put('artifacts', ('b' * 64, 'outra.xml', b'<xml>2</xml>'))
    monkeypatch.setattr('svc_nfse_engine.repository.ObjectStorage', storage)
    with database() as db:
        names = [row[0] for row in db.rows('artifacts', ('filename',))]
    assert names == ['nota.xml']
