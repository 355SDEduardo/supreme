"""Per-application engines and enforced tenant criteria. No shared domain metadata."""
from __future__ import annotations

from sqlalchemy import Column, String, Text, Table, event, inspect
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria
from fastapi import HTTPException
from .auth_context import current_context

def request_db():
    # Provided by the application's dependency override (the function is a stable marker).
    raise RuntimeError('Database dependency not configured.')
    yield

def prepare_metadata(base, slug: str):
    """Apply the same infrastructure columns to runtime and deployment DDL."""
    classes = [mapper.class_ for mapper in base.registry.mappers]
    outbox = base.metadata.tables.get('supreme_outbox')
    if outbox is None:
        outbox = Table('supreme_outbox', base.metadata, Column('id', String(100), primary_key=True), Column('body', Text, nullable=False))
    organization_only = slug == 'svc-companies'
    for cls in classes:
        if not hasattr(cls, 'organization_id'):
            cls.organization_id = Column(String(100), nullable=True, index=True)
        if not organization_only and cls.__tablename__ not in {'tax_obligations', 'chart_of_accounts', 'iam_users'} and not hasattr(cls, 'company_id'):
            cls.company_id = Column(String(100), nullable=True, index=True)
    return classes, outbox


def initialize_database(app, base) -> None:
    engine = app.state.engine
    options = engine.get_execution_options()
    if not options.get('supreme_managed_schema'):
        base.metadata.create_all(engine)
        return
    schema = options.get('schema_translate_map', {}).get(None)
    inspector = inspect(engine)
    present = set(inspector.get_table_names(schema=schema))
    for table in base.metadata.tables.values():
        if table.name not in present:
            raise RuntimeError('Schema incompleto: aplique as migrações Supabase antes de iniciar o serviço.')
        columns = {col['name'] for col in inspector.get_columns(table.name, schema=schema)}
        if not set(table.columns.keys()).issubset(columns):
            raise RuntimeError('Colunas ausentes: aplique as migrações Supabase antes de iniciar o serviço.')


def configure_database(app, base, database_url=None, database_engine=None):
    from .supabase_database import create_service_engine
    slug = app.title
    engine = database_engine if database_engine is not None else create_service_engine(slug, database_url)
    classes, outbox = prepare_metadata(base, slug)
    app.state.outbox = outbox
    organization_only = slug == 'svc-companies'

    class TenantSession(Session):
        pass

    @event.listens_for(TenantSession, 'do_orm_execute')
    def scope_query(state):
        claims = current_context.get()
        if not claims:
            return
        org, company = claims['organization_id'], claims.get('company_id')
        if state.is_select:
            for cls in classes:
                state.statement = state.statement.options(with_loader_criteria(cls, cls.organization_id == org, include_aliases=True))
                if not organization_only and hasattr(cls, 'company_id'):
                    state.statement = state.statement.options(with_loader_criteria(cls, cls.company_id == company, include_aliases=True))
                if organization_only and cls.__tablename__ == 'companies' and claims.get('role') not in {'super_admin','supervisor','service'}:
                    state.statement = state.statement.options(with_loader_criteria(cls, cls.id.in_(claims.get('company_ids', [])), include_aliases=True))
        elif state.is_update or state.is_delete:
            # Bulk mutations bypass before_flush and are deliberately unavailable to HTTP handlers.
            raise HTTPException(403, 'Use alterações por recurso para preservar o isolamento.')

    @event.listens_for(TenantSession, 'before_flush')
    def scope_writes(session, *_):
        claims = current_context.get()
        if not claims:
            return
        for row in session.new | session.dirty | session.deleted:
            for key, expected in [('organization_id', claims['organization_id'])] + ([] if organization_only else [('company_id', claims.get('company_id'))]):
                if not hasattr(type(row), key):
                    continue
                value = getattr(row, key)
                if value and value != expected:
                    raise HTTPException(403, 'Recurso pertence a outro contexto.')
                setattr(row, key, expected)

    @event.listens_for(TenantSession, 'after_flush')
    def record_events(session, *_):
        import json
        from .events import make_event
        if not current_context.get():
            return
        kinds = {'PayableReceivableBill': 'BillChanged', 'Document': 'DocumentUploaded',
                 'BankStatement': 'BankStatementImported', 'Reconciliation': 'ReconciliationChanged',
                 'Task': 'TaskChanged', 'DocumentChecklistItem':'ChecklistItemChanged',
                 'BankTransaction':'BankTransactionChanged'}
        for row in session.new | session.dirty:
            kind = kinds.get(type(row).__name__)
            if kind:
                data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
                # Binary custody stays private; only reference metadata crosses services.
                data.pop('storage_path', None)
                envelope = make_event(kind, {'resource': json.loads(json.dumps(data, default=str))})
                session.connection().execute(outbox.insert().values(id=envelope.event_id, body=envelope.model_dump_json()))

    factory = sessionmaker(engine, class_=TenantSession, expire_on_commit=False)
    app.state.engine, app.state.sessions = engine, factory
    return engine

def db_dependency(app):
    def get_db():
        with app.state.sessions() as session:
            yield session
    return get_db
