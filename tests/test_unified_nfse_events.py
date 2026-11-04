from importlib import import_module
from supreme_common.auth_context import current_context

def test_cancelled_note_in_later_batch_leaves_financial_totals():
    from svc_nfse_engine.app import ingest, notes
    samples=import_module('services.svc-nfse-engine.tests.multilayout.nfse_samples')
    marker=current_context.set({'sub':'event-test','organization_id':'event-org','company_id':'event-company',
        'role':'super_admin','mfa_verified':True,'correlation_id':'event-correlation'})
    try:
        first=ingest([('nota.xml',samples.national())],'multi_layout_audit')
        assert len(notes())==1
        second=ingest([('cancelamento.xml',samples.event())],'multi_layout_audit')
        assert notes()==[]
        assert len(notes(active=False))==1
        assert first['snapshot_version']!=second['snapshot_version']
    finally:
        current_context.reset(marker)
