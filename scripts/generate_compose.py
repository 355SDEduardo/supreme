"""Generate the checked-in Compose topology from the service inventory."""
from pathlib import Path
from scripts.service_catalog import SERVICES

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {'security-iam','companies','obligations','documents','bank-reconciliation','finance-bpo',
           'fiscal-gov','client-portal','analytics-dre','accounting-ai'}

def main():
    common = '''name: supreme
x-environment: &environment
  SUPREME_ENV: ${SUPREME_ENV:-development}
  SECRET_KEY: ${SECRET_KEY:?Execute scripts/bootstrap.py}
  MASTER_ENCRYPTION_KEY: ${MASTER_ENCRYPTION_KEY:?Execute scripts/bootstrap.py}
  STORAGE_ROOT_DIR: /data/storage
  DB_ROOT_DIR: /data/db
  DOCUMENT_UPLOADS_DIR: /data/storage/uploads
  PDF_OUTPUTS_DIR: /data/storage/pdf_outputs
  TAX_AUDIT_WORKSPACES_DIR: /data/storage/tax_audit
  NFE_FISCAL_CATALOG_PATH: /data/storage/nfe/fiscal_data.json
  EVENT_DB_PATH: /events/events.db
  REDIS_URL: redis://redis:6379/0
'''
    for slug,_,port in SERVICES:
        common += f'  SVC_{slug.upper().replace("-","_")}_URL: http://svc-{slug}:{port}\n'
    common += '''services:
  redis:
    image: redis:7-alpine
    command: [redis-server, --appendonly, 'yes']
    volumes: [redis-data:/data]
    healthcheck:
      test: [CMD, redis-cli, ping]
      interval: 5s
      retries: 10
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Configure POSTGRES_PASSWORD no .env}
'''
    for slug in sorted(DOMAINS):
        key = 'DB_'+slug.upper().replace('-','_')+'_PASSWORD'
        common += f'      {key}: ${{{key}:?Execute scripts/bootstrap.py}}\n'
    common += '''
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./infra/postgres/init.sh:/docker-entrypoint-initdb.d/init.sh:ro
    healthcheck:
      test: [CMD-SHELL, pg_isready -U postgres]
      interval: 5s
      retries: 10
'''
    volumes = ['redis-data','postgres-data','event-log']
    for slug,_,port in SERVICES:
        name = 'svc-' + slug
        volume = slug + '-data'
        volumes.append(volume)
        db_name = slug.replace('-', '_')
        common += f'''  {name}:
    build:
      context: .
      dockerfile: services/{name}/Dockerfile
    environment:
      <<: *environment
'''
        if slug in DOMAINS:
            key = 'DB_'+slug.upper().replace('-','_')+'_PASSWORD'
            common += f'      DATABASE_URL: postgresql+psycopg://{db_name}:${{{key}}}@postgres:5432/{db_name}\n'
        common += f'''    expose: ['{port}']
    volumes:
      - {volume}:/data
      - event-log:/events
    depends_on:
      postgres: {{condition: service_healthy}}
      redis: {{condition: service_healthy}}
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}/health')"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: unless-stopped
'''
    common += '''  gateway:
    build:
      context: .
      dockerfile: gateway/Dockerfile
    environment:
      <<: *environment
    ports: ['127.0.0.1:8080:8080']
    restart: unless-stopped
volumes:
'''
    common += ''.join('  ' + name + ':\n' for name in volumes)
    (ROOT/'docker-compose.yml').write_text(common,encoding='utf-8')
    init = '#!/bin/sh\nset -eu\n'
    for slug in sorted(DOMAINS):
        name = slug.replace('-','_')
        key = 'DB_'+slug.upper().replace('-','_')+'_PASSWORD'
        init += f'''psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${{{key}}}" <<'SQL'
CREATE ROLE {name} LOGIN PASSWORD :'service_password';
CREATE DATABASE {name} OWNER {name};
REVOKE ALL ON DATABASE {name} FROM PUBLIC;
SQL
'''
    (ROOT/'infra/postgres').mkdir(parents=True,exist_ok=True)
    (ROOT/'infra/postgres/init.sh').write_text(init,encoding='utf-8',newline='\n')

if __name__ == '__main__':
    main()
