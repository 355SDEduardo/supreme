"""Prepare a resumable copy of local custody. Original files are only opened for reading."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
from hashlib import sha256

from supreme_common.object_storage import BUCKET_LIMITS

SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
CATALOG_LIMIT = 10 * 1024 ** 2


class ConfigurationError(RuntimeError):
    """The remote destination is not configured. Nothing was uploaded."""


def file_digest(path: Path) -> tuple[str, int]:
    digest, size = sha256(), 0
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def safe_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or candidate.is_symlink():
        raise ValueError('Caminho fora da raiz do acervo.')
    return candidate


def _record(**fields) -> dict:
    return {
        'id': fields['id'], 'service': fields['service'], 'bucket': fields['bucket'],
        'organization_id': fields['organization_id'], 'company_id': fields['company_id'],
        'source': fields['source'], 'member': fields.get('member', ''), 'name': fields.get('name', ''),
        'sha256': fields['sha256'], 'size': fields['size'], 'status': fields.get('status', 'pending'),
        'remote_reference': fields.get('remote_reference', ''), 'error': fields.get('error', ''),
    }


def _tenant_file(root: Path, base: Path, path: Path, service: str, bucket: str) -> dict | None:
    relative = path.relative_to(root).as_posix()
    parts = path.relative_to(base).parts
    if len(parts) < 3 or not SAFE_ID.fullmatch(parts[0]) or not SAFE_ID.fullmatch(parts[1]):
        digest, size = file_digest(path)
        return _record(id=f'{service}:::{relative}', service=service, bucket=bucket, organization_id='',
                       company_id='', source=relative, name=path.name, sha256=digest, size=size,
                       status='blocked', error='Organização ou empresa ausente; não há empresa padrão.')
    digest, size = file_digest(path)
    org, company, *rest = parts
    return _record(id=f'{service}:{org}:{company}:{relative}', service=service, bucket=bucket,
                   organization_id=org, company_id=company, source=relative, name='/'.join(rest),
                   sha256=digest, size=size)


def discover(root: Path) -> list[dict]:
    root = root.resolve()
    records = []
    uploads = root / 'uploads'
    if uploads.exists():
        for path in sorted(uploads.rglob('*')):
            if path.is_file() and not path.is_symlink() and not path.name.endswith('.tmp'):
                records.append(_tenant_file(root, uploads, path, 'documents', 'documents-custody'))
    audit = root / 'tax_audit'
    if audit.exists():
        for path in sorted(audit.rglob('*')):
            if path.is_file() and not path.is_symlink() and path.name != 'state.db' and not path.name.endswith('.tmp'):
                records.append(_tenant_file(root, audit, path, 'tax_audit', 'tax-audit-workspaces'))
    catalog_root = root / 'nfe'
    if catalog_root.exists():
        for path in sorted(catalog_root.glob('*/*/fiscal_data.json')):
            if path.is_file() and not path.is_symlink():
                records.append(_tenant_file(root, catalog_root, path, 'nfe', ''))
    nfse = root / 'nfse'
    if nfse.exists():
        for db_path in sorted(nfse.glob('*/*/state.db')):
            if db_path.is_symlink():
                continue
            org, company = db_path.parts[-3], db_path.parts[-2]
            relative = db_path.relative_to(root).as_posix()
            if not SAFE_ID.fullmatch(org) or not SAFE_ID.fullmatch(company):
                continue
            try:
                with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
                    rows = db.execute('SELECT sha, filename, content FROM artifacts').fetchall()
            except sqlite3.Error:
                continue
            for sha, filename, content in rows:
                blob = bytes(content)
                digest = sha256(blob).hexdigest()
                mismatch = sha != digest
                records.append(_record(
                    id=f'nfse:{org}:{company}:{relative}:{sha}', service='nfse', bucket='nfse-xml',
                    organization_id=org, company_id=company, source=relative, member=sha, name=filename or sha,
                    sha256=digest, size=len(blob), status='failed' if mismatch else 'pending',
                    error='O hash gravado no SQLite não confere com o conteúdo; nada foi alterado.' if mismatch else ''))
    return [item for item in records if item is not None]


def read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_manifest(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(''.join(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n' for record in records),
                         encoding='utf-8')
    temporary.replace(path)


def merge(existing: list[dict], discovered: list[dict]) -> list[dict]:
    current = {item['id']: item for item in existing}
    discovered_ids = set()
    for item in discovered:
        previous = current.get(item['id'])
        discovered_ids.add(item['id'])
        if previous and previous.get('status') == 'transferred' and previous.get('sha256') == item['sha256']:
            item['status'] = 'transferred'
            item['remote_reference'] = previous.get('remote_reference', '')
            item['error'] = ''
        elif previous and previous.get('status') == 'transferred':
            item['observed_sha256'] = item['sha256']
            item['sha256'] = previous['sha256']
            item['status'] = 'failed'
            item['remote_reference'] = previous.get('remote_reference', '')
            item['error'] = 'Origem alterada após a transferência. O original e o objeto remoto não foram modificados.'
        elif item['status'] == 'pending' and previous:
            item['remote_reference'] = previous.get('remote_reference', '')
        current[item['id']] = item
    for identity, previous in current.items():
        if identity not in discovered_ids and previous.get('status') != 'failed':
            previous['status'] = 'failed'
            previous['error'] = 'Origem ausente. Nenhum arquivo ou objeto remoto foi apagado.'
    return sorted(current.values(), key=lambda item: item['id'])


def load_content(root: Path, record: dict) -> bytes:
    path = safe_path(root, record['source'])
    if record['service'] == 'nfse':
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT content FROM artifacts WHERE sha=?', (record['member'],)).fetchone()
        if row is None:
            raise FileNotFoundError('Artefato ausente; o SQLite não foi alterado.')
        return bytes(row[0])
    return path.read_bytes()


def store_record(record: dict, content: bytes) -> str:
    if record['service'] == 'nfe':
        return _store_catalog(record, content)
    if record['service'] == 'tax_audit':
        return _store_audit(record, content)
    return _store_object(record, content)


def _context(record: dict):
    from supreme_common.auth_context import current_context
    claims = {'sub': 'archive-transfer', 'organization_id': record['organization_id'],
              'company_id': record['company_id'], 'correlation_id': record['sha256'][:32], 'role': 'service'}
    return current_context.set(claims), current_context


def _store_object(record: dict, content: bytes) -> str:
    from supreme_common.object_storage import ObjectStorage, enabled
    if not enabled():
        raise ConfigurationError('Storage remoto não configurado.')
    marker, context = _context(record)
    try:
        storage = ObjectStorage(record['bucket'])
        reference = storage.put(content)
        if storage.get(reference) != content:
            raise RuntimeError('Leitura remota divergente do arquivo original.')
        return reference
    finally:
        context.reset(marker)


def _store_audit(record: dict, content: bytes) -> str:
    from supreme_common.fiscal_database import enabled
    from svc_federal_tax_audit.repository import put_file
    if not enabled('tax_audit'):
        raise ConfigurationError('Banco de auditoria remoto não configurado.')
    marker, context = _context(record)
    try:
        put_file(record['name'], content)
    finally:
        context.reset(marker)
    return _store_object(record, content)


def _store_catalog(record: dict, content: bytes) -> str:
    from supreme_common.fiscal_database import enabled
    from svc_nfe_difal.repository import replace_catalog
    if not enabled('nfe'):
        raise ConfigurationError('Banco NF-e remoto não configurado.')
    marker, context = _context(record)
    try:
        replace_catalog(content)
    finally:
        context.reset(marker)
    return 'nfe-catalog:' + record['sha256']


def _limit(record: dict) -> int:
    if record['service'] == 'nfe':
        return CATALOG_LIMIT
    return BUCKET_LIMITS[record['bucket']]


def apply(root: Path, manifest: Path) -> dict:
    root = root.resolve()
    records = read_manifest(manifest)
    summary = {'transferred': 0, 'pending': 0, 'failed': 0, 'blocked': 0}
    for record in records:
        if record.get('organization_id') == '' or record.get('company_id') == '':
            record['status'] = 'blocked'
            record['error'] = 'Organização ou empresa ausente; não há empresa padrão.'
        elif record.get('status') == 'transferred' or record.get('observed_sha256'):
            record['status'] = 'transferred' if record.get('status') == 'transferred' else 'failed'
        else:
            try:
                content = load_content(root, record)
                digest = sha256(content).hexdigest()
                if digest != record['sha256'] or (record['service'] == 'nfse' and record['member'] != digest):
                    raise ValueError('Hash divergente do manifesto. O original não foi alterado.')
                if len(content) > _limit(record):
                    raise ValueError('Arquivo excede o limite do destino. O original não foi alterado.')
                record['remote_reference'] = store_record(record, content)
                record['status'] = 'transferred'
                record['error'] = ''
            except ConfigurationError as exc:
                record['status'] = 'blocked'
                record['error'] = str(exc)
            except Exception as exc:
                record['status'] = 'failed'
                record['error'] = str(exc)[:240]
        summary[record['status']] = summary.get(record['status'], 0) + 1
        write_manifest(manifest, records)
    return summary


def plan(root: Path, manifest: Path) -> dict:
    records = merge(read_manifest(manifest), discover(root))
    write_manifest(manifest, records)
    return {'records': len(records)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'apply'))
    parser.add_argument('--root', default=os.getenv('STORAGE_ROOT_DIR', './data/storage'))
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    root, manifest = Path(args.root), Path(args.manifest)
    if args.command == 'plan':
        print(json.dumps(plan(root, manifest), ensure_ascii=False))
    else:
        print(json.dumps(apply(root, manifest), ensure_ascii=False))


if __name__ == '__main__':
    main()
