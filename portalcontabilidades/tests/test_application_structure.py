"""Regression coverage for package isolation and router composition."""
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient

from portalcontabilidades.app import create_app
from portalcontabilidades.core.database import Base
from portalcontabilidades.features.conciliacao.models import BankAccount
from portalcontabilidades.features.documentos.models import Document


def test_feature_imports_preserve_namespaces():
    # A fresh interpreter detects import side effects before pytest has cached models.
    code = """
import importlib
import sys
original_path = sys.path.copy()
for name in ('documentos', 'conciliacao', 'multiempresa', 'seguranca', 'obrigacoes'):
    importlib.import_module(f'portalcontabilidades.features.{name}.router')
assert sys.path == original_path
assert not {'models', 'schemas', 'service'} & set(sys.modules)
"""
    source_dir = Path(__file__).resolve().parents[1] / "src"
    result = subprocess.run(
        [sys.executable, "-W", "error::sqlalchemy.exc.SAWarning", "-c", code],
        cwd=source_dir,
        env={**os.environ, "PYTHONPATH": str(source_dir)},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert BankAccount.metadata is Document.metadata is Base.metadata
    assert Document.__module__ != BankAccount.__module__


def test_repeated_startup_preserves_model_registration(database_engine):
    original_mappers = set(Base.registry.mappers)
    for _ in range(2):
        with TestClient(create_app(database_engine=database_engine)) as client:
            assert client.get("/").status_code == 200
            assert len(client.get("/").json()["features_loaded"]) == 10
    assert set(Base.registry.mappers) == original_mappers


def test_certificate_routes_are_registered(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/certificates/vault/upload" in paths
    assert "/certificates/expirations" in paths
    response = client.get("/certificates/expirations")
    assert response.status_code == 200
    assert response.json() == []


def test_legacy_entrypoint_exports_application():
    from main import app as legacy_app
    from portalcontabilidades.app import app

    assert legacy_app is app
