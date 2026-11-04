from contextlib import ExitStack
from importlib import import_module
from pathlib import Path
import json
import time
import pytest
from fastapi.testclient import TestClient
import httpx
from supreme_common.auth_context import create_access_token, current_context
from scripts.service_catalog import SERVICES

def claims(company='company-a', organization='org-a', role='super_admin'):
    return {'sub':'operator-a','organization_id':organization,'company_id':company,'role':role,'mfa_verified':True}

def headers(**kwargs):
    return {'Authorization':'Bearer '+create_access_token(claims(**kwargs))}

@pytest.mark.parametrize('slug,route,port', SERVICES)
def test_service_health_and_private_api_requires_authentication(slug, route, port):
    module = import_module('svc_' + slug.replace('-','_') + '.app')
    with TestClient(module.create_app()) as client:
        assert client.get('/health').status_code == 200
        # Unknown private routes still cannot reveal application details anonymously.
        assert client.get('/private-resource').status_code == 401
        response = client.get('/openapi.json')
        assert response.status_code == 200
        assert response.json()['info']['title'] == 'svc-' + slug

def test_document_custody_and_cross_company_rejection():
    from svc_documents.app import create_app
    with TestClient(create_app()) as client:
        response = client.post('/documents/upload', headers=headers(), data={'company_id':'company-a','competence':'2026-10'},
            files={'file':('nota.xml',b'<?xml version="1.0"?><root/>','application/xml')})
        assert response.status_code == 200, response.text
        document = response.json()
        assert client.get('/documents/'+document['id']+'/content',headers=headers()).content.endswith(b'<root/>')
        assert client.get('/documents/'+document['id']+'/metadata',headers=headers(company='company-b')).status_code == 404
        assert client.get('/documents',headers=headers(company='company-b')).json() == []
        assert client.get('/documents?company_id=company-b',headers=headers()).status_code == 403
        assert client.post('/documents/upload',headers=headers(),data={'company_id':'company-b','competence':'2026-10'},
            files={'file':('nota.xml',b'<r/>')}).status_code == 403

def test_iam_mfa_setup_login_replay_and_invalid_pfx():
    import pyotp
    from svc_security_iam.app import create_app
    from svc_security_iam.auth import Identity
    from supreme_common.auth_context import hash_password
    with TestClient(create_app()) as client:
        with client.app.state.sessions() as db:
            db.add(Identity(id='operator-a',organization_id='org-a',email='admin@example.test',
                password_hash=hash_password('very-long-test-password'),role='super_admin',company_ids='[]'))
            db.commit()
        response = client.post('/security/auth/token',json={'email':'admin@example.test','password':'wrong'})
        assert response.status_code == 401
        response = client.post('/security/auth/token',json={'email':'admin@example.test','password':'very-long-test-password'})
        assert response.status_code == 200
        token = response.json()['access_token']
        auth = {'Authorization':'Bearer '+token}
        setup = client.post('/security/mfa/setup',headers=auth)
        assert setup.status_code == 200, setup.text
        code = pyotp.TOTP(setup.json()['secret']).now()
        verified = client.post('/security/mfa/verify',headers=auth,json={'token':code})
        assert verified.status_code == 200, verified.text
        assert client.post('/security/mfa/verify',headers=auth,json={'token':code}).status_code == 400
        response = client.post('/certificates/vault/upload',headers=headers(),data={'company_id':'company-a','password':'bad'},files={'file':('invalid.pfx',b'garbage')})
        assert response.status_code == 400, response.text

def test_nfse_snapshots_tenant_isolation_and_export():
    from svc_nfse_engine.app import create_app
    with TestClient(create_app()) as client:
        response = client.post('/api/load-samples',headers=headers())
        assert response.status_code == 200, response.text
        assert response.json()['processed_count'] == 4
        version = response.json()['snapshot_version']
        exported = client.get('/api/export/json?version='+version,headers=headers())
        assert len(exported.json()['notas']) == 4
        assert client.get('/api/notes',headers=headers(company='company-b')).json() == []
        excel = client.get('/api/export/excel',headers=headers())
        assert excel.status_code == 200 and excel.content[:2] == b'PK'
        assert client.get('/api/export/excel?mode=auditoria',headers=headers()).content[:2] == b'PK'
        assert client.get('/api/retencoes?competencia=2026-01',headers=headers()).status_code == 200
        assert client.get('/api/dashboard/stats',headers=headers()).status_code == 200
        key = exported.json()['notas'][0]['chave_nfse']
        assert client.delete('/api/notes/'+key,headers=headers()).status_code == 200
        assert len(client.get('/api/export/json',headers=headers()).json()['notas']) == 3
        assert len(client.get('/api/export/json?version='+version,headers=headers()).json()['notas']) == 4

def test_gateway_route_ownership_and_failure_status():
    from gateway.bff_router import create_app, target
    assert target('companies/x/obligations') == ('obligations','/companies/x/obligations')
    assert target('nfse/upload') == ('nfse-engine','/api/upload')
    assert target('pdf/merge') == ('pdf-tools','/pdf/merge')
    assert target('reconciliation/suggest') == ('bank-reconciliation','/reconciliations/suggest')
    requests = []
    def upstream(request):
        requests.append(request)
        return httpx.Response(200,json={'proxied':True})
    with TestClient(create_app(transport=httpx.MockTransport(upstream))) as client:
        assert client.get('/api/v1/nfse/notes').status_code == 401
        response = client.get('/api/v1/nfse/notes',headers=headers())
        assert response.status_code == 200 and response.json()['proxied']
        assert requests[-1].url.path == '/api/notes'
        assert requests[-1].headers['authorization'].startswith('Bearer ')

def test_event_delivery_retries_and_acknowledgement():
    import asyncio
    from supreme_common.events import publish, consume_once
    marker = current_context.set({**claims(),'correlation_id':'test-correlation'})
    try:
        publish('TestEvent', {'amount':'10.00'}, event_id='unique-event')
        publish('TestEvent', {'amount':'10.00'}, event_id='unique-event')
    finally:
        current_context.reset(marker)
    attempts = []
    async def handler(event):
        attempts.append(event.event_id)
        if len(attempts) == 1:
            raise RuntimeError('Transient test failure')
    async def execute():
        await consume_once('test-consumer',{'TestEvent':handler})
        await consume_once('test-consumer',{'TestEvent':handler})
        await consume_once('test-consumer',{'TestEvent':handler})
    asyncio.run(execute())
    assert attempts == ['unique-event','unique-event']
