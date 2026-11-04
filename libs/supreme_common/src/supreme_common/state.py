"""Transactional state shared by workers of one service, partitioned by tenant."""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
from .auth_context import context, tenant_path

@contextmanager
def tenant_database(service):
    root = Path(os.getenv('STORAGE_ROOT_DIR', './data/storage')) / service
    path = tenant_path(root) / 'state.db'
    with sqlite3.connect(path, timeout=30) as connection:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('BEGIN IMMEDIATE')
        yield connection

def tenant_key():
    claims = context()
    return claims['organization_id'] + ':' + claims.get('company_id', '')
