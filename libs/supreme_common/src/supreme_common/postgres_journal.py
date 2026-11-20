"""PostgreSQL event journal: durable insert, bounded reads and acknowledgement after delivery."""

from __future__ import annotations

from functools import lru_cache
import os

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from .supabase_database import postgres_configuration

metadata = MetaData(schema="events")
events = Table(
    "events",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("event_id", String(100), nullable=False, unique=True),
    Column("kind", String(100), nullable=False),
    Column("body", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
deliveries = Table(
    "deliveries",
    metadata,
    Column("subscriber", String(100), primary_key=True),
    Column("event_id", String(100), primary_key=True),
    Column("delivered_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


def journal_url() -> str | None:
    url = os.getenv("SUPABASE_EVENTS_DB_URL") or os.getenv("SUPABASE_DB_URL")
    if not url and (
        os.getenv("SUPREME_DATABASE_MODE") == "supabase"
        or any(
            key.startswith("SUPABASE_") and key.endswith("_DB_URL") and value
            for key, value in os.environ.items()
        )
    ):
        raise ValueError("Configure SUPABASE_EVENTS_DB_URL para o journal durável no Supabase.")
    if url and os.getenv("REDIS_URL"):
        raise ValueError("Use o journal Supabase ou Redis; remova REDIS_URL no modo Supabase.")
    return url


class PostgresJournal:
    def __init__(self, engine):
        self.engine = engine

    def publish(self, envelope) -> None:
        with self.engine.begin() as db:
            db.execute(
                insert(events)
                .values(
                    event_id=envelope.event_id,
                    kind=envelope.event_type,
                    body=envelope.model_dump(mode="json"),
                )
                .on_conflict_do_nothing(index_elements=[events.c.event_id])
            )

    def pending(self, subscriber: str) -> list[tuple[str, dict]]:
        delivered = (
            select(deliveries.c.event_id)
            .where(
                deliveries.c.subscriber == subscriber,
                deliveries.c.event_id == events.c.event_id,
            )
            .exists()
        )
        with self.engine.connect() as db:
            return [
                (row.event_id, row.body)
                for row in db.execute(
                    select(events.c.event_id, events.c.body)
                    .where(~delivered)
                    .order_by(events.c.id)
                    .limit(100)
                )
            ]

    def acknowledge(self, subscriber: str, event_id: str) -> None:
        with self.engine.begin() as db:
            db.execute(
                insert(deliveries)
                .values(subscriber=subscriber, event_id=event_id)
                .on_conflict_do_nothing(index_elements=[deliveries.c.subscriber, deliveries.c.event_id])
            )


@lru_cache(maxsize=1)
def journal(raw_url: str) -> PostgresJournal:
    url, options = postgres_configuration(raw_url, "events")
    # Each service process has a journal client; do not retain another backend connection.
    from sqlalchemy.pool import NullPool

    for key in ("pool_size", "max_overflow", "pool_timeout", "pool_recycle"):
        options.pop(key, None)
    options["poolclass"] = NullPool
    return PostgresJournal(create_engine(url, **options))
