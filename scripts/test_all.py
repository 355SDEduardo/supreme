"""Run Python and JavaScript checks without ambiguous legacy import namespaces."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]

def main():
    run_tmp = ROOT / 'data' / 'test-runs' / f'runner-{uuid.uuid4().hex[:8]}'
    run_tmp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['TMP'] = str(run_tmp)
    env['TEMP'] = str(run_tmp)
    pytest_args = list(sys.argv[1:])
    if not any(arg.startswith('--basetemp') for arg in pytest_args):
        pytest_args.extend([f'--basetemp={run_tmp / "pytest"}', '-p', 'no:cacheprovider'])
    try:
        result = subprocess.run([sys.executable, '-m', 'pytest', *pytest_args], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
        node = shutil.which('node')
        if not node:
            print('Node.js não instalado; testes JavaScript não executados.', file=sys.stderr)
            return 1
        for folder in [ROOT / 'services/svc-nfse-engine/tests/strict', ROOT / 'st_difal_web/tests']:
            for path in sorted(folder.glob('*.cjs')):
                result = subprocess.run([node, '--test', str(path)], cwd=folder.parent, env=env)
                if result.returncode:
                    return result.returncode
        for path in sorted((ROOT / 'frontend').rglob('*.js')):
            result = subprocess.run([node, '--check', str(path)], cwd=ROOT, env=env)
            if result.returncode:
                return result.returncode
        return 0
    finally:
        shutil.rmtree(run_tmp, ignore_errors=True)

if __name__ == '__main__':
    raise SystemExit(main())
