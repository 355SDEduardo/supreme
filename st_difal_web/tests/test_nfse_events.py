from dataclasses import replace
from datetime import datetime
import xml.etree.ElementTree as ET

from core.nfse_events import NfseEventManager
from core.nfse_models import DocumentStatus
from core.nfse_parser_national import NationalNfseParser
from core.nfse_pipeline import process_nfse_batch
from tests.nfse_samples import KEY, national, event, abrasf


def test_orphan_reconciliation_and_immutable_status_projection():
    manager = NfseEventManager()
    document = NationalNfseParser().parse(ET.fromstring(national()), 'hash', 'a.xml')
    cancellation = manager.parse_event_xml(ET.fromstring(event()), 'event-hash')
    manager.register_event(cancellation, set())
    assert len(manager.orphan_events) == 1
    assert manager.reconcile_orphans(KEY) == [cancellation]
    assert not manager.orphan_events
    assert manager.project_status(document).status == DocumentStatus.CANCELLED
    assert document.status == DocumentStatus.AUTHORIZED


def test_batch_event_order_deduplication_and_orphans():
    cancellation = event()
    state = process_nfse_batch([('event.xml', cancellation), ('a.xml', national()),
        ('same.xml', cancellation), ('missing.xml', event(key='9' * 50))])
    assert state.documents[0].status == DocumentStatus.CANCELLED
    assert len(state.events) == 2
    assert len(state.orphan_events) == 1
    assert state.total_gross_amount == 0


def test_substitution_chain_cycle_and_chronological_projection():
    manager = NfseEventManager()
    first = manager.parse_event_xml(ET.fromstring(event(code='e101103', substitute='B')), 'first')
    second = replace(first, event_id='second', target_access_key='B', substituting_access_key='C')
    third = replace(first, event_id='third', target_access_key='C', substituting_access_key=KEY)
    for item in (first, second, third):
        manager.register_event(item, {KEY, 'B', 'C'})
    assert manager.get_effective_document_chain(KEY) == [KEY, 'B', 'C']
    doc = NationalNfseParser().parse(ET.fromstring(national()), 'hash', 'a.xml')
    assert manager.project_status(doc).status == DocumentStatus.SUBSTITUTED
    # naive/aware timestamps must sort deterministically without TypeError.
    older = replace(first, event_id='older', event_type='CANCELAMENTO', substituting_access_key='',
                    event_datetime=datetime(2026, 1, 1))
    manager.register_event(older, {KEY})
    assert manager.project_status(doc).status == DocumentStatus.SUBSTITUTED


def test_abrasf_event_match_is_unambiguous_and_request_does_not_cancel():
    content = b'''<CancelarNfseEnvio><InfPedidoCancelamento><IdentificacaoNfse><Numero>001</Numero>
        <Cnpj>00111222000133</Cnpj><CodigoMunicipio>3106200</CodigoMunicipio></IdentificacaoNfse>
        <DataHora>2026-03-01T10:00:00</DataHora></InfPedidoCancelamento></CancelarNfseEnvio>'''
    state = process_nfse_batch([('pedido.xml', content), ('nota.xml', abrasf())])
    assert len(state.events) == 1
    assert not state.events[0].confirmed
    assert not state.orphan_events
    assert state.documents[0].status == DocumentStatus.AUTHORIZED
