"""Private, bounded in-memory workspaces for the interactive importer."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import sqlite3
from threading import RLock
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException, Request
from supreme_common.auth_context import context


current_workspace = ContextVar('nfse_workspace', default=None)
TTL_SECONDS = 7200
MAX_WORKSPACES = 16


@dataclass
class Workspace:
    owner: tuple
    connection: sqlite3.Connection = field(
        default_factory=lambda: sqlite3.connect(':memory:', check_same_thread=False))
    lock: RLock = field(default_factory=RLock)
    touched: float = field(default_factory=monotonic)
    active: int = 0

    @contextmanager
    def database(self):
        with self.lock, self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            yield self.connection


def owner():
    claims = context()
    return (claims['organization_id'], claims['company_id'], claims['sub'])


class Workspaces:
    def __init__(self):
        self.items = {}
        self.lock = RLock()

    def create(self):
        with self.lock:
            self.expire()
            if len(self.items) >= MAX_WORKSPACES:
                raise HTTPException(503, 'Limite de sessões NFS-e atingido. Tente novamente mais tarde.')
            key = str(uuid4())
            self.items[key] = Workspace(owner())
            return key

    def expire(self):
        with self.lock:
            for key, workspace in list(self.items.items()):
                if not workspace.active and monotonic() - workspace.touched > TTL_SECONDS:
                    with workspace.lock:
                        workspace.connection.close()
                        del self.items[key]

    def get(self, key):
        with self.lock:
            self.expire()
            workspace = self.items.get(key)
            if workspace is None or workspace.owner != owner():
                raise HTTPException(410, 'Sessão NFS-e encerrada. Reabra o módulo e importe os arquivos novamente.')
            workspace.touched = monotonic()
            return workspace

    def delete(self, key):
        with self.lock:
            workspace = self.get(key)
            if workspace.active:
                raise HTTPException(409, 'Há uma operação NFS-e em andamento. Aguarde sua conclusão.')
            with workspace.lock:
                workspace.connection.close()
                del self.items[key]

    def close(self):
        with self.lock:
            for workspace in self.items.values():
                with workspace.lock:
                    workspace.connection.close()
            self.items.clear()


async def workspace_context(request: Request):
    key = request.query_params.get('workspace')
    registry = request.app.state.workspaces
    with registry.lock:
        workspace = registry.get(key) if key is not None else None
        if workspace:
            workspace.active += 1
    marker = current_workspace.set(workspace)
    try:
        yield
    finally:
        current_workspace.reset(marker)
        if workspace:
            with registry.lock:
                workspace.active -= 1
                workspace.touched = monotonic()
