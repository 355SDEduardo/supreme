"""Durable at-least-once events with consumer acknowledgements and retry.

Local mode uses an infrastructure SQLite log. Redis mode uses one stream per
subscriber; each subscriber has its own group so every interested service sees
each event. An event is acknowledged only after its handler commits.
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import uuid
from pydantic import BaseModel, Field
from .auth_context import context, current_context, create_access_token

log = logging.getLogger(__name__)

class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    organization_id: str
    company_id: str
    correlation_id: str
    actor_user_id: str
    payload: dict

@contextmanager
def event_db():
    path = Path(os.getenv('EVENT_DB_PATH', './data/events/events.db'))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=30) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, event_id TEXT UNIQUE, kind TEXT, body TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS deliveries (subscriber TEXT, event_id TEXT, PRIMARY KEY(subscriber,event_id))')
        yield db

def publish(event_type, payload, event_id=None):
    claims = context()
    event = DomainEvent(event_type=event_type, organization_id=claims['organization_id'],
        company_id=claims.get('company_id') or '', correlation_id=claims['correlation_id'],
        actor_user_id=claims['sub'], payload=payload, **({'event_id': event_id} if event_id else {}))
    publish_envelope(event)
    return event.event_id

def publish_envelope(event):
    # Always persist first: Redis delivery may be retried by the relay.
    with event_db() as db:
        db.execute('INSERT OR IGNORE INTO events(event_id,kind,body) VALUES(?,?,?)',
                   (event.event_id, event.event_type, event.model_dump_json()))
    return event.event_id

def make_event(event_type, payload, event_id=None):
    claims = context()
    return DomainEvent(event_type=event_type, organization_id=claims['organization_id'],
        company_id=claims.get('company_id') or '', correlation_id=claims['correlation_id'],
        actor_user_id=claims['sub'], payload=payload, **({'event_id': event_id} if event_id else {}))

async def outbox_loop(app):
    """Publishing is idempotent: a crash between broker write and deletion is safe."""
    from sqlalchemy import select, delete
    while True:
        table = app.state.outbox
        with app.state.engine.begin() as connection:
            for row in connection.execute(select(table).limit(100)).mappings().all():
                publish_envelope(DomainEvent.model_validate_json(row['body']))
                connection.execute(delete(table).where(table.c.id == row['id']))
        await asyncio.sleep(0.5)

async def consume_once(subscriber, handlers):
    with event_db() as db:
        rows = db.execute('SELECT e.event_id,e.body FROM events e LEFT JOIN deliveries d '
            'ON d.event_id=e.event_id AND d.subscriber=? WHERE d.event_id IS NULL ORDER BY e.id LIMIT 100', (subscriber,)).fetchall()
    for event_id, body in rows:
        event = DomainEvent.model_validate_json(body)
        handler = handlers.get(event.event_type)
        if handler:
            claims = {'sub': event.actor_user_id, 'organization_id': event.organization_id,
                      'company_id': event.company_id, 'role': 'service', 'correlation_id': event.correlation_id,
                      'mfa_verified': True}
            claims['_token'] = create_access_token(claims)
            marker = current_context.set(claims)
            try:
                await handler(event)
            except Exception:
                log.exception('Event handler failed: subscriber=%s event_id=%s', subscriber, event_id)
                return
            finally:
                current_context.reset(marker)
        with event_db() as db:
            db.execute('INSERT OR IGNORE INTO deliveries VALUES(?,?)', (subscriber, event_id))

async def run_consumer(subscriber, handlers):
    if os.getenv('REDIS_URL'):
        return await run_redis_consumer(subscriber, handlers)
    while True:
        await consume_once(subscriber, handlers)
        await asyncio.sleep(1)

async def run_redis_consumer(subscriber, handlers):
    from redis.asyncio import Redis
    from redis.exceptions import ResponseError, RedisError
    broker = Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
    stream, consumer, initialized = 'supreme:events', str(uuid.uuid4()), False
    script = """if redis.call('SETNX', KEYS[1], '1') == 1 then
        return redis.call('XADD', KEYS[2], '*', 'body', ARGV[1]) end return ''"""
    try:
        while True:
            try:
                if not initialized:
                    try:
                        await broker.xgroup_create(stream, subscriber, id='0-0', mkstream=True)
                    except ResponseError as exc:
                        if 'BUSYGROUP' not in str(exc):
                            raise
                    initialized = True
                with event_db() as db:
                    db.execute('CREATE TABLE IF NOT EXISTS redis_relay (event_id TEXT PRIMARY KEY)')
                    rows = db.execute('SELECT e.event_id,e.body FROM events e LEFT JOIN redis_relay r ON e.event_id=r.event_id '
                        'WHERE r.event_id IS NULL ORDER BY e.id LIMIT 100').fetchall()
                for event_id, body in rows:
                    await broker.eval(script, 2, 'supreme:event:' + event_id, stream, body)
                    with event_db() as db:
                        db.execute('INSERT OR IGNORE INTO redis_relay VALUES(?)', (event_id,))
                reclaimed = await broker.xautoclaim(stream, subscriber, consumer, min_idle_time=30000, start_id='0-0', count=50)
                messages = list(reclaimed[1])
                incoming = await broker.xreadgroup(subscriber, consumer, {stream:'>'}, count=50, block=1000)
                for _, entries in incoming:
                    messages.extend(entries)
                for message_id, fields in messages:
                    envelope = DomainEvent.model_validate_json(fields['body'])
                    with event_db() as db:
                        db.execute('INSERT OR IGNORE INTO events(event_id,kind,body) VALUES(?,?,?)',
                            (envelope.event_id,envelope.event_type,envelope.model_dump_json()))
                    await consume_once(subscriber, handlers)
                    with event_db() as db:
                        done = db.execute('SELECT 1 FROM deliveries WHERE subscriber=? AND event_id=?',
                                          (subscriber,envelope.event_id)).fetchone()
                    if done:
                        await broker.xack(stream, subscriber, message_id)
            except RedisError:
                log.exception('Redis unavailable; journal and pending deliveries will be retried.')
                initialized = False
                await asyncio.sleep(2)
    finally:
        await broker.aclose()

def start_consumer(app, subscriber, handlers):
    app.state.event_handlers = handlers
    app.state.consumer = asyncio.create_task(run_consumer(subscriber, handlers))

async def stop_consumer(app):
    import contextlib
    if task := getattr(app.state, 'consumer', None):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
