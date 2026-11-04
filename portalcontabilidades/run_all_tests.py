"""Run pytest with the active interpreter, on Windows, Linux, or macOS."""
from pathlib import Path
import subprocess
import sys
from typing import Sequence

BASE_DIR = Path(__file__).resolve().parent


def run_suite(args: Sequence[str] = ()) -> int:
    """Discover tests automatically and preserve pytest's exit code/output."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=BASE_DIR,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(run_suite(sys.argv[1:]))
