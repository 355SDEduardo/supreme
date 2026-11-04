"""Expire only server-named outputs inside the configured output directory."""
from pathlib import Path
import re
import time

def cleanup_expired_outputs(directory: Path, ttl: int = 7200, now: float | None = None):
    directory=directory.resolve()
    cutoff=(time.time() if now is None else now)-ttl
    removed=0
    for path in directory.iterdir():
        if path.is_symlink() or not re.fullmatch(r'[0-9a-f]{32}\.(pdf|zip)',path.name):
            continue
        if path.resolve().parent!=directory:
            continue
        try:
            if path.is_file() and path.stat().st_mtime<cutoff:
                path.unlink()
                removed+=1
        except (PermissionError,FileNotFoundError):
            continue
    return removed
