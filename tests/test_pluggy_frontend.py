from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def test_pluggy_frontend_behaviors() -> None:
    node = shutil.which("node")
    assert node, "Node.js é necessário para validar a interface Pluggy."
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("pluggy_frontend.cjs"))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
