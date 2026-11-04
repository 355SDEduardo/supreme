"""Reproduce the initial source extraction without touching legacy trees or data.

Intended for migration auditing, not as a runtime dependency. Existing destinations
are never overwritten. All services import their own extracted packages.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SERVICES = [
    ('security-iam', 'seguranca', 10), ('companies', 'multiempresa', 9),
    ('obligations', 'obrigacoes', 1), ('documents', 'documentos', 2),
    ('pdf-tools', None, 0), ('nfse-engine', None, 0), ('nfe-difal', None, 0),
    ('federal-tax-audit', None, 0), ('bank-reconciliation', 'conciliacao', 3),
    ('finance-bpo', 'financeiro', 4), ('fiscal-gov', 'integracoes_fiscais', 5),
    ('client-portal', 'portal_cliente', 6), ('analytics-dre', 'analytics', 7),
    ('accounting-ai', 'automacao_ia', 8),
]
MANIFEST = []

def write(path, content):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding='utf-8')

def copy(source, dest, replacements=()):
    source, dest = ROOT / source, ROOT / dest
    items = [source] if source.is_file() else source.rglob('*')
    for item in items:
        if not item.is_file() or item.suffix in {'.pyc', '.pdf', '.txt'} or '__pycache__' in item.parts:
            continue
        target = dest if source.is_file() else dest / item.relative_to(source)
        if item.suffix not in {'.py', '.js', '.cjs', '.html', '.css', '.xml'}:
            continue
        content = item.read_text(encoding='utf-8-sig')
        for before, after in replacements:
            content = content.replace(before, after)
        write(target, content)
        MANIFEST.append({'source': item.relative_to(ROOT).as_posix(), 'destination': target.relative_to(ROOT).as_posix()})

def main():
    for index, (slug, domain, number) in enumerate(SERVICES, 1):
        name = 'svc-' + slug
        package = name.replace('-', '_')
        base = Path('services') / name
        src = base / 'src' / package
        write(src / '__init__.py', '')
        deps = ['supreme-common', 'fastapi>=0.115,<1', 'uvicorn>=0.30,<1', 'pydantic>=2.8,<3', 'python-multipart>=0.0.9']
        if domain:
            replacements = [('portalcontabilidades.core.database', package + '.database'),
                            ('portalcontabilidades.core.config', package + '.config'),
                            ('portalcontabilidades.core.security', 'supreme_common.auth_context'),
                            ('portalcontabilidades.core.tax_ids', 'supreme_common.tax_ids')]
            copy(f'portalcontabilidades/src/portalcontabilidades/features/{domain}', src, replacements)
            copy(f'portalcontabilidades/tests/features/test_feature_{number:02}.py', base / 'tests' / f'test_feature_{number:02}.py',
                 [(f'portalcontabilidades.features.{domain}', package)])
            deps += ['sqlalchemy>=2,<3', 'httpx>=0.27,<1']
            if slug == 'security-iam': deps += ['cryptography>=42', 'pyotp>=2.9']
            if slug == 'analytics-dre': deps += ['reportlab>=4']
            write(src / 'database.py', f'''from sqlalchemy.orm import declarative_base
from supreme_common.database import request_db
Base = declarative_base()
def get_db():
    yield from request_db()
''')
            write(src / 'config.py', f'''import os
from types import SimpleNamespace
settings = SimpleNamespace(
    STORAGE_DIR=os.getenv('DOCUMENT_UPLOADS_DIR', './data/storage/uploads'),
    MASTER_ENCRYPTION_KEY=os.getenv('MASTER_ENCRYPTION_KEY', ''),
)
''')
            routers = 'router, cert_router' if slug == 'security-iam' else 'router'
            write(src / 'app.py', f'''from supreme_common.application import domain_app
from .database import Base
from .router import {routers}
def create_app(**kwargs):
    return domain_app('{name}', Base, [{routers}], **kwargs)
app = create_app()
''')
            write(base / 'tests' / 'conftest.py', f'''import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from {package}.database import Base
from {package} import models
@pytest.fixture
def database_engine():
    engine = create_engine('sqlite://', connect_args={{'check_same_thread': False}}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
@pytest.fixture
def db_session(database_engine):
    with Session(database_engine) as session:
        yield session
''')
        if slug == 'pdf-tools':
            copy('pdf/app', src, [('from app.', f'from {package}.')])
            copy('pdf/tests', base / 'tests', [('from app.', f'from {package}.')])
            deps += ['pypdf>=6.8', 'pymupdf>=1.28', 'reportlab>=4', 'pikepdf>=8']
        if slug == 'nfse-engine':
            copy('nfse/app', src, [('from app.', f'from {package}.')])
            for path in (ROOT / 'st_difal_web/core').glob('nfse_*.py'):
                copy(path.relative_to(ROOT), src / 'multilayout' / path.name)
            write(src / 'multilayout/__init__.py', '')
            copy('nfse/tests', base / 'tests/strict', [('from app.', f'from {package}.')])
            copy('nfse/data/samples', src / 'samples')
            deps += ['lxml>=4.9', 'openpyxl>=3.1']
        if slug == 'nfe-difal':
            copy('st_difal_web/core', src / 'core')
            for path in (ROOT / 'st_difal_web/tests').glob('*'):
                if path.name.startswith(('test_core', 'test_zip_comparison.py', 'test_zip_extractor.py')) or path.name in {'sample_data.py', '__init__.py'}:
                    copy(path.relative_to(ROOT), base / 'tests' / path.name, [('from core.', f'from {package}.core.')])
            deps += ['openpyxl>=3.1', 'pymupdf>=1.28', 'pypdf>=6.8']
        if slug == 'federal-tax-audit':
            copy('audit/tools', src / 'tools', [('from audit_engine', 'from .audit_engine'), ('from agent_tools', 'from .agent_tools')])
            copy('audit/server/app.py', src / 'legacy_api.py')
            deps += ['pymupdf>=1.28', 'httpx>=0.27']
        deps_literal = ',\n    '.join(json.dumps(d) for d in deps)
        write(base / 'pyproject.toml', f'''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[project]
name = "{name}"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
    {deps_literal}
]
[tool.uv.sources]
supreme-common = {{ workspace = true }}
[tool.setuptools.packages.find]
where = ["src"]
[tool.setuptools.package-data]
"*" = ["static/**/*", "samples/*.xml"]
[tool.pytest.ini_options]
testpaths = ["tests"]
''')
        write(base / 'Dockerfile', f'''FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY libs/supreme_common /build/common
COPY services/{name} /build/service
RUN pip install --no-cache-dir /build/common /build/service && useradd --create-home supreme && mkdir /data && chown supreme /data
USER supreme
EXPOSE {8000 + index}
CMD ["uvicorn", "{package}.app:app", "--host", "0.0.0.0", "--port", "{8000 + index}"]
''')
        write(base / 'README.md', f'''# {name}

Serviço MS-{index:02}, porta {8000 + index}. Execute na raiz: `uv run uvicorn {package}.app:app --port {8000 + index}`.

`GET /health` verifica o processo; `/docs` descreve os contratos. Rotas privadas exigem JWT emitido pelo IAM. O banco e armazenamento são privados; consulte a configuração e os fluxos no README da raiz.

Teste isolado: `uv run pytest {base.as_posix()}/tests -q`.
''')
    copy('portalcontabilidades/src/portalcontabilidades/core/tax_ids.py', 'libs/supreme_common/src/supreme_common/tax_ids.py')
    for source, target in [('audit/web','tax-audit'), ('nfse/static','nfse-intelligence'), ('pdf/app/static','pdf-tools'), ('portalcontabilidades/src/portalcontabilidades/static','portal-contabil')]:
        copy(source, 'frontend/modules/' + target)
    write('docs/migration/source-map.json', json.dumps(MANIFEST, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
