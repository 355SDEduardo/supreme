from pathlib import Path
import shutil
import subprocess

import pytest


def test_nfse_javascript_interactions():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js indisponível.')
    result = subprocess.run([node, '--test', str(Path(__file__).with_name('test_nfse_ui.cjs'))],
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
