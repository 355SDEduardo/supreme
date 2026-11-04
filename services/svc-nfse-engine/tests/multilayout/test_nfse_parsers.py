from decimal import Decimal
import xml.etree.ElementTree as ET

import pytest

from svc_nfse_engine.multilayout.nfse_models import DocumentKind, DocumentStatus, IssWithholdingType
from svc_nfse_engine.multilayout.nfse_parser_national import NationalNfseParser
from svc_nfse_engine.multilayout.nfse_parser_abrasf import AbrasfNfseParser
from svc_nfse_engine.multilayout.nfse_parser_municipal import PaulistanaNfseParser, HeuristicFallbackParser
from svc_nfse_engine.multilayout.nfse_pipeline import process_nfse_batch
from .nfse_samples import KEY, national, abrasf, paulistana


def test_national_scopes_identity_times_parties_and_provenance():
    document = NationalNfseParser().parse(ET.fromstring(national(rtc=True)), 'hash', 'nota.xml')
    assert document.issuer.tax_id == '00000000000100'
    assert document.provider.tax_id == '12ABC34501DE35'
    assert document.customer.tax_id == '00111222000133'
    assert document.identity.nfse_issued_at.hour == 14
    assert document.identity.dps_issued_at.hour == 10
    assert document.identity.access_key == KEY and document.identity.xml_id == 'NFS' + KEY
    assert document.amounts.gross_service == Decimal('10000.00')
    assert document.amounts.iss_base == Decimal('10000.00')
    assert document.ibs_cbs.tax_base == Decimal('10000.00')
    assert document.ibs_cbs.total_ibs == Decimal('20.00')
    assert any(p.canonical_field == 'amounts.iss_base' and '}valores' in p.source_xpath for p in document.provenance)


@pytest.mark.parametrize(('code', 'expected'), [('1', IssWithholdingType.NAO_RETIDO),
    ('2', IssWithholdingType.RETIDO_TOMADOR), ('3', IssWithholdingType.RETIDO_INTERMEDIARIO)])
def test_official_tpretissqn_domain(code, expected):
    doc = NationalNfseParser().parse(ET.fromstring(national(retention=code)), 'hash', 'a.xml')
    assert doc.iss_withholding_type == expected


@pytest.mark.parametrize(('code', 'simple', 'mei'), [('1', False, False), ('2', True, True), ('3', True, False), ('4', None, None)])
def test_official_simple_domain(code, simple, mei):
    doc = NationalNfseParser().parse(ET.fromstring(national(simple=code)), 'hash', 'a.xml')
    assert doc.provider.is_simple_national is simple
    assert doc.provider.is_mei is mei


def test_dps_standalone_is_not_authorized_and_not_financial_total():
    root = ET.fromstring(national())
    dps = next(n for n in root.iter() if n.tag.endswith('}DPS'))
    state = process_nfse_batch([('dps.xml', ET.tostring(dps))])
    assert len(state.documents) == 1
    assert state.documents[0].kind == DocumentKind.DPS
    assert state.documents[0].status == DocumentStatus.UNKNOWN
    assert state.total_gross_amount == 0
    assert any(f.code == 'DPS_NOT_AUTHORIZED' for f in state.documents[0].findings)


@pytest.mark.parametrize('rate', ['0.05', '5.00'])
def test_abrasf_rates_and_multi_service_totals(rate):
    document = AbrasfNfseParser().parse(ET.fromstring(abrasf(rate=rate, multiple=True)), 'hash', 'nota.xml')
    assert document.amounts.iss_rate_declared == Decimal('5.00')
    assert len(document.services) == 2
    assert document.services[0].lc116_subitem == '01.07'
    assert document.amounts.gross_service == Decimal('10000.00')
    assert document.federal_withholding.irrf == Decimal('150.00')


