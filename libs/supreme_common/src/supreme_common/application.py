from contextlib import asynccontextmanager
from importlib import import_module
from fastapi import Depends, FastAPI
from .auth_context import AuthMiddleware, enforce_request_context, secret_key
from .database import configure_database, db_dependency
from .uploads import RequestLimitMiddleware

def domain_app(name, base, routers, *, database_url=None, database_engine=None):
    package = name.replace('-', '_')
    @asynccontextmanager
    async def lifespan(app):
        secret_key()
        try:
            events = import_module(package + '.events')
        except ModuleNotFoundError as exc:
            if exc.name != package + '.events':
                raise
            events = None
        configure_database(app, base, database_url, database_engine)
        base.metadata.create_all(app.state.engine)
        import asyncio
        from .events import outbox_loop
        app.state.outbox_task = asyncio.create_task(outbox_loop(app))
        try:
            if events and hasattr(events, 'start'):
                await events.start(app)
            yield
        finally:
            import contextlib
            app.state.outbox_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app.state.outbox_task
            if events and hasattr(events, 'stop'):
                await events.stop(app)
            app.state.engine.dispose()
    app = FastAPI(title=name, lifespan=lifespan)
    public = {'/security/auth/token', '/security/auth/mfa-login'} if name == 'svc-security-iam' else set()
    app.add_middleware(AuthMiddleware, public=public)
    app.add_middleware(RequestLimitMiddleware)
    for router in routers:
        app.include_router(router, dependencies=[Depends(enforce_request_context)])
    module = import_module(package + '.database')
    app.dependency_overrides[module.get_db] = db_dependency(app)
    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': name}
    return app
