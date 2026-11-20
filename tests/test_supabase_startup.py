"""Reject mixed fiscal persistence before accepting HTTP traffic."""
from __future__ import annotations

from importlib import import_module
from unittest.mock import AsyncMock

import pytest


@pytest.mark.parametrize('package', ['svc_nfse_engine', 'svc_federal_tax_audit'])
@pytest.mark.parametrize('storage', ['local', 'supabase'])
async def test_remote_fiscal_startup_requires_configured_supabase_storage(monkeypatch, package, storage):
    monkeypatch.setenv('SUPREME_DATABASE_MODE', 'supabase')
    monkeypatch.setenv('SUPREME_STORAGE_MODE', storage)
    if package == 'svc_federal_tax_audit':
        events = import_module(package + '.events')
        monkeypatch.setattr(events, 'start', AsyncMock())
        monkeypatch.setattr(events, 'stop', AsyncMock())
    app = import_module(package + '.app').create_app()
    with pytest.raises(RuntimeError, match='Storage'):
        async with app.router.lifespan_context(app):
            pass
