from __future__ import annotations

import asyncio
from threading import Event, get_ident
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from supreme_common import events, postgres_journal
from supreme_common.auth_context import current_context


def envelope():
    return events.DomainEvent(
        event_id="synthetic-event",
        event_type="Example",
        organization_id="org-1",
        company_id="company-1",
        actor_user_id="user-1",
        correlation_id="test-1",
        payload={"amount": "12.34"},
    )


@pytest.mark.asyncio
async def test_journal_acknowledges_only_after_handler_success_and_retries_failure(monkeypatch):
    monkeypatch.setenv("SUPABASE_EVENTS_DB_URL", "postgresql://synthetic")
    backend = MagicMock()
    backend.pending.return_value = [("synthetic-event", envelope().model_dump(mode="json"))]
    monkeypatch.setattr(postgres_journal, "journal", lambda _: backend)
    attempts = []

    async def handler(event):
        claims = current_context.get()
        assert claims["organization_id"] == "org-1"
        assert claims["company_id"] == "company-1"
        attempts.append(event.event_id)
        if len(attempts) == 1:
            raise RuntimeError("transient synthetic failure")

    await events.consume_once("consumer", {"Example": handler})
    backend.acknowledge.assert_not_called()
    assert current_context.get() is None
    await events.consume_once("consumer", {"Example": handler})
    backend.acknowledge.assert_called_once_with("consumer", "synthetic-event")
    assert current_context.get() is None


def test_publish_uses_postgres_without_creating_local_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_EVENTS_DB_URL", "postgresql://synthetic")
    monkeypatch.setenv("EVENT_DB_PATH", str(tmp_path / "must-not-exist.db"))
    backend = MagicMock()
    monkeypatch.setattr(postgres_journal, "journal", lambda _: backend)
    event = envelope()
    assert events.publish_envelope(event) == event.event_id
    backend.publish.assert_called_once_with(event)
    assert not (tmp_path / "must-not-exist.db").exists()


def test_incomplete_remote_setup_never_silently_uses_sqlite(monkeypatch):
    monkeypatch.setenv("SUPREME_DATABASE_MODE", "supabase")
    with pytest.raises(ValueError, match="SUPABASE_EVENTS_DB_URL"):
        postgres_journal.journal_url()
    monkeypatch.setenv("SUPABASE_EVENTS_DB_URL", "postgresql://synthetic")
    monkeypatch.setenv("REDIS_URL", "redis://synthetic")
    with pytest.raises(ValueError, match="REDIS_URL"):
        postgres_journal.journal_url()


def test_journal_sql_is_deduplicated_and_pending_reads_are_bounded():
    engine = MagicMock()
    backend = postgres_journal.PostgresJournal(engine)
    backend.publish(envelope())
    stmt = engine.begin.return_value.__enter__.return_value.execute.call_args.args[0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO events.events" in compiled
    assert "ON CONFLICT (event_id) DO NOTHING" in compiled
    backend.pending("consumer")
    stmt = engine.connect.return_value.__enter__.return_value.execute.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "NOT (EXISTS" in str(compiled)
    assert 100 in compiled.params.values()


@pytest.mark.asyncio
async def test_remote_journal_io_keeps_loop_responsive_and_propagates_context(monkeypatch):
    monkeypatch.setenv("SUPABASE_EVENTS_DB_URL", "postgresql://synthetic")
    loop = asyncio.get_running_loop()
    loop_thread = get_ident()
    backend = MagicMock()
    order = []
    outer = {"correlation_id": "outer-context"}

    def check_worker():
        assert get_ident() != loop_thread
        assert current_context.get() == outer
        heartbeat = Event()
        loop.call_soon_threadsafe(heartbeat.set)
        assert heartbeat.wait(2), "event loop blocked during journal I/O"

    def pending(subscriber):
        check_worker()
        order.append("pending")
        return [("synthetic-event", envelope().model_dump(mode="json"))]

    def acknowledge(subscriber, event_id):
        check_worker()
        assert order == ["pending", "handler"]
        order.append("ack")

    async def handler(event):
        assert get_ident() == loop_thread
        assert current_context.get()["organization_id"] == "org-1"
        order.append("handler")

    backend.pending.side_effect = pending
    backend.acknowledge.side_effect = acknowledge
    monkeypatch.setattr(postgres_journal, "journal", lambda _: backend)
    marker = current_context.set(outer)
    try:
        await events.consume_once("consumer", {"Example": handler})
        assert current_context.get() == outer
        assert order == ["pending", "handler", "ack"]
    finally:
        current_context.reset(marker)


@pytest.mark.asyncio
@pytest.mark.parametrize("publish_fails", [False, True])
async def test_outbox_transaction_runs_off_loop_and_deletes_only_after_publish(monkeypatch, publish_fails):
    from contextlib import contextmanager, suppress
    from types import SimpleNamespace
    from sqlalchemy import Column, Integer, MetaData, Table, Text

    loop = asyncio.get_running_loop()
    loop_thread = get_ident()
    finished = asyncio.Event()
    trace = []
    failures = []
    outer = {"correlation_id": "outbox-context"}
    table = Table("outbox", MetaData(), Column("id", Integer), Column("body", Text))
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = [
        {"id": 1, "body": envelope().model_dump_json()}
    ]

    @contextmanager
    def begin():
        try:
            assert get_ident() != loop_thread
            assert current_context.get() == outer
            trace.append("begin")
            yield connection
            trace.append("commit")
        except Exception as exc:
            failures.append(exc)
            trace.append("rollback")
            raise
        finally:
            loop.call_soon_threadsafe(finished.set)

    def publish(event):
        trace.append("publish")
        heartbeat = Event()
        loop.call_soon_threadsafe(heartbeat.set)
        assert heartbeat.wait(2), "event loop blocked during publishing"
        if publish_fails:
            raise OSError("synthetic journal unavailable")

    monkeypatch.setattr(events, "publish_envelope", publish)
    app = SimpleNamespace(state=SimpleNamespace(engine=SimpleNamespace(begin=begin), outbox=table))
    marker = current_context.set(outer)
    task = asyncio.create_task(events.outbox_loop(app))
    try:
        await asyncio.wait_for(finished.wait(), timeout=3)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        current_context.reset(marker)
    assert trace == ["begin", "publish", "rollback" if publish_fails else "commit"]
    assert connection.execute.call_count == (1 if publish_fails else 2)
    if publish_fails:
        assert isinstance(failures[0], OSError)
    else:
        assert failures == []
        assert str(connection.execute.call_args.args[0]).startswith("DELETE FROM outbox")
