from pathlib import Path
import shutil
from uuid import uuid4


def generate_safe_filename(extension: str = ".pdf") -> Path:
    if not extension.startswith("."):
        extension = f".{extension}"
    return Path(f"{uuid4().hex}{extension}")


def ensure_directory(directory: str | Path) -> Path:
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def cleanup_files(*paths: str | Path | None) -> None:
    for item in paths:
        if item is None:
            continue
        path = Path(item)
        try:
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
