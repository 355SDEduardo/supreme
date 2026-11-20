from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import httpx

import pytest

from scripts.supabase_maintenance import (
    ARCHIVE_COPY, PENDING_EVENTS, archive_delivered_events, assert_statement_is_safe, probe, report,
)


class Connection:
    def __init__(self, role):
        self.role = role
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if 'current_user' in sql:
            return SimpleNamespace(scalar_one=lambda: self.role)
        if 'without_delivery' in sql or 'total_events' in sql:
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: {
                'total_events': 4, 'without_delivery': 1, 'archived': 2}))
        return SimpleNamespace(rowcount=3)


def test_maintenance_statements_do_not_delete_history():
    assert_statement_is_safe(ARCHIVE_COPY)
    assert_statement_is_safe(PENDING_EVENTS)
    assert 'DELETE' not in ARCHIVE_COPY.upper()
    assert 'audit_logs' not in ARCHIVE_COPY
    assert 'events.deliveries' in ARCHIVE_COPY
    with pytest.raises(ValueError):
        assert_statement_is_safe('DELETE FROM iam.audit_logs')
    with pytest.raises(ValueError):
        assert_statement_is_safe('UPDATE events.events SET kind = kind')


def test_runtime_role_cannot_archive_and_report_is_read_only():
    with pytest.raises(PermissionError):
        archive_delivered_events(Connection('supreme_events'), 365)
    admin = Connection('postgres')
    assert archive_delivered_events(admin, 365) == 3
    assert admin.statements[-1][1] == {'days': 365}
    assert report(Connection('supreme_events')) == {'total_events': 4, 'without_delivery': 1}
    assert 'events_archive' not in PENDING_EVENTS
    with pytest.raises(ValueError):
        archive_delivered_events(admin, 0)


def test_probe_does_not_contact_an_unconfigured_project(capsys):
    assert probe() == 2
    assert 'não executada' in capsys.readouterr().out


def test_probe_rejects_partial_configuration_without_network(monkeypatch, capsys):
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPREME_DATABASE_MODE', 'supabase')
    monkeypatch.setenv('SUPREME_STORAGE_MODE', 'supabase')
    assert probe() == 2
    output = capsys.readouterr().out
    assert 'SUPABASE_IAM_DB_URL' in output
    assert 'SUPABASE_EVENTS_DB_URL' in output
    assert 'SUPABASE_SERVICE_ROLE_KEY' in output


@pytest.fixture
def remote_probe(monkeypatch):
    from scripts import supabase_maintenance as maintenance
    from supreme_common.object_storage import BUCKET_LIMITS, ObjectStorage

    monkeypatch.setenv('SUPABASE_DB_URL', 'postgresql://postgres:synthetic@localhost:6543/postgres')
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'synthetic-storage-key')
    engines = []

    def factory(url, **options):
        db = Mock()

        @contextmanager
        def connect():
            yield db

        engine = SimpleNamespace(connect=connect, dispose=Mock(), db=db, url=url, options=options)
        engines.append(engine)
        return engine

    buckets = [dict(id=name, name=name, public=False, file_size_limit=limit)
               for name, limit in BUCKET_LIMITS.items()]
    response = httpx.Response(200, json=buckets)
    monkeypatch.setattr(maintenance, 'create_engine', factory)
    monkeypatch.setattr(httpx, 'get', lambda *args, **kwargs: response)
    monkeypatch.setattr(ObjectStorage, '_request', lambda *args, **kwargs: httpx.Response(200, json=buckets))
    return engines, buckets


def test_probe_checks_each_runtime_schema_read_only_and_closes_connections(remote_probe):
    from scripts.supabase_maintenance import PROBE_SCHEMAS
    from scripts.supabase_schema import runtime_tables

    engines, _ = remote_probe
    assert probe() == 0
    assert len(engines) == len(PROBE_SCHEMAS)
    expected = {(table.schema, table.name) for table in runtime_tables()}
    checked = set()
    for engine in engines:
        assert engine.url.drivername == 'postgresql+psycopg'
        assert engine.options['connect_args']['prepare_threshold'] is None
        assert str(engine.db.execute.call_args_list[0].args[0]) == 'SET TRANSACTION READ ONLY'
        engine.dispose.assert_called_once()
        for call in engine.db.execute.call_args_list[1:]:
            statement = call.args[0]
            for table in statement.get_final_froms():
                checked.add((table.schema, table.name))
    assert checked == expected


@pytest.mark.parametrize('problem', ['missing', 'public', 'limit'])
def test_probe_rejects_unsafe_or_missing_storage_buckets(remote_probe, monkeypatch, problem):
    _, buckets = remote_probe
    if problem == 'missing':
        buckets.pop()
    elif problem == 'public':
        buckets[0]['public'] = True
    else:
        buckets[0]['file_size_limit'] = None
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: httpx.Response(200, json=buckets))
    assert probe() == 1


def test_report_cli_uses_runtime_driver_and_releases_connection(remote_probe, monkeypatch):
    from scripts import supabase_maintenance as maintenance

    engines, _ = remote_probe
    monkeypatch.setattr('sys.argv', ['supabase_maintenance'])
    monkeypatch.setattr(maintenance, 'report', lambda db: {'total_events': 0, 'without_delivery': 0})
    maintenance.main()
    assert len(engines) == 1
    engine = engines[0]
    assert engine.url.drivername == 'postgresql+psycopg'
    assert engine.options['connect_args']['prepare_threshold'] is None
    assert str(engine.db.execute.call_args_list[0].args[0]) == 'SET TRANSACTION READ ONLY'
    engine.dispose.assert_called_once()
