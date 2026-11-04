"""Exercise actual ASGI services together over their HTTP boundaries."""
import asyncio
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from importlib import import_module
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from supreme_common.auth_context import create_access_token, current_context
from supreme_common.events import consume_once
from scripts.service_catalog import SERVICES

@pytest.fixture
def platform(monkeypatch):
    apps = {'svc-'+slug: import_module('svc_'+slug.replace('-','_')+'.app').create_app() for slug,_,_ in SERVICES}
    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            app = apps[request.url.host]
            return await httpx.ASGITransport(app=app).handle_async_request(request)
    transport = Transport()
    original = httpx.AsyncClient
    class Client(original):
        def __init__(self,*args,**kwargs):
            kwargs.setdefault('transport',transport)
            super().__init__(*args,**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    for slug,_,port in SERVICES:
        monkeypatch.setenv('SVC_'+slug.upper().replace('-','_')+'_URL',f'http://svc-{slug}:{port}')
    from gateway.bff_router import create_app
    with ExitStack() as stack:
        clients={name: stack.enter_context(TestClient(app)) for name,app in apps.items()}
        gateway=stack.enter_context(TestClient(create_app(transport=transport)))
        token=create_access_token({'sub':'integration-user','organization_id':'integration-org',
            'role':'super_admin','mfa_verified':True,'company_id':'integration-company'})
        gateway.headers['Authorization']='Bearer '+token
        yield gateway,apps,clients

def test_gateway_health_openapi_and_nfse_document_audit_flow(platform):
    gateway,apps,clients=platform
    response=gateway.get('/api/v1/platform/health')
    assert response.status_code == 200
    assert all(item['available'] for item in response.json()['services'])
    schema=gateway.get('/api/openapi.json')
    assert schema.status_code == 200, schema.text
    assert schema.json()['x-unavailable-services'] == []
    assert '/api/v1/pdf/merge' in schema.json()['paths']
    assert '/api/v1/nfse/upload' in schema.json()['paths']
    from svc_nfse_engine.sample_generator import SAMPLE_FILES
    filename,raw=next(iter(SAMPLE_FILES.items()))
    response=gateway.post('/api/v1/nfse/upload',files={'files':(filename,raw.strip().encode(),'application/xml')})
    assert response.status_code == 200, response.text
    assert response.json()['processed_count'] == 1
    docs=gateway.get('/api/v1/documents')
    assert docs.status_code == 200 and len(docs.json()) == 1
    async def deliver():
        await consume_once('federal-tax-audit',apps['svc-federal-tax-audit'].state.event_handlers)
        await consume_once('fiscal-gov',apps['svc-fiscal-gov'].state.event_handlers)
    asyncio.run(deliver())
    result=gateway.get('/api/v1/tax-audit/audit')
    assert result.status_code == 200, result.text
    assert result.json()['resumo_faturamento']['total_nfse_emitidas'] == 1
    assert 'LIDER' not in result.json()['empresa']['razao_social'] or 'LIDER' in raw
    projection=apps['svc-fiscal-gov'].state.sessions()
    from svc_fiscal_gov.integration import RetentionProjection
    with projection as db:
        assert db.query(RetentionProjection).count() == 1

def test_bank_settlement_is_idempotent_and_analytics_use_real_data(platform):
    gateway,apps,clients=platform
    from svc_finance_bpo.models import PayableReceivableBill
    from svc_bank_reconciliation.models import BankAccount,BankTransaction
    claims={'sub':'integration-user','organization_id':'integration-org','role':'super_admin',
            'company_id':'integration-company','mfa_verified':True,'correlation_id':'integration-test'}
    marker=current_context.set(claims)
    try:
        with apps['svc-finance-bpo'].state.sessions() as db:
            db.add(PayableReceivableBill(id='bill-a',company_id='integration-company',type='payable',
                counterparty_name='Fornecedor sintético',original_amount=Decimal('123.45'),final_amount=Decimal('123.45'),
                issue_date=date.today(),due_date=date.today(),payment_method='pix',status='approved'))
            db.commit()
        with apps['svc-bank-reconciliation'].state.sessions() as db:
            db.add(BankAccount(id='account-a',company_id='integration-company',bank_code='001',bank_name='Banco sintético',
                agency_number='1',account_number='1'))
            db.flush()
            db.add(BankTransaction(id='transaction-a',bank_account_id='account-a',fitid='fitid-test',
                amount=Decimal('-123.45'),transaction_date=date.today(),memo='Fornecedor sintético',status='pending'))
            db.commit()
    finally:
        current_context.reset(marker)
    response=gateway.post('/api/v1/reconciliation/suggest?account_id=account-a')
    assert response.status_code == 200, response.text
    assert response.json()[0]['best_match_bill_id'] == 'bill-a'
    payload={'company_id':'integration-company','bank_account_id':'account-a','transaction_id':'transaction-a','bill_ids':['bill-a']}
    first=gateway.post('/api/v1/reconciliation/confirm',json=payload)
    assert first.status_code == 200,first.text
    repeated=gateway.post('/api/v1/reconciliation/confirm',json=payload)
    assert repeated.status_code == 200
    with apps['svc-finance-bpo'].state.sessions() as db:
        assert db.query(PayableReceivableBill).filter(PayableReceivableBill.id=='bill-a').one().status == 'paid'
    # Drain the transactional finance outbox, then project each event through the consumer.
    from supreme_common.events import DomainEvent, publish_envelope
    from sqlalchemy import select
    table=apps['svc-finance-bpo'].state.outbox
    with apps['svc-finance-bpo'].state.engine.begin() as db:
        for row in db.execute(select(table)).mappings():
            publish_envelope(DomainEvent.model_validate_json(row['body']))
    asyncio.run(consume_once('analytics-dre',apps['svc-analytics-dre'].state.event_handlers))
    competence=date.today().strftime('%Y-%m')
    dre=gateway.get('/api/v1/analytics/companies/integration-company/dre?competence='+competence)
    assert dre.status_code == 200,dre.text
    assert dre.json()['net_income'] == -123.45
    pdf=gateway.post('/api/v1/analytics/companies/integration-company/export-pdf',json={'competence':competence})
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-'),pdf.text[:300]

def test_company_registration_context_switch_and_organization_isolation(platform):
    gateway,apps,clients=platform
    response=gateway.post('/api/v1/companies',json={'organization_id':'integration-org',
        'corporate_name':'Empresa sintética','tax_id':'11222333000181','tax_regime':'lucro_presumido'})
    assert response.status_code == 200,response.text
    company_id=response.json()['id']
    assert len(gateway.get('/api/v1/companies').json()) == 1
    cockpit=gateway.get('/api/v1/cockpit/companies/summary')
    assert cockpit.status_code==200,cockpit.text
    assert cockpit.json()['average_closing_progress_pct'] is None
    batch=gateway.post('/api/v1/companies/batch/request-documents',json={
        'organization_id':'integration-org','company_ids':[company_id],'competence':'2026-10'})
    assert batch.status_code==200 and batch.json()['success_count']==1,batch.text
    response=gateway.post('/api/v1/auth/switch-company-context',json={'target_company_id':company_id})
    assert response.status_code == 200,response.text
    gateway.headers['Authorization']='Bearer '+response.json()['access_token']
    from svc_security_iam.auth import Identity
    with apps['svc-security-iam'].state.sessions() as db:
        db.add(Identity(id='analyst-a',organization_id='integration-org',email='analyst@example.test',
            password_hash='not-used-by-this-test',role='analyst',company_ids='[]'))
        db.commit()
    assigned=gateway.post('/api/v1/companies/'+company_id+'/assign-analyst',
        json={'analyst_user_id':'analyst-a','department':'fiscal'})
    assert assigned.status_code==200,assigned.text
    other=create_access_token({'sub':'other-user','organization_id':'other-org','role':'super_admin',
        'company_id':'company-other','mfa_verified':True})
    response=gateway.get('/api/v1/companies',headers={'Authorization':'Bearer '+other})
    assert response.status_code == 200 and response.json() == []
