from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from core.models import ProcessingState


@dataclass
class _Entry:
    state: ProcessingState = field(default_factory=ProcessingState)
    touched_at: float = field(default_factory=time.monotonic)


class SessionStore:
    def __init__(self, *, ttl_seconds: int = 7200, max_sessions: int = 100):
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.RLock()

    def create_id(self) -> str:
        return secrets.token_urlsafe(24)

    def get(self, session_id: str) -> ProcessingState:
        with self._lock:
            self._cleanup()
            entry = self._entries.setdefault(session_id, _Entry())
            entry.touched_at = time.monotonic()
            return entry.state

    def replace(self, session_id: str, state: ProcessingState) -> None:
        with self._lock:
            self._cleanup()
            self._entries[session_id] = _Entry(state=state)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._entries.pop(session_id, None)

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.touched_at > self._ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)

        overflow = len(self._entries) - self._max_sessions
        if overflow > 0:
            oldest = sorted(
                self._entries, key=lambda key: self._entries[key].touched_at
            )[:overflow]
            for key in oldest:
                self._entries.pop(key, None)
