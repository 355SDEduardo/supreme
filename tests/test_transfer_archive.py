from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

from scripts.transfer_archive import ConfigurationError, apply, discover, plan


def build_archive(root):
    document = root / 'uploads' / 'org-a' / 'company-a' / ('ab' * 32)
    document.parent.mkdir(parents=True)
    document.write_bytes(b'%PDF-1.4 original')
    loose = root / 'uploads' / 'company-only' / 'file.pdf'
    loose.parent.mkdir(parents=True)
    loose.write_bytes(b'%PDF-1.4 loose')
    audit = root / 'tax_audit' / 'org-a' / 'company-a' / 'notas' / 'Consolidado_NFSe.json'
    audit.parent.mkdir(parents=True)
    audit.write_bytes(b'{"notas":[]}')
    catalog = root / 'nfe' / 'org-a' / 'company-a' / 'fiscal_data.json'
    catalog.parent.mkdir(parents=True)
    catalog.write_bytes(b'[]')
    database = root / 'nfse' / 'org-a' / 'company-a' / 'state.db'
    database.parent.mkdir(parents=True)
    content = b'<xml>nota</xml>'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE artifacts (sha TEXT PRIMARY KEY, filename TEXT, content BLOB)')
        db.execute('INSERT INTO artifacts VALUES (?,?,?)', (sha256(content).hexdigest(), 'nota.xml', content))
    originals = {path: path.read_bytes() for path in (document, loose, audit, catalog, database)}
    return originals


def test_plan_hashes_sources_and_refuses_a_default_company(tmp_path):
    originals = build_archive(tmp_path)
    manifest = tmp_path / 'manifest.jsonl'
    assert plan(tmp_path, manifest)['records'] == 5
    records = {item['id']: item for item in discover(tmp_path)}
    blocked = [item for item in records.values() if item['organization_id'] == '']
    assert len(blocked) == 1
    assert blocked[0]['status'] == 'blocked'
    nfse = next(item for item in records.values() if item['service'] == 'nfse')
    assert nfse['sha256'] == sha256(b'<xml>nota</xml>').hexdigest()
    assert nfse['member'] == nfse['sha256']
    for path, content in originals.items():
        assert path.read_bytes() == content


def test_apply_resumes_and_preserves_originals(tmp_path, monkeypatch):
    originals = build_archive(tmp_path)
    manifest = tmp_path / 'manifest.jsonl'
    plan(tmp_path, manifest)
    stored = {}
    calls = {'n': 0}

    def store(record, content):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('storage indisponível')
        if record['service'] == 'nfe' and not stored.get('catalog-ready'):
            raise ConfigurationError('Banco NF-e remoto não configurado.')
        digest = sha256(content).hexdigest()
        stored[record['id']] = content
        return 'nfe-catalog:' + digest if record['service'] == 'nfe' else f'supabase://{record["bucket"]}/{digest}'

    monkeypatch.setattr('scripts.transfer_archive.store_record', store)
    first = apply(tmp_path, manifest)
    assert first['failed'] == 1
    assert first['blocked'] >= 1
    stored['catalog-ready'] = True
    second = apply(tmp_path, manifest)
    assert second['failed'] == 0
    assert second['transferred'] == 4
    assert second['blocked'] == 1
    third = apply(tmp_path, manifest)
    assert third['transferred'] == 4
    assert calls['n'] == 6
    for path, content in originals.items():
        assert path.read_bytes() == content
    saved = [json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines()]
    assert {item['status'] for item in saved if item['organization_id']} == {'transferred'}


def test_changed_source_is_not_uploaded_again(tmp_path, monkeypatch):
    build_archive(tmp_path)
    manifest = tmp_path / 'manifest.jsonl'
    plan(tmp_path, manifest)
    monkeypatch.setattr('scripts.transfer_archive.store_record', lambda record, content: 'ref-' + record['sha256'])
    apply(tmp_path, manifest)
    target = tmp_path / 'tax_audit' / 'org-a' / 'company-a' / 'notas' / 'Consolidado_NFSe.json'
    target.write_bytes(b'{"notas":[1]}')
    plan(tmp_path, manifest)
    calls = []
    monkeypatch.setattr('scripts.transfer_archive.store_record', lambda record, content: calls.append(record['id']) or 'new')
    apply(tmp_path, manifest)
    assert calls == []
    rows = [json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines()]
    changed = next(item for item in rows if item['name'] == 'notas/Consolidado_NFSe.json')
    assert changed['status'] == 'failed'
    assert 'não foram modificados' in changed['error']
