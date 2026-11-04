"""Portal batches are temporary, replaceable and isolated from integrated custody."""
from io import BytesIO
import zipfile

from supreme_common.auth_context import create_access_token
from svc_nfse_engine.sample_generator import SAMPLE_FILES
from tests.test_integration import platform as platform_fixture

platform = platform_fixture


def test_portal_workspace_replaces_zip_with_xml_and_exports_only_latest(platform):
    gateway, _, _ = platform
    prefix = '/api/v1/nfse'
    # Existing integrated data must never appear in a new browser workspace.
    assert gateway.post(prefix + '/load-samples').status_code == 200
    workspace = gateway.post(prefix + '/workspaces').json()['workspace']
    params = {'workspace': workspace}
    assert gateway.get(prefix + '/notes', params=params).json() == []
    assert gateway.get(prefix + '/export/json', params=params).json()['notas'] == []
    samples = list(SAMPLE_FILES.items())
    archive = BytesIO()
    with zipfile.ZipFile(archive, 'w') as target:
        for name, raw in samples[:2]:
            target.writestr(name, raw.strip())
    response = gateway.post(prefix + '/upload', params=params,
                            files={'files': ('lote.zip', archive.getvalue(), 'application/zip')})
    assert response.status_code == 200, response.text
    assert response.json()['processed_count'] == 2
    assert len(gateway.get(prefix + '/notes', params=params).json()) == 2
    name, raw = samples[2]
    response = gateway.post(prefix + '/upload', params=params,
                            files={'files': (name, raw.strip().encode(), 'application/xml')})
    assert response.status_code == 200, response.text
    items = gateway.get(prefix + '/notes', params=params).json()
    assert len(items) == 1
    assert items[0]['arquivo_origem'] == name
    assert gateway.get(prefix + '/dashboard/stats', params=params).json()['total_notas'] == 1
    assert gateway.get(prefix + '/export/json', params=params).json()['notas'][0]['chave_nfse'] == items[0]['chave_nfse']
    for format_ in ('csv', 'excel'):
        export = gateway.get(prefix + '/export/' + format_, params=params)
        assert export.status_code == 200 and export.content
    # No automatic custody or mutation of the persistent company collection.
    assert gateway.get('/api/v1/documents').json() == []
    assert len(gateway.get(prefix + '/notes').json()) == len(samples)
    assert gateway.delete(prefix + '/notes', params=params).status_code == 200
    assert gateway.get(prefix + '/export/json', params=params).json()['notas'] == []


def test_workspace_failures_preserve_batch_and_context_is_enforced(platform):
    gateway, apps, _ = platform
    prefix = '/api/v1/nfse'
    key = gateway.post(prefix + '/workspaces').json()['workspace']
    params = {'workspace': key}
    assert gateway.post(prefix + '/load-samples', params=params).status_code == 200
    before = gateway.get(prefix + '/export/json', params=params).json()
    for name, content in [('bad.xml', b'<broken'), ('unknown.xml', b'<unknown/>'), ('bad.zip', b'bad')]:
        result = gateway.post(prefix + '/upload', params=params, files={'files': (name, content)})
        assert result.status_code == 400, result.text
        assert gateway.get(prefix + '/export/json', params=params).json() == before
    other_key = gateway.post(prefix + '/workspaces').json()['workspace']
    assert gateway.get(prefix + '/notes', params={'workspace': other_key}).json() == []
    for claim, value in [('sub', 'other-user'), ('organization_id', 'other-org'), ('company_id', 'other-company')]:
        claims = {'sub': 'integration-user', 'organization_id': 'integration-org',
                  'company_id': 'integration-company', 'role': 'super_admin', 'mfa_verified': True}
        claims[claim] = value
        response = gateway.get(prefix + '/export/json', params=params,
                               headers={'Authorization': 'Bearer ' + create_access_token(claims)})
        assert response.status_code == 410
    assert gateway.delete(prefix + '/workspaces/' + key).status_code == 200
    assert gateway.get(prefix + '/notes', params=params).status_code == 410
    apps['svc-nfse-engine'].state.workspaces.items[other_key].touched -= 7201
    assert gateway.get(prefix + '/notes', params={'workspace': other_key}).status_code == 410
    assert gateway.get(prefix + '/notes', params={'workspace': ''}).status_code == 410
