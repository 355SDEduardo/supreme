"""Run isolated services; stop the entire process group on failure or Ctrl+C."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def service_environment(slug: str, environment: dict[str, str]) -> dict[str, str]:
    from supreme_common.supabase_database import SERVICE_SCHEMAS
    result = dict(environment)
    # This runner launches all domains; a process-wide URL would cross boundaries.
    result.pop('DATABASE_URL', None)
    schema = SERVICE_SCHEMAS.get('svc-' + slug) or {
        'nfse-engine': 'nfse', 'nfe-difal': 'nfe', 'federal-tax-audit': 'tax_audit'
    }.get(slug)
    own_key = f'SUPABASE_{schema.upper()}_DB_URL' if schema else None
    if slug != 'gateway' and not result.get('SUPABASE_EVENTS_DB_URL') and result.get('SUPABASE_DB_URL'):
        result['SUPABASE_EVENTS_DB_URL'] = result['SUPABASE_DB_URL']
    for key in list(result):
        if key.startswith('SUPABASE_') and key.endswith('_DB_URL'):
            allowed = {own_key, 'SUPABASE_EVENTS_DB_URL'} if slug != 'gateway' else set()
            if schema and not result.get(own_key):
                allowed.add('SUPABASE_DB_URL')
            if key not in allowed:
                result.pop(key)
    if slug == 'gateway':
        result.pop('SUPREME_DATABASE_MODE', None)
        result.pop('DATABASE_URL', None)
    if slug not in {'documents', 'nfse-engine', 'federal-tax-audit', 'fiscal-gov'}:
        result.pop('SUPABASE_SERVICE_ROLE_KEY', None)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    from supreme_common.auth_context import secret_key
    from scripts.service_catalog import SERVICES
    secret_key()
    if len(os.getenv('MASTER_ENCRYPTION_KEY','')) != 64:
        parser.error('Execute scripts/bootstrap.py para preparar o cofre.')
    for slug,_,port in SERVICES:
        os.environ.setdefault('SVC_' + slug.upper().replace('-','_') + '_URL', f'http://127.0.0.1:{port}')
    bindings = []
    try:
        for port in [8080] + [item[2] for item in SERVICES]:
            connection = socket.socket()
            connection.bind((args.host,port))
            bindings.append(connection)
    finally:
        for connection in bindings:
            connection.close()
    processes = []
    logdir = ROOT/'data/logs'
    logdir.mkdir(parents=True,exist_ok=True)
    streams = []
    try:
        for slug,_,port in SERVICES + [('gateway','platform',8080)]:
            module = 'gateway.bff_router:app' if slug == 'gateway' else 'svc_' + slug.replace('-','_') + '.app:app'
            output = (logdir/(slug+'.log')).open('a', encoding='utf-8')
            streams.append(output)
            processes.append((slug,subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host',args.host,'--port',str(port)],
                cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,env=service_environment(slug, os.environ),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)))
        print('Supreme: http://' + args.host + ':8080 — logs em data/logs; Ctrl+C para encerrar.',flush=True)
        while True:
            for slug,process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f'{slug} encerrou com código {process.returncode}. Consulte data/logs/{slug}.log.')
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('Encerrando os serviços...',flush=True)
    finally:
        for _,process in processes:
            if process.poll() is None:
                process.terminate()
        for _,process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for output in streams:
            output.close()

if __name__ == '__main__':
    main()
