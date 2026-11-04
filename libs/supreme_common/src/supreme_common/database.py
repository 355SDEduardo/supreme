"""Per-application engines and enforced tenant criteria. No shared domain metadata."""
from sqlalchemy import Column, String, Text, Table, create_engine, event
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria
from fastapi import HTTPException, Request
from .auth_context import current_context

def request_db():
    # Provided by the application's dependency override (the function is a stable marker).
    raise RuntimeError('Database dependency not configured.')
    yield

def configure_database(app, base, database_url=None, database_engine=None):
    import os
    from pathlib import Path
    slug = app.title
    path = Path(os.getenv('DB_ROOT_DIR', './data/db'))
    path.mkdir(parents=True, exist_ok=True)
    url = database_url or os.getenv('DATABASE_URL') or f'sqlite:///{(path / (slug + ".db")).as_posix()}'
    engine = database_engine or create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    classes = [mapper.class_ for mapper in base.registry.mappers]
    outbox = base.metadata.tables.get('supreme_outbox')
    if outbox is None:
        outbox = Table('supreme_outbox', base.metadata, Column('id', String(100), primary_key=True), Column('body', Text, nullable=False))
    app.state.outbox = outbox
    organization_only = slug == 'svc-companies'
    for cls in classes:
        if not hasattr(cls, 'organization_id'):
            cls.organization_id = Column(String(100), nullable=True, index=True)
        if not organization_only and cls.__tablename__ not in {'tax_obligations', 'chart_of_accounts', 'iam_users'} and not hasattr(cls, 'company_id'):
            cls.company_id = Column(String(100), nullable=True, index=True)

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