def test_abrasf_embedded_cancellation_uses_event_projection():
    state = process_nfse_batch([('a.xml', abrasf(cancelled=True))])
    assert state.documents[0].status == DocumentStatus.CANCELLED
    assert len(state.events) == 1
    assert state.total_gross_amount == 0


def test_paulistana_identifier_rates_and_taxes():
    doc = PaulistanaNfseParser().parse(ET.fromstring(paulistana()), 'hash', 'sp.xml')
    assert doc.identity.access_key == '35503080012300045ABC123'
    assert doc.amounts.iss_rate_applied == Decimal('5.00')
    assert doc.iss_withholding_type == IssWithholdingType.NAO_RETIDO
    assert doc.federal_withholding.cofins == Decimal('450.00')


def test_fallback_decimal_comma_and_safe_unknown_rejection():
    content = b'<NotaServico><Numero>0001</Numero><ValorServicos>1.250,50</ValorServicos></NotaServico>'
    doc = HeuristicFallbackParser().parse(ET.fromstring(content), 'hash', 'a.xml')
    assert doc.amounts.gross_service == Decimal('1250.50')
    assert doc.identity.access_key.startswith('SYNTH_')
    assert doc.findings[0].code == 'SCHEMA_UNKNOWN_HEURISTIC_PARSED'
    with pytest.raises(ValueError):
        HeuristicFallbackParser().parse(ET.fromstring('<Anything/>'), 'hash', 'a.xml')


@pytest.mark.parametrize(('code', 'retained'), [('1', '365.00'), ('2', '0.00'), ('3', '0.00'), ('0', '0.00')])
def test_national_social_retention_domain_avoids_double_counting(code, retained):
    from svc_nfse_engine.multilayout.nfse_parser_abrasf import federal_total
    content = national().replace(b'<vRetCSLL>100.00</vRetCSLL>',
        f'<vRetCSLL>100.00</vRetCSLL><piscofins><tpRetPisCofins>{code}</tpRetPisCofins><vPis>65.00</vPis><vCofins>300.00</vCofins></piscofins>'.encode())
    doc = NationalNfseParser().parse(ET.fromstring(content), 'hash', 'a.xml')
    assert doc.federal_withholding.pis_own == Decimal('65.00')
    assert doc.federal_withholding.pis + doc.federal_withholding.cofins == Decimal(retained)
    assert federal_total(doc.federal_withholding) == Decimal('250.00') + Decimal(retained)
    pis_provenance = next(p for p in doc.provenance if p.canonical_field == 'federal_withholding.pis')
    assert Decimal(pis_provenance.normalized_value) == doc.federal_withholding.pis


def test_national_rtc_declared_classification_and_assessed_amounts_remain_scoped():
    content = national(rtc=True).replace(b'</infDPS>', b'<IBSCBS><cIndOp>100501</cIndOp><valores><trib><gIBSCBS><CST>200</CST><cClassTrib>200001</cClassTrib><vBC>1.00</vBC></gIBSCBS></trib></valores></IBSCBS></infDPS>')
    doc = NationalNfseParser().parse(ET.fromstring(content), 'hash', 'a.xml')
    assert doc.ibs_cbs.cst == '200'
    assert doc.ibs_cbs.tax_base == Decimal('10000.00')
    assert doc.ibs_cbs.ind_op == '100501'
def test_abrasf_provider_identity_and_name_in_separate_blocks():
    from .nfse_samples import abrasf
    from svc_nfse_engine.multilayout.nfse_pipeline import process_nfse_batch
    raw = abrasf().replace(b'<OrgaoGerador>',
        b'<PrestadorServico><RazaoSocial>Nome cadastral</RazaoSocial></PrestadorServico><OrgaoGerador>')
    state = process_nfse_batch([('nota.xml', raw)])
    assert not state.issues
    note = state.documents[0]
    assert note.provider.tax_id == '00111222000133'
    assert note.provider.name == 'Nome cadastral'
    assert '00111222000133' in note.identity.access_key

