from __future__ import annotations

from scripts.supabase_schema import DESTINATION, domain_metadata, generate_sql


def test_initial_migration_matches_runtime_metadata_and_preserves_service_boundaries():
    generated = generate_sql()
    assert DESTINATION.read_text(encoding="utf-8") == generated
    metadata = domain_metadata()
    assert "companies.portfolio_resources" in metadata["companies"].tables
    assert "reconciliation.pluggy_configurations" in metadata["reconciliation"].tables
    for schema, domain in metadata.items():
        for table in domain.tables.values():
            assert table.schema == schema
            for fk in table.foreign_keys:
                assert fk.column.table.schema == schema
            if schema != "events" and table.name != "supreme_outbox":
                assert "organization_id" in table.c
        if schema != "events":
            assert f"{schema}.supreme_outbox" in domain.tables
    assert "raw_user_meta_data" not in generated
    assert "auth.users" not in generated
    assert "CREATE DATABASE" not in generated


def test_migration_sequence_covers_current_models():
    from scripts.supabase_schema import migration_gaps
    assert migration_gaps() == []


def test_database_roles_have_no_browser_grants_or_schema_creation_privileges():
    sql = generate_sql()
    assert "GRANT ALL" not in sql
    assert "GRANT CREATE" not in sql
    assert "TO authenticated" not in sql
    assert "TO anon" not in sql
    assert "REVOKE UPDATE, DELETE ON iam.audit_logs" in sql
    assert "NOBYPASSRLS" in sql
