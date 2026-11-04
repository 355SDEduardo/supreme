"""Transactional outbox for document engines that use SQLite directly."""
import asyncio
import os
from pathlib import Path
import sqlite3
from .events import DomainEvent, make_event, publish_envelope

def enqueue(db, kind, payload, event_id):
    db.execute('CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, body TEXT)')
    event = make_event(kind, payload, event_id)
    db.execute('INSERT OR IGNORE INTO outbox VALUES(?,?)', (event.event_id, event.model_dump_json()))

def drain(service):
    root = Path(os.getenv('STORAGE_ROOT_DIR', './data/storage')) / service
    for path in root.glob('*/*/state.db'):
        with sqlite3.connect(path, timeout=30) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='outbox'").fetchone()
            if not exists:
                continue
            for event_id, body in db.execute('SELECT id,body FROM outbox LIMIT 100').fetchall():
                publish_envelope(DomainEvent.model_validate_json(body))
                db.execute('DELETE FROM outbox WHERE id=?', (event_id,))

async def run(service):
    while True:
        await asyncio.to_thread(drain, service)
        await asyncio.sleep(0.5)
