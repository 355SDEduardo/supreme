"""NFS-e exports with calculation memory, events and safe spreadsheet cells."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from svc_nfse_engine.multilayout.nfse_models import NfseProcessingState
from svc_nfse_engine.multilayout.nfse_parser_abrasf import federal_total
from svc_nfse_engine.multilayout.nfse_rules_engine import effective_iss_withheld

NOTE_COLUMNS = [
    ('filename', 'Arquivo Origem'), ('access_key', 'Chave de Acesso'), ('number', 'Número NFS-e'),
    ('series', 'Série'), ('competence', 'Competência'), ('issued', 'Data Processamento / Emissão'),
    ('status', 'Status Projetado'), ('family', 'Família de Schema'), ('provider_id', 'CNPJ/CPF Prestador'),
    ('provider_name', 'Razão Social Prestador'), ('provider_city', 'Município Prestador (IBGE)'),
    ('regime', 'Regime Tributário Prestador'), ('customer_id', 'CNPJ/CPF Tomador'),
    ('customer_name', 'Razão Social Tomador'), ('subitems', 'Subitem LC 116'),
    ('gross', 'Valor Bruto Serviços (R$)'), ('discounts', 'Descontos (R$)'),
    ('base', 'Base de Cálculo ISS (R$)'), ('rate', 'Alíquota ISS (%)'), ('iss', 'Valor ISS (R$)'),
    ('retention', 'Tipo Retenção ISS'), ('iss_withheld', 'ISS Retido (R$)'),
    ('federal', 'Total Retenções Federais (R$)'), ('net_declared', 'Valor Líquido Declarado (R$)'),
    ('net_calculated', 'Valor Líquido Calculado (R$)'), ('difference', 'Divergência Líquido (R$)'),
    ('findings', 'Qtd Apontamentos'), ('kind', 'Tipo Documento'), ('sha256', 'SHA-256 Original'),
    ('cancelled_at', 'Data Cancelamento / Substituição')]
FINDING_COLUMNS = [('access_key', 'Chave da Nota'), ('number', 'Número NFS-e'), ('provider', 'Prestador'),
    ('severity', 'Severidade'), ('code', 'Código do Apontamento'), ('title', 'Título da Ocorrência'),
    ('description', 'Descrição e Fatos Observados'), ('reported', 'Valor Reportado no XML'),
    ('expected', 'Valor Esperado'), ('difference', 'Diferença'), ('legal_basis', 'Fundamentação Legal')]


def nfse_note_rows(state: NfseProcessingState) -> list[dict[str, Any]]:
    rows = []
    for d in state.documents:
        a = d.amounts
        status_events = [e for e in state.events if e.target_access_key == d.identity.access_key
                         and e.confirmed and e.event_type in {'CANCELAMENTO', 'SUBSTITUICAO'}]
        rows.append(dict(filename=d.filename, access_key=d.identity.access_key, number=d.identity.nfse_number,
            series=d.identity.series, competence=d.identity.competence_date.isoformat() if d.identity.competence_date else '',
            issued=d.identity.nfse_issued_at.isoformat() if d.identity.nfse_issued_at else '',
            status=d.status.value, family=d.family.value, provider_id=d.provider.tax_id,
            provider_name=d.provider.name, provider_city=d.provider.ibge_city_code,
            regime='MEI' if d.provider.is_mei else 'Simples Nacional' if d.provider.is_simple_national else 'Normal' if d.provider.is_simple_national is False else 'Não informado',
            customer_id=d.customer.tax_id if d.customer else '', customer_name=d.customer.name if d.customer else '',
            subitems=', '.join(s.lc116_subitem for s in d.services), gross=a.gross_service,
            discounts=a.unconditional_discount + a.conditional_discount, base=a.iss_base,
            rate=a.iss_rate_applied if a.iss_rate_applied is not None else a.iss_rate_declared,
            iss=a.iss_amount, retention=d.iss_withholding_type.name, iss_withheld=effective_iss_withheld(d),
            federal=federal_total(d.federal_withholding), net_declared=a.net_amount_declared,
            net_calculated=a.net_amount_calculated, difference=a.net_difference, findings=len(d.findings),
            kind=d.kind.value, sha256=d.artifact_sha256,
            cancelled_at=', '.join(e.event_datetime.isoformat() for e in status_events)))
    return rows


def nfse_finding_rows(state: NfseProcessingState) -> list[dict[str, Any]]:
    return [{'access_key': d.identity.access_key, 'number': d.identity.nfse_number, 'provider': d.provider.name,
             **f.to_dict(), 'difference': f.difference} for d in state.documents for f in d.findings]


def severity_counts(state: NfseProcessingState) -> dict[str, int]:
    return dict(Counter(f.severity.value for d in state.documents for f in d.findings))


def build_nfse_json_payload(state: NfseProcessingState) -> dict[str, Any]:
    payload = state.to_dict()
    payload['severity_counts'] = severity_counts(state)
    payload['totals_scope'] = 'NFS-e autorizadas vigentes; DPS, canceladas e substituídas excluídas dos totais financeiros.'
    payload['signature_validation'] = 'Não executada: SHA-256 comprova integridade dos bytes recebidos, não autenticidade fiscal.'
    return payload


def _safe_csv(value: object) -> str:
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def _csv(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    output = StringIO(newline='')
    writer = csv.writer(output, delimiter=';')
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_safe_csv(row.get(key)) for key, _ in columns])
    return '\ufeff' + output.getvalue()


def generate_nfse_csv_notes(state: NfseProcessingState) -> str:
    return _csv(nfse_note_rows(state), NOTE_COLUMNS)


def generate_nfse_csv_findings(state: NfseProcessingState) -> str:
    return _csv(nfse_finding_rows(state), FINDING_COLUMNS)


def generate_nfse_excel_report(state: NfseProcessingState) -> BytesIO:
    workbook = Workbook()
    workbook.remove(workbook.active)

    def sheet(title: str, rows: list[dict[str, Any]], columns: list[tuple[str, str]]):
        ws = workbook.create_sheet(title)
        ws.append([label for _, label in columns])
        for row in rows:
            ws.append([row.get(key, '') for key, _ in columns])
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                    cell.number_format = '@'
                elif isinstance(cell.value, Decimal):
                    cell.number_format = '"R$" #,##0.00'
        for cell in ws[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='17394F')
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for index in range(1, len(columns) + 1):
            values = [len(str(ws.cell(row, index).value or '')) for row in range(1, min(ws.max_row, 51) + 1)]
            ws.column_dimensions[get_column_letter(index)].width = min(60, max(values, default=10) + 3)
        return ws

    summary = [dict(label='Sistema', value='st_difal_web - Módulo NFS-e'),
        dict(label='Extraído em', value=datetime.now().isoformat(timespec='seconds')),
        dict(label='Escopo financeiro', value='Somente NFS-e autorizadas vigentes'),
        dict(label='XMLs inspecionados', value=state.total_processed),
        dict(label='Documentos normalizados', value=state.total_valid),
        dict(label='Notas com apontamentos', value=state.total_with_findings),
        dict(label='Bruto vigente', value=state.total_gross_amount),
        dict(label='ISS apurado vigente', value=state.total_iss_amount),
        dict(label='ISS retido vigente', value=state.total_iss_withheld),
        dict(label='Retenções federais vigentes', value=state.total_federal_withheld),
        dict(label='Líquido auditado vigente', value=state.total_net_amount)]
    active = [d for d in state.documents if d.kind.value == 'NFSE' and d.status.value == 'AUTHORIZED']
    summary.extend([dict(label='Deduções vigentes', value=sum((d.amounts.deductions for d in active), Decimal('0.00'))),
        dict(label='Descontos vigentes', value=sum((d.amounts.unconditional_discount + d.amounts.conditional_discount for d in active), Decimal('0.00'))),
        dict(label='Base de ISS vigente', value=sum((d.amounts.iss_base for d in active), Decimal('0.00')))])
    for group, counts in (('Família', Counter(d.family.value for d in state.documents)),
                          ('Status', Counter(d.status.value for d in state.documents)),
                          ('Severidade', severity_counts(state))):
        summary.extend(dict(label=f'{group}: {key}', value=count) for key, count in counts.items())
    sheet('Resumo Executivo', summary, [('label', 'Indicador'), ('value', 'Valor')])
    notes = sheet('Notas Auditadas', nfse_note_rows(state), NOTE_COLUMNS)
    rate_column = next(i for i, (key, _) in enumerate(NOTE_COLUMNS, 1) if key == 'rate')
    for index, row in enumerate(nfse_note_rows(state), 2):
        if row['rate'] is not None:
            notes.cell(index, rate_column, row['rate'] / 100).number_format = '0.00%'
        if row['difference'] != 0:
            notes.cell(index, 26).font = Font(color='9C0006', bold=True)
    findings = nfse_finding_rows(state)
    finding_sheet = sheet('Apontamentos Fiscais', findings, FINDING_COLUMNS)
    colors = {'CRITICAL': 'FFC7CE', 'HIGH': 'FCE4D6', 'WARNING': 'FFF2CC', 'INFO': 'DDEBF7'}
    for index, row in enumerate(findings, 2):
        finding_sheet.cell(index, 4).fill = PatternFill('solid', fgColor=colors[row['severity']])
    if not findings:
        finding_sheet.append(['Nenhum apontamento fiscal detectado nas regras verificadas.'])
    retention_rows = [dict(access_key=d.identity.access_key, number=d.identity.nfse_number,
        provider=d.provider.name, simple=str(d.provider.is_simple_national),
        **d.federal_withholding.__dict__, iss_withheld=effective_iss_withheld(d),
        declared=d.amounts.total_withheld,
        risk=any(f.code == 'SIMPLES_FEDERAL_WITHHOLDING_UNDUE' for f in d.findings)) for d in state.documents]
    sheet('Retenções Tributárias', retention_rows, [('access_key', 'Chave da Nota'), ('number', 'Número'),
        ('provider', 'Prestador'), ('simple', 'Optante Simples'), ('irrf', 'IRRF'), ('inss_cp', 'INSS/CP'),
        ('csll', 'CSLL'), ('pis', 'PIS'), ('cofins', 'COFINS'), ('other_withholdings', 'Outras Retenções'),
        ('social_contributions_total', 'Contribuições Sociais Retidas (NT007)'),
        ('pis_own', 'PIS Próprio'), ('cofins_own', 'COFINS Próprio'), ('social_retention_type', 'Tipo Retenção Social'),
        ('iss_withheld', 'ISS Retido'), ('declared', 'Total Retido Declarado'), ('risk', 'Risco de Retenção Indevida')])
    rtc_rows = [dict(access_key=d.identity.access_key, number=d.identity.nfse_number, **d.ibs_cbs.__dict__)
                for d in state.documents if d.ibs_cbs]
    rtc = sheet('Reforma Tributária (IBS-CBS)', rtc_rows, [('access_key', 'Chave da Nota'), ('number', 'Número'),
        ('cst', 'CST IBS/CBS'), ('c_class_trib', 'Classificação Tributária'), ('tax_base', 'Base IBS/CBS'),
        ('ibs_state_rate', 'Alíquota IBS UF (%)'), ('ibs_state_amount', 'IBS UF'),
        ('ibs_city_rate', 'Alíquota IBS Município (%)'), ('ibs_city_amount', 'IBS Município'),
        ('cbs_rate', 'Alíquota CBS (%)'), ('cbs_amount', 'CBS'), ('total_ibs', 'Total IBS'),
        ('total_cbs', 'Total CBS'), ('total_nf', 'Total Geral Nota')])
    for row in range(2, rtc.max_row + 1):
        for column in (6, 8, 10):
            rtc.cell(row, column).number_format = '0.00"%"'
    if not rtc_rows:
        rtc.append(['Nenhum documento com tributação RTC / IBS-CBS identificado neste lote.'])
    provenance_rows = [dict(access_key=d.identity.access_key, **p.to_dict()) for d in state.documents for p in d.provenance]
    provenance = sheet('Trilha de Proveniência', provenance_rows[:5000], [('access_key', 'Chave da Nota'),
        ('canonical_field', 'Campo Canônico'), ('source_xpath', 'XPath no XML Original'),
        ('raw_value', 'Valor Bruto Texto'), ('normalized_value', 'Valor Normalizado'),
        ('source_schema', 'Schema'), ('transformation_rule', 'Regra de Transformação')])
    if len(provenance_rows) > 5000:
        provenance.append(['Limite de 5.000 registros no Excel. JSON contém a trilha completa.'])
    sheet('Eventos Fiscais', [e.to_dict() for e in state.events], [('event_id', 'ID Evento'),
        ('target_access_key', 'Chave Alvo'), ('event_type', 'Tipo'), ('event_datetime', 'Data Registro'),
        ('reason', 'Motivo'), ('substituting_access_key', 'Chave Substituta'), ('confirmed', 'Confirmado'),
        ('raw_payload_sha256', 'SHA-256')])
    sheet('Ocorrências de Leitura', state.issues, [('filename', 'Arquivo'), ('message', 'Ocorrência'), ('sha256', 'SHA-256')])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
