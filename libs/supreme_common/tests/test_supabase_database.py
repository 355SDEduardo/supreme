from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool


def test_supabase_transaction_pool_qualifies_schema_and_disables_prepared_statements(monkeypatch):
    from supreme_common.supabase_database import engine_configuration

    monkeypatch.setenv(
        "SUPABASE_DB_URL", "postgresql://postgres.demo:synthetic@localhost:6543/postgres?sslmode=require"
    )
    url, options = engine_configuration("svc-bank-reconciliation")
    assert url.drivername == "postgresql+psycopg"
    assert options["execution_options"]["schema_translate_map"] == {None: "reconciliation"}
    assert options["connect_args"]["prepare_threshold"] is None
    assert options["poolclass"] is NullPool
    assert options["hide_parameters"] is True


def test_session_pool_is_bounded_and_service_url_takes_precedence(monkeypatch):
    from supreme_common.supabase_database import engine_configuration

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://postgres:synthetic@localhost/postgres")
    monkeypatch.setenv(
        "SUPABASE_FINANCE_DB_URL", "postgresql://supreme_finance.demo:synthetic@localhost/postgres"
    )
    url, options = engine_configuration("svc-finance-bpo")
    assert url.username == "supreme_finance.demo"
    assert options["pool_size"] == 2
    assert options["max_overflow"] == 1
    assert options["execution_options"]["schema_translate_map"] == {None: "finance"}


def test_explicit_sqlite_keeps_local_tests_isolated(monkeypatch):
    from supreme_common.supabase_database import engine_configuration

    monkeypatch.setenv("SUPABASE_DB_URL", "invalid-remote-url")
    url, options = engine_configuration("svc-companies", "sqlite://")
    assert url.drivername == "sqlite"
    assert "execution_options" not in options


@pytest.mark.parametrize(
    "service,url",
    [
        ("unknown-service", "postgresql://postgres:synthetic@localhost/postgres"),
        ("svc-companies", "sqlite:///wrong.db"),
        ("svc-companies", "postgresql+psycopg2://postgres:synthetic@localhost/postgres"),
    ],
)
def test_invalid_supabase_configuration_fails_without_exposing_url(monkeypatch, service, url):
    from supreme_common.supabase_database import engine_configuration

    monkeypatch.setenv("SUPABASE_DB_URL", url)
    with pytest.raises(ValueError) as error:
        engine_configuration(service)
    assert "synthetic" not in str(error.value)


def test_production_requires_service_role_and_tls(monkeypatch):
    from supreme_common.supabase_database import engine_configuration

    monkeypatch.setenv("SUPREME_ENV", "production")
    monkeypatch.setenv(
        "SUPABASE_DB_URL", "postgresql://postgres.demo:synthetic@localhost/postgres?sslmode=require"
    )
    with pytest.raises(ValueError, match="credencial"):
        engine_configuration("svc-companies")
    monkeypatch.setenv(
        "SUPABASE_COMPANIES_DB_URL",
        "postgresql://supreme_companies.demo:synthetic@localhost/postgres?sslmode=disable",
    )
    with pytest.raises(ValueError, match="TLS"):
        engine_configuration("svc-companies")


def test_managed_schema_startup_checks_missing_columns_without_creating_tables():
    from supreme_common.database import initialize_database

    base = declarative_base()

    class Row(base):
        __tablename__ = "existing"
        id = Column(String, primary_key=True)
        required = Column(String)

    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.exec_driver_sql("CREATE TABLE existing (id VARCHAR PRIMARY KEY)")
    app = SimpleNamespace(state=SimpleNamespace(engine=engine.execution_options(supreme_managed_schema=True)))
    with pytest.raises(RuntimeError, match="migra"):
        initialize_database(app, base)
    from sqlalchemy import inspect

    assert [col["name"] for col in inspect(engine).get_columns("existing")] == ["id"]


def test_runner_only_passes_own_database_and_journal_credentials():
    from scripts.dev_runner import service_environment

    environment = {
        "SUPREME_DATABASE_MODE": "supabase",
        "SUPABASE_IAM_DB_URL": "private-iam",
        "SUPABASE_FINANCE_DB_URL": "private-finance",
        "SUPABASE_EVENTS_DB_URL": "private-events",
        "SECRET_KEY": "shared-auth-secret",
        "DATABASE_URL": "legacy-url",
    }
    finance = service_environment("finance-bpo", environment)
    assert "SUPABASE_IAM_DB_URL" not in finance
    assert finance["SUPABASE_FINANCE_DB_URL"] == "private-finance"
    assert finance["SUPABASE_EVENTS_DB_URL"] == "private-events"
    gateway = service_environment("gateway", environment)
    assert not any(key.endswith("DB_URL") or key == "DATABASE_URL" for key in gateway)
    assert gateway["SECRET_KEY"] == "shared-auth-secret"


def test_runner_never_distributes_generic_database_credentials():
    from scripts.dev_runner import service_environment
    from scripts.service_catalog import SERVICES
    from supreme_common.supabase_database import SERVICE_SCHEMAS

    environment = {
        "DATABASE_URL": "synthetic-admin-credential",
        "SUPABASE_DB_URL": "synthetic-shared-credential",
        "SUPABASE_EVENTS_DB_URL": "synthetic-events-credential",
        **{f"SUPABASE_{schema.upper()}_DB_URL": f"synthetic-{schema}"
           for schema in (*SERVICE_SCHEMAS.values(), "nfse", "nfe", "tax_audit")},
    }
    for slug in [*(item[0] for item in SERVICES), "gateway"]:
        scoped = service_environment(slug, environment)
        assert "DATABASE_URL" not in scoped, slug
        assert "SUPABASE_DB_URL" not in scoped, slug
    assert environment["DATABASE_URL"] == "synthetic-admin-credential"


@pytest.mark.parametrize("url,expected", [
    ("postgresql://postgres:synthetic@localhost/postgres?sslmode=require", "credencial"),
    ("postgresql://supreme_companies:synthetic@localhost/postgres", "TLS"),
    ("postgresql://supreme_companies:synthetic@localhost/postgres?sslmode=require", None),
])
def test_explicit_postgres_cannot_bypass_managed_schema_safety(monkeypatch, url, expected):
    from supreme_common.supabase_database import engine_configuration

    monkeypatch.setenv("SUPREME_DATABASE_MODE", "supabase")
    monkeypatch.setenv("SUPREME_ENV", "production")
    if expected:
        with pytest.raises(ValueError, match=expected):
            engine_configuration("svc-companies", url)
    else:
        target, options = engine_configuration("svc-companies", url)
        assert target.drivername == "postgresql+psycopg"
        assert options["execution_options"]["supreme_managed_schema"] is True
        assert options["execution_options"]["schema_translate_map"] == {None: "companies"}
