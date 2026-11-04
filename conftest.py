"""All automated checks use disposable state and explicit test-only secrets."""
import os
import sys
import pytest

os.environ.setdefault('SECRET_KEY', 'test-only-key-that-is-longer-than-thirty-two-characters')
os.environ.setdefault('MASTER_ENCRYPTION_KEY', '12' * 32)

@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'test-only-key-that-is-longer-than-thirty-two-characters')
    monkeypatch.setenv('MASTER_ENCRYPTION_KEY', '12' * 32)
    monkeypatch.setenv('REDIS_URL', '')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    for name, relative in {'DB_ROOT_DIR':'db','STORAGE_ROOT_DIR':'storage','DOCUMENT_UPLOADS_DIR':'uploads',
        'PDF_OUTPUTS_DIR':'pdf','TAX_AUDIT_WORKSPACES_DIR':'audit','EVENT_DB_PATH':'events/events.db',
        'NFE_FISCAL_CATALOG_PATH':'nfe/fiscal_data.json'}.items():
        monkeypatch.setenv(name, str(tmp_path/relative))
    if module := sys.modules.get('svc_documents.config'):
        monkeypatch.setattr(module.settings, 'STORAGE_DIR', str(tmp_path/'uploads'))
    if module := sys.modules.get('svc_pdf_tools.main'):
        pdf_output = tmp_path.parent / (tmp_path.name + '-pdf-output')
        pdf_output.mkdir(exist_ok=True)
        monkeypatch.setattr(module, 'OUTPUT_DIR', pdf_output)
