from dataclasses import replace
from datetime import date
from decimal import Decimal
import xml.etree.ElementTree as ET

import pytest

from svc_nfse_engine.multilayout.nfse_models import FindingSeverity
from svc_nfse_engine.multilayout.nfse_parser_national import NationalNfseParser
from svc_nfse_engine.multilayout.nfse_rules_engine import NfseRulesEngine, calculated_net
from .nfse_samples import national


def document(**kwargs):
    return NationalNfseParser().parse(ET.fromstring(national(**kwargs)), 'hash', 'nota.xml')


def codes(doc):
    return {f.code for f in NfseRulesEngine().audit_document(doc)}


def test_iss_not_withheld_does_not_reduce_net_and_tolerance():
    doc = document()
    assert calculated_net(doc) == Decimal('9750.00')
    assert 'ARITHMETIC_NET_AMOUNT_MISMATCH' not in codes(doc)
    assert 'ARITHMETIC_NET_AMOUNT_MISMATCH' in codes(document(net='9250.00'))
    assert 'ARITHMETIC_NET_AMOUNT_MISMATCH' not in codes(document(net='9750.02'))
    assert 'ARITHMETIC_NET_AMOUNT_MISMATCH' in codes(document(net='9750.03'))


@pytest.mark.parametrize('retention', ['2', '3'])
def test_withheld_iss_reduces_net(retention):
    doc = document(retention=retention, net='9250.00')
    assert calculated_net(doc) == Decimal('9250.00')
    assert 'ARITHMETIC_NET_AMOUNT_MISMATCH' not in codes(doc)


def test_iss_incidence_for_construction_and_item_12_13_general_rule():
    assert 'ISS_INCIDENCE_LOCATION_DIVERGENCE' in codes(document(subcode='070201', execution='3106200'))
    assert 'ISS_INCIDENCE_LOCATION_DIVERGENCE' not in codes(document(subcode='070201', execution='3106200', incidence='3106200'))
    assert 'ISS_INCIDENCE_LOCATION_DIVERGENCE' not in codes(document(subcode='121301', execution='3106200'))


@pytest.mark.parametrize(('rate', 'code'), [('6.00', 'ISS_RATE_ABOVE_STATUTORY_MAXIMUM'),
    ('1.50', 'ISS_RATE_BELOW_STATUTORY_MINIMUM')])
def test_iss_rate_bounds(rate, code):
    assert code in codes(document(rate=rate))


def test_iss_minimum_exceptions_simple_and_transition():
    assert 'ISS_RATE_BELOW_STATUTORY_MINIMUM' not in codes(document(rate='1.50', subcode='070201'))
    assert 'ISS_RATE_BELOW_STATUTORY_MINIMUM' not in codes(document(rate='1.50', simple='3'))
    doc = document(rate='4.60')
    doc = replace(doc, identity=replace(doc.identity, competence_date=date(2029, 3, 1)))
    assert 'ISS_RATE_ABOVE_STATUTORY_MAXIMUM' in codes(doc)
    doc = replace(doc, amounts=replace(doc.amounts, iss_rate_applied=Decimal('4.50')))
    assert 'ISS_RATE_ABOVE_STATUTORY_MAXIMUM' not in codes(doc)


def test_simples_retention_is_not_blanket_prohibited_and_inss_is_independent():
    lawful = document(simple='3', retention='2', subcode='070201', net='9250.00')
    assert 'SIMPLES_ISS_RETENTION_UNWARRANTED' not in codes(lawful)
    assert 'SIMPLES_FEDERAL_WITHHOLDING_UNDUE' in codes(lawful)
    local_review = document(simple='3', retention='2', net='9250.00')
    finding = next(f for f in NfseRulesEngine().audit_document(local_review) if f.code == 'SIMPLES_ISS_RETENTION_UNWARRANTED')
    assert finding.severity == FindingSeverity.WARNING
    doc = replace(lawful, federal_withholding=replace(lawful.federal_withholding,
        irrf=Decimal('0'), csll=Decimal('0'), inss_cp=Decimal('100')))
    assert 'SIMPLES_FEDERAL_WITHHOLDING_UNDUE' not in codes(doc)


def test_customer_rtc_and_calculation_memory():
    doc = replace(document(gross='50000.00', rtc=True), customer=None)
    assert 'HIGH_VALUE_UNIDENTIFIED_CUSTOMER' in codes(doc)
    assert 'RTC_IBS_CBS_CALCULATION_MISMATCH' not in codes(doc)
    bad = replace(doc, ibs_cbs=replace(doc.ibs_cbs, total_ibs=Decimal('500')))
    assert 'RTC_IBS_CBS_CALCULATION_MISMATCH' in codes(bad)
    enriched = NfseRulesEngine().enrich_document(doc)
    assert enriched.amounts.net_amount_calculated == calculated_net(doc)
    assert enriched.amounts.net_difference == enriched.amounts.net_amount_declared - calculated_net(doc)


def test_negative_values_are_critical():
    doc = document()
    doc = replace(doc, amounts=replace(doc.amounts, gross_service=Decimal('-1')))
    assert any(f.code == 'NEGATIVE_FISCAL_AMOUNT' and f.severity == FindingSeverity.CRITICAL
               for f in NfseRulesEngine().audit_document(doc))


def test_rtc_effective_rates_and_complex_adjustments():
    doc = document(rtc=True)
    doc = replace(doc, ibs_cbs=replace(doc.ibs_cbs, cbs_rate=Decimal('1.8'), cbs_effective_rate=Decimal('.9')))
    assert 'RTC_IBS_CBS_CALCULATION_MISMATCH' not in codes(doc)
    doc = replace(doc, ibs_cbs=replace(doc.ibs_cbs, has_complex_adjustments=True, total_cbs=Decimal('1')))
    assert 'RTC_COMPLEX_ADJUSTMENTS_REVIEW' in codes(doc)
    assert 'RTC_IBS_CBS_CALCULATION_MISMATCH' not in codes(doc)
