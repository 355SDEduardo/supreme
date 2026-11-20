"""Report custody and copy delivered events. Runtime roles do not delete history."""

from __future__ import annotations

import argparse
import json
import os
import re

from sqlalchemy import create_engine, select, text
from supreme_common.supabase_database import SERVICE_SCHEMAS, postgres_configuration

PROBE_SCHEMAS = (*SERVICE_SCHEMAS.values(), 'nfse', 'nfe', 'tax_audit', 'events')

ARCHIVE_COPY = """
INSERT INTO events.events_archive (id, event_id, kind, body, created_at)
SELECT e.id, e.event_id, e.kind, e.body, e.created_at
FROM events.events AS e
WHERE e.created_at < now() - make_interval(days => :days)
  AND EXISTS (SELECT 1 FROM events.deliveries AS known)
  AND (
    SELECT count(DISTINCT d.subscriber) FROM events.deliveries AS d WHERE d.event_id = e.event_id
  ) = (
    SELECT count(DISTINCT subscriber) FROM events.deliveries
  )
  AND NOT EXISTS (
    SELECT 1 FROM events.events_archive AS archived WHERE archived.event_id = e.event_id
  )
"""

PENDING_EVENTS = """
SELECT
  (SELECT count(*) FROM events.events) AS total_events,
  (SELECT count(*) FROM events.events AS e
    WHERE NOT EXISTS (SELECT 1 FROM events.deliveries AS d WHERE d.event_id = e.event_id)
  ) AS without_delivery
"""

PROBE_NAMES = (
    'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_DB_URL',
    'SUPABASE_MAINTENANCE_DB_URL',
    *(f'SUPABASE_{schema.upper()}_DB_URL' for schema in PROBE_SCHEMAS),
)


def assert_statement_is_safe(statement: str) -> None:
    upper = statement.upper()
    for banned in ('DELETE ', 'DELETE\n', 'TRUNCATE', 'DROP ', 'DROP\n', 'UPDATE ', 'AUDIT_LOGS'):
        if banned in upper:
            raise ValueError('A manutenção não pode apagar auditoria nem alterar eventos confirmados.')


def configured() -> dict[str, bool]:
    return {name: bool(os.getenv(name)) for name in PROBE_NAMES}


def redact(message: str) -> str:
    hidden = re.sub(r'(?i)\b(?:postgres(?:ql)?(?:\+\w+)?|https?)://\S+', lambda match: match.group(0).split('://')[0] + '://***', message)
    return re.sub(r'(?i)(bearer\s+)\S+', r'\1***', hidden)


def archive_delivered_events(connection, days: int) -> int:
    if not 1 <= days <= 3650:
        raise ValueError('A retenção precisa ficar entre 1 e 3650 dias.')
    assert_statement_is_safe(ARCHIVE_COPY)
    role = connection.execute(text('SELECT current_user')).scalar_one()
    if str(role).startswith('supreme_'):
        raise PermissionError('Use a credencial administrativa. O role de runtime não arquiva eventos.')
    result = connection.execute(text(ARCHIVE_COPY), {'days': days})
    return result.rowcount or 0


def report(connection) -> dict:
    assert_statement_is_safe(PENDING_EVENTS)
    row = connection.execute(text(PENDING_EVENTS)).mappings().one()
    return {'total_events': row['total_events'], 'without_delivery': row['without_delivery']}


