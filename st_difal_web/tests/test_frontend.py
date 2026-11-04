from pathlib import Path
import shutil
import subprocess

import pytest


def test_zip_comparison_javascript_interactions():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js indisponível para os testes de interação JavaScript.")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("test_zip_comparison_ui.cjs"))],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
