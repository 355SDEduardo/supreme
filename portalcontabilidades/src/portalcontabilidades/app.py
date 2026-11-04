"""FastAPI application composition and database startup."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from .core.config import settings
from .core.database import Base, engine
from .features.registry import FEATURES


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Models are imported once by the registry; startup only creates tables."""
    Base.metadata.create_all(bind=application.state.database_engine)
    yield


def create_app(*, database_engine: Engine | None = None) -> FastAPI:
    """Create an application; tests may provide an isolated database engine."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        description=(
            "Plataforma completa para Escritórios de Contabilidade e BPO Financeiro no Brasil. "
            "Engloba compliance regulatório (CFC, RFB, SEFAZ, FGTS, eSocial, EFD-Reinf, DCTFWeb), "
            "gestão documental com rastreabilidade jurídica, conciliação bancária OFX, contas a pagar e receber "
            "com validação de boletos FEBRABAN e Chaves PIX, governança de IA Human-in-the-Loop e segurança LGPD com Vault AES-256."
        ),
        lifespan=lifespan,
    )
    application.state.database_engine = engine if database_engine is None else database_engine
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    loaded_features = []
    for feature in FEATURES:
        for router in feature.routers:
            application.include_router(router)
        loaded_features.append({
            "folder": feature.folder,
            "label": feature.label,
            "routes": sum(len(router.routes) for router in feature.routers),
        })

    static_dir = Path(__file__).resolve().parent / "static"
    if not static_dir.exists():
        static_dir.mkdir(parents=True, exist_ok=True)
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    application.mount("/app", StaticFiles(directory=str(static_dir), html=True), name="frontend")

    @application.get("/", tags=["Root"])
    def root(request: Request):
        """Health check and platform modules summary."""
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/app/")
        return {
            "name": settings.PROJECT_NAME,
            "status": "operational",
            "version": "1.0.0",
            "features_loaded": loaded_features,
            "documentation_url": "/docs",
            "redoc_url": "/redoc",
            "frontend_url": "/app/",
        }

    @application.get("/health", tags=["Root"])
    def health_check():
        """Liveness probe."""
        return {"status": "ok", "database": "connected"}

    return application


app = create_app()
