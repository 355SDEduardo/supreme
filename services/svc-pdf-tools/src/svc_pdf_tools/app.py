from fastapi import APIRouter, Depends, FastAPI
from supreme_common.auth_context import AuthMiddleware, enforce_request_context
from supreme_common.uploads import RequestLimitMiddleware
from .main import app as legacy_app

def create_app():
    from contextlib import asynccontextmanager
    from supreme_common.auth_context import secret_key
    @asynccontextmanager
    async def lifespan(app):
        import asyncio
        import contextlib
        import os
        from .housekeeping import cleanup_expired_outputs
        from . import main
        secret_key()
        async def cleanup():
            while True:
                await asyncio.to_thread(cleanup_expired_outputs,main.OUTPUT_DIR,
                    int(os.getenv('PDF_OUTPUT_TTL_SECONDS','7200')))
                await asyncio.sleep(60)
        task=asyncio.create_task(cleanup())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    app = FastAPI(title='svc-pdf-tools', lifespan=lifespan)
    router = APIRouter()
    for route in legacy_app.routes:
        if getattr(route, 'path', '').startswith(('/pdf/', '/api/status')):
            router.routes.append(route)
    app.include_router(router, dependencies=[Depends(enforce_request_context)])
    app.add_middleware(RequestLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'svc-pdf-tools'}
    from pydantic import BaseModel, Field
    class ReportInput(BaseModel):
        title: str = Field(max_length=300)
        lines: list[str] = Field(max_length=500)
    @app.post('/pdf/render-report', dependencies=[Depends(enforce_request_context)])
    def render_report(payload: ReportInput):
        from io import BytesIO
        from xml.sax.saxutils import escape
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from fastapi.responses import Response
        output = BytesIO()
        styles = getSampleStyleSheet()
        story = [Paragraph(escape(payload.title), styles['Title']), Spacer(1, 16)]
        story.extend(Paragraph(escape(line[:2000]), styles['BodyText']) for line in payload.lines)
        SimpleDocTemplate(output).build(story)
        return Response(output.getvalue(), media_type='application/pdf')
    return app

app = create_app()
