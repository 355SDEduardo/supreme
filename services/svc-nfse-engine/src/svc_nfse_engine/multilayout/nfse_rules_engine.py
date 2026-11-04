"""Decimal accounting checks and dated fiscal screening rules.

Local tax responsibility and benefits require evidence beyond an XML. Those
checks are warnings rather than a claim that a municipality's levy is invalid.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re

from svc_nfse_engine.multilayout.nfse_models import (
    CanonicalNfse, DocumentKind, FindingSeverity, IssWithholdingType, NfseFinding,
)
from svc_nfse_engine.multilayout.nfse_parser_abrasf import federal_total

ZERO = Decimal('0.00')
CENT = Decimal('0.01')
EXECUTION_SUBITEMS = {'03.05', '07.02', '07.04', '07.05', '07.09', '07.10', '07.11',
    '07.12', '07.16', '07.17', '07.18', '07.19', '11.01', '11.02', '11.04',
    '16.01', '16.02', '17.10', '20.01', '20.02', '20.03'} | {f'12.{n:02d}' for n in range(1, 18) if n != 13}
MINIMUM_EXCEPTIONS = {'07.02', '07.05', '16.01'}
RETENTION_TYPES = {IssWithholdingType.RETIDO_TOMADOR, IssWithholdingType.RETIDO_INTERMEDIARIO}


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def effective_iss_withheld(document: CanonicalNfse) -> Decimal:
    if document.iss_withholding_type in RETENTION_TYPES:
        return document.amounts.iss_withheld_amount or document.amounts.iss_amount
    return ZERO


def calculated_net(document: CanonicalNfse) -> Decimal:
    amounts = document.amounts
    return money(amounts.gross_service - amounts.unconditional_discount - amounts.conditional_discount
                 - federal_total(document.federal_withholding) - effective_iss_withheld(document))


class NfseRulesEngine:
    def __init__(self, tolerance: Decimal = Decimal('0.02')):
        self.tolerance = tolerance

    def audit_document(self, document: CanonicalNfse) -> list[NfseFinding]:
        findings: list[NfseFinding] = []

        def report(code: str, severity: FindingSeverity, title: str, description: str,
                   expected: object = '', reported: object = '', difference: Decimal = ZERO,
                   legal_basis: str = '', source_fields: tuple[str, ...] = ()) -> None:
            findings.append(NfseFinding(code, severity, title, description, str(expected),
                str(reported), difference, legal_basis, source_fields))

        if not document.provider.tax_id:
            report('MISSING_PROVIDER_ID', FindingSeverity.HIGH, 'Prestador sem CPF/CNPJ',
                   'Identificação fiscal obrigatória não encontrada.', 'CPF/CNPJ', '', legal_basis='Auditoria documental')
        elif not re.fullmatch(r'(?:[0-9]{11}|[A-Z0-9]{12}[0-9]{2})', document.provider.tax_id):
            report('INVALID_PROVIDER_ID_FORMAT', FindingSeverity.WARNING, 'Formato do CPF/CNPJ incomum',
                   'Conferir identificação fiscal do prestador.', 'CPF (11) ou CNPJ (14)', document.provider.tax_id)
        if document.kind == DocumentKind.DPS:
            report('DPS_NOT_AUTHORIZED', FindingSeverity.INFO, 'DPS avulsa',
                   'Declaração sem NFS-e autorizada: excluída dos totais financeiros do lote.')
            return findings
        if document.family.value == 'NATIONAL' and not re.fullmatch(r'[0-9]{50}', document.identity.access_key):
            report('INVALID_NATIONAL_ACCESS_KEY', FindingSeverity.HIGH, 'Chave nacional inválida',
                   'A chave nacional deve conter 50 dígitos sem prefixo NFS.', '50 dígitos', document.identity.access_key)
        if document.identity.competence_date is None:
            report('MISSING_COMPETENCE_DATE', FindingSeverity.WARNING, 'Competência não informada',
                   'Regras por vigência não podem ser integralmente avaliadas.')
        a = document.amounts
        federal_values = tuple(value for value in document.federal_withholding.__dict__.values() if isinstance(value, Decimal))
        if any(value < ZERO for value in (a.gross_service, a.iss_base, a.iss_amount, a.deductions,
                a.conditional_discount, a.unconditional_discount, *federal_values)):
            report('NEGATIVE_FISCAL_AMOUNT', FindingSeverity.CRITICAL, 'Valor fiscal negativo',
                   'Conferir os valores monetários declarados.', 'Valores >= 0', 'Valor negativo')
        expected_net = calculated_net(document)
        difference = money(a.net_amount_declared - expected_net)
        if abs(difference) > self.tolerance:
            report('ARITHMETIC_NET_AMOUNT_MISMATCH', FindingSeverity.HIGH, 'Divergência no valor líquido',
                   'Líquido = serviços - descontos - retenções efetivas. ISS próprio não reduz o líquido.',
                   expected_net, a.net_amount_declared, difference, 'Auditoria contábil',
                   ('amounts.net_amount_declared', 'iss_withholding_type', 'federal_withholding'))
        effective_ret = federal_total(document.federal_withholding) + effective_iss_withheld(document)
        if abs(a.total_withheld - effective_ret) > self.tolerance:
            report('TOTAL_WITHHOLDINGS_MISMATCH', FindingSeverity.HIGH, 'Total de retenções divergente',
                   'Soma das retenções efetivas difere do total declarado.', effective_ret, a.total_withheld,
                   a.total_withheld - effective_ret, 'Auditoria contábil', ('amounts.total_withheld',))
        if document.iss_withholding_type == IssWithholdingType.NAO_INFORMADO:
            report('ISS_WITHHOLDING_UNKNOWN', FindingSeverity.WARNING, 'Retenção de ISS não identificada',
                   'O cálculo não presume retenção. Conferir a natureza do ISS no XML.')
        elif document.iss_withholding_type == IssWithholdingType.NAO_RETIDO and a.iss_withheld_amount > ZERO:
            report('ISS_WITHHOLDING_CONFLICT', FindingSeverity.HIGH, 'ISS retido contradiz indicador',
                   'Valor de retenção positivo com indicador de não retenção.', ZERO, a.iss_withheld_amount)
        rate = a.iss_rate_applied if a.iss_rate_applied is not None else a.iss_rate_declared
        if rate is not None and a.iss_base > ZERO:
            expected_iss = money(a.iss_base * rate / 100)
            if abs(a.iss_amount - expected_iss) > self.tolerance:
                report('ISS_AMOUNT_CALCULATION_MISMATCH', FindingSeverity.HIGH, 'Cálculo do ISS divergente',
                       'ISS apurado difere de base × alíquota / 100.', expected_iss, a.iss_amount,
                       a.iss_amount - expected_iss, 'Auditoria contábil', ('amounts.iss_base', 'amounts.iss_rate_applied'))
        competence = document.identity.competence_date
        year = competence.year if competence else None
        factor = {2029: Decimal('.9'), 2030: Decimal('.8'), 2031: Decimal('.7'), 2032: Decimal('.6')}.get(year, Decimal('1'))
        if rate is not None and year is not None and year <= 2032:
            maximum = Decimal('5') * factor
            if rate > maximum:
                report('ISS_RATE_ABOVE_STATUTORY_MAXIMUM', FindingSeverity.CRITICAL, 'ISS acima do máximo legal',
                       'Alíquota ultrapassa o teto da competência.', maximum, rate, rate - maximum,
                       'LC 116/2003, arts. 8º e 8º-B', ('amounts.iss_rate_applied',))
            if rate > ZERO and rate < Decimal('2') * factor and not document.provider.is_simple_national and not all(s.lc116_subitem in MINIMUM_EXCEPTIONS for s in document.services):
                report('ISS_RATE_BELOW_STATUTORY_MINIMUM', FindingSeverity.HIGH, 'ISS abaixo do mínimo legal',
                       'Conferir benefícios e exceções aplicáveis.', Decimal('2') * factor, rate,
                       legal_basis='LC 116/2003, arts. 8º-A e 8º-B')
        for service in document.services:
            exceptions = EXECUTION_SUBITEMS | ({'14.14'} if competence and competence >= date(2025, 9, 25) else set())
            expected_city = (document.customer.ibge_city_code if document.customer else '') if service.lc116_subitem == '17.05' else service.execution_city_ibge if service.lc116_subitem in exceptions else document.provider.ibge_city_code
            if service.lc116_subitem and expected_city and service.incidence_city_ibge and expected_city != service.incidence_city_ibge:
                report('ISS_INCIDENCE_LOCATION_DIVERGENCE', FindingSeverity.HIGH, 'Município de incidência divergente',
                       f'Subitem {service.lc116_subitem}: conferir local legal da incidência.', expected_city,
                       service.incidence_city_ibge, legal_basis='LC 116/2003, art. 3º; LC 218/2025')
        if document.provider.is_simple_national:
            f = document.federal_withholding
            social = f.social_contributions_total if f.social_contributions_total is not None else f.pis + f.cofins + f.csll
            if f.irrf + social > ZERO:
                report('SIMPLES_FEDERAL_WITHHOLDING_UNDUE', FindingSeverity.HIGH, 'Retenção federal no Simples Nacional',
                       'IRRF/PIS/COFINS/CSLL são dispensados sobre receitas próprias. Conferir o enquadramento; INSS tem regra própria.',
                       ZERO, f.irrf + social, legal_basis='IN RFB 765/2007; IN SRF 459/2004')
            if document.iss_withholding_type in RETENTION_TYPES:
                if not any(s.lc116_subitem in EXECUTION_SUBITEMS | {'17.05', '14.14'} for s in document.services):
                    report('SIMPLES_ISS_RETENTION_UNWARRANTED', FindingSeverity.WARNING, 'Conferir responsabilidade pela retenção de ISS',
                           'O XML não demonstra hipótese do art. 3º; verificar também a lei municipal de responsabilidade do art. 6º.',
                           legal_basis='CGSN 140/2018, art. 27; LC 116/2003, arts. 3º e 6º')
                if a.iss_rate_declared is not None and rate is not None and rate > a.iss_rate_declared:
                    report('SIMPLES_ISS_RETENTION_RATE_DISCREPANCY', FindingSeverity.WARNING, 'Alíquota retida difere da declarada',
                           'Conferir percentual efetivo informado pelo prestador.', a.iss_rate_declared, rate,
                           legal_basis='CGSN 140/2018, art. 27')
        if a.gross_service > Decimal('10000') and (document.customer is None or not document.customer.tax_id):
            report('HIGH_VALUE_UNIDENTIFIED_CUSTOMER', FindingSeverity.WARNING, 'Nota de alto valor sem CPF/CNPJ do tomador',
                   'Tomador não identificado: conferir documentação cadastral.')
        rtc = document.ibs_cbs
        if rtc and competence and year >= 2026:
            if rtc.cst not in {'000', '010', '011', '200', '220', '221', '222', '400', '410', '510', '550', '620', '800', '810', '820', '830'}:
                report('RTC_INVALID_CST', FindingSeverity.WARNING, 'CST IBS/CBS não catalogado',
                       'Conferir CST na tabela vigente para a competência.', 'CST IBS/CBS catalogado', rtc.cst, legal_basis='Leiaute RTC IBS/CBS')
            uf_rate = rtc.ibs_state_effective_rate if rtc.ibs_state_effective_rate is not None else rtc.ibs_state_rate
            city_rate = rtc.ibs_city_effective_rate if rtc.ibs_city_effective_rate is not None else rtc.ibs_city_rate
            cbs_rate = rtc.cbs_effective_rate if rtc.cbs_effective_rate is not None else rtc.cbs_rate
            expected_ibs = money(rtc.tax_base * uf_rate / 100) + money(rtc.tax_base * city_rate / 100)
            expected_cbs = money(rtc.tax_base * cbs_rate / 100)
            if rtc.has_complex_adjustments:
                report('RTC_COMPLEX_ADJUSTMENTS_REVIEW', FindingSeverity.WARNING, 'Ajustes RTC exigem conferência complementar',
                       'Diferimentos, devoluções, créditos ou tributação regular não são validados pela fórmula básica.', legal_basis='Leiaute RTC IBS/CBS')
            elif abs(expected_ibs - rtc.total_ibs) > self.tolerance or abs(expected_cbs - rtc.total_cbs) > self.tolerance:
                report('RTC_IBS_CBS_CALCULATION_MISMATCH', FindingSeverity.HIGH, 'Totalizadores IBS/CBS divergentes',
                       'Conferência aritmética básica; reduções, diferimentos e créditos exigem análise complementar.',
                       f'IBS={expected_ibs}; CBS={expected_cbs}', f'IBS={rtc.total_ibs}; CBS={rtc.total_cbs}', legal_basis='Leiaute RTC IBS/CBS')
        return findings

    def enrich_document(self, document: CanonicalNfse) -> CanonicalNfse:
        net = calculated_net(document)
        return replace(document, amounts=replace(document.amounts, net_amount_calculated=net,
            net_difference=money(document.amounts.net_amount_declared - net)),
            findings=document.findings + tuple(self.audit_document(document)))