def probe() -> int:
    state = configured()
    print('Variáveis presentes: ' + ', '.join(f'{name}={str(value).lower()}' for name, value in state.items()))
    if not any(state.values()):
        print('Homologação remota não executada: nenhuma variável Supabase está configurada neste processo.')
        return 2
    missing = [
        f'SUPABASE_{schema.upper()}_DB_URL' for schema in PROBE_SCHEMAS
        if not os.getenv(f'SUPABASE_{schema.upper()}_DB_URL') and not os.getenv('SUPABASE_DB_URL')
    ]
    missing.extend(name for name in ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY') if not state[name])
    if missing:
        print('Homologação incompleta. Configure: ' + ', '.join(missing))
        return 2
    failures = []
    from scripts.supabase_schema import runtime_tables

    tables = runtime_tables()
    for schema in PROBE_SCHEMAS:
        engine = None
        try:
            raw_url = os.getenv(f'SUPABASE_{schema.upper()}_DB_URL') or os.environ['SUPABASE_DB_URL']
            url, options = postgres_configuration(raw_url, schema)
            engine = create_engine(url, **options)
            with engine.connect() as connection:
                connection.execute(text('SET TRANSACTION READ ONLY'))
                for table in tables:
                    if table.schema == schema:
                        # Validate columns and SELECT grants without reading tenant data.
                        connection.execute(select(table).limit(0))
            print(f'PostgreSQL {schema}: conexão, tabelas e leitura ok')
        except Exception:
            # Driver errors can include DSNs, passwords and query parameters.
            failures.append(f'PostgreSQL {schema}: falha; confira URL, TLS, role e migrações.')
        finally:
            if engine is not None:
                engine.dispose()
    if state['SUPABASE_URL'] and state['SUPABASE_SERVICE_ROLE_KEY']:
        try:
            from supreme_common.object_storage import BUCKET_LIMITS, ObjectStorage

            response = ObjectStorage('documents-custody')._request('GET', '/bucket')
            if response.status_code != 200:
                failures.append(f'Storage respondeu {response.status_code}.')
            else:
                buckets = {bucket['id']: bucket for bucket in response.json()}
                for name, limit in BUCKET_LIMITS.items():
                    bucket = buckets.get(name)
                    if bucket is None or bucket.get('public') is not False or bucket.get('file_size_limit') != limit:
                        failures.append(f'Storage {name}: bucket ausente, público ou limite divergente.')
                    else:
                        print(f'Storage {name}: privado, limite correto')
        except Exception:
            failures.append('Storage falhou: confira HTTPS, credencial e disponibilidade do projeto.')
    else:
        print('Storage não configurado.')
    for failure in failures:
        print(failure)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--archive-delivered-events', action='store_true')
    parser.add_argument('--older-than-days', type=int, default=365)
    args = parser.parse_args()
    assert_statement_is_safe(ARCHIVE_COPY)
    print('Auditoria do IAM permanece imutável. Eventos sem confirmação de todos os consumidores não são arquivados.')
    print('O arquivamento copia eventos entregues e não apaga os originais. Objetos sem referência são apenas relatados.')
    if args.probe:
        raise SystemExit(probe())
    if not any(configured().values()):
        print('Relatório remoto não executado: configure o projeto de teste antes da homologação.')
        raise SystemExit(2)
    if not args.archive_delivered_events:
        url = os.getenv('SUPABASE_EVENTS_DB_URL') or os.getenv('SUPABASE_DB_URL')
        if not url:
            print('Nenhuma linha foi alterada. Relatório de eventos não configurado.')
            return
        engine = None
        try:
            target, options = postgres_configuration(url, 'events')
            engine = create_engine(target, **options)
            with engine.connect() as connection:
                connection.execute(text('SET TRANSACTION READ ONLY'))
                print(json.dumps(report(connection), ensure_ascii=False))
        except Exception:
            print('Relatório indisponível; confira URL, TLS, role e migrações do journal.')
            raise SystemExit(1) from None
        finally:
            if engine is not None:
                engine.dispose()
        print('Nenhuma linha foi alterada.')
        return
    url = os.getenv('SUPABASE_MAINTENANCE_DB_URL')
    if not url:
        print('Arquivamento não executado: configure SUPABASE_MAINTENANCE_DB_URL com a credencial do owner.')
        raise SystemExit(2)
    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 10})
        with engine.begin() as connection:
            copied = archive_delivered_events(connection, args.older_than_days)
    except Exception as exc:
        print(redact(str(exc)))
        raise SystemExit(1) from None
    print(f'Eventos copiados para o arquivo: {copied}. Os originais foram preservados.')


if __name__ == '__main__':
    main()
