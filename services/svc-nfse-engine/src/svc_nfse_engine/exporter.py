"""
Módulo de Exportação em Planilhas Excel (.xlsx) e CSV.
Gera planilhas corporativas elegantes e completas com formatação numérica de moeda (R$),
datas, cabeçalhos estilizados, fórmulas e múltiplas abas analíticas.
"""

import io
import csv
from decimal import Decimal
from typing import List, Optional
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from svc_nfse_engine.models import NFSNacionalModel
from svc_nfse_engine.retencoes import TAX_FIELDS, get_retention_amounts
from supreme_common.spreadsheet import safe_cell


class NFSeExporter:
    """Gerador de planilhas formatadas de NFS-e."""

    # Estilos de design corporativo
    HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")  # Slate 800
    SUBHEADER_FILL = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
    ACCENT_FILL = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")   # Teal
    ZEBRA_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    ALERT_FILL = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")

    FONT_HEADER = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    FONT_TITLE = Font(name="Segoe UI", size=14, bold=True, color="0F172A")
    FONT_SECTION = Font(name="Segoe UI", size=12, bold=True, color="1E293B")
    FONT_BODY = Font(name="Segoe UI", size=10, color="0F172A")
    FONT_BOLD = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    FONT_MUTED = Font(name="Segoe UI", size=9, color="64748B", italic=True)

    BORDER_THIN = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )
    BORDER_DOUBLE_BOTTOM = Border(
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="double", color="0F172A"),
    )

    FORMAT_CURRENCY = 'R$ #,##0.00'
    FORMAT_PERCENT = '0.00%'
    FORMAT_DATE = 'DD/MM/YYYY'
    FORMAT_DATETIME = 'DD/MM/YYYY HH:MM'
    RETENTION_HEADERS = (
        "ISSQN Retido (R$)", "INSS Retido (R$)", "PIS Retido (R$)",
        "COFINS Retido (R$)", "IRRF Retido (R$)", "CSLL Retido (R$)",
    )

    @classmethod
    def _retention_cells(cls, note: NFSNacionalModel):
        amounts = get_retention_amounts(note)
        return [(float(amounts[field]), cls.FORMAT_CURRENCY, "right") for field in TAX_FIELDS]

    @classmethod
    def generate_excel(cls, notes: List[NFSNacionalModel], periodo_info: Optional[str] = None) -> bytes:
        """Gera pasta de trabalho Excel com 4 abas analíticas."""
        wb = Workbook()

        # 1. Aba Resumo Gerencial
        ws_resumo = wb.active
        ws_resumo.title = "Resumo Gerencial"
        cls._build_sheet_resumo(ws_resumo, notes, periodo_info=periodo_info)

        # 2. Aba Detalhamento Completo
        ws_detalhe = wb.create_sheet(title="Notas Fiscais")
        cls._build_sheet_detalhado(ws_detalhe, notes)

        # 3. Aba Auditoria e Retenções
        ws_retencoes = wb.create_sheet(title="Retenções na Fonte e INSS")
        cls._build_sheet_retencoes(ws_retencoes, notes)

        # 4. Aba Dados Bancários, PIX e Contratos
        ws_pix = wb.create_sheet(title="PIX e Complementares")
        cls._build_sheet_complementares(ws_pix, notes)

        # Salva em buffer de memória
        buffer = io.BytesIO()
        for sheet in wb.worksheets:
            for row in sheet:
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.value = safe_cell(cell.value)
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def _auto_fit_columns(cls, ws, max_len_cap: int = 50):
        """Ajusta larguras das colunas de forma automática e elegante."""
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = cell.value
                if val is not None:
                    sval = str(val)
                    if len(sval) > max_len:
                        max_len = len(sval)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), max_len_cap)

    @classmethod
    def _build_sheet_resumo(cls, ws, notes: List[NFSNacionalModel], periodo_info: Optional[str] = None):
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = "RELATÓRIO FISCAL CONSOLIDADO - NFS-e NACIONAL"
        ws["A1"].font = cls.FONT_TITLE
        ws["A2"] = f"Total de Notas Processadas: {len(notes)}"
        ws["A2"].font = cls.FONT_MUTED

        header_row = 4
        if periodo_info:
            ws["A3"] = f"Período Selecionado: {periodo_info}"
            ws["A3"].font = cls.FONT_MUTED
            header_row = 5

        # Cabeçalhos do quadro financeiro
        ws[f"A{header_row}"] = "Indicador Fiscal / Contábil"
        ws[f"B{header_row}"] = "Valor Total (R$)"
        ws[f"C{header_row}"] = "% do Faturamento"
        for col in ("A", "B", "C"):
            cell = ws[f"{col}{header_row}"]
            cell.fill = cls.HEADER_FILL
            cell.font = cls.FONT_HEADER
            cell.alignment = Alignment(horizontal="center" if col != "A" else "left")

        # Consolidar em Decimal antes de converter para células numéricas do Excel.
        zero = Decimal("0.00")
        total_bruto = sum((n.valor_servico for n in notes), zero)
        total_liq = sum((n.valor_liquido for n in notes), zero)
        total_ret = sum((n.valor_total_retencoes for n in notes), zero)
        iss_proprio = sum((n.valor_issqn for n in notes if n.tipo_retencao_issqn != 2), zero)
        iss_retido = sum(n.valor_issqn for n in notes if n.tipo_retencao_issqn == 2)
        inss_retido = sum(n.tributos_federais.valor_ret_cp_inss for n in notes)
        pis_total = sum(n.tributos_federais.valor_pis for n in notes)
        cofins_total = sum(n.tributos_federais.valor_cofins for n in notes)

        linhas = [
            ("Faturamento Bruto Total (vServ)", float(total_bruto), 1.0 if total_bruto else 0.0),
            ("Faturamento Líquido Efetivo (vLiq)", float(total_liq), float(total_liq / total_bruto) if total_bruto else 0.0),
            ("Total de Retenções na Fonte (vTotalRet)", float(total_ret), float(total_ret / total_bruto) if total_bruto else 0.0),
            ("ISSQN a Recolher (Apuração Própria)", float(iss_proprio), float(iss_proprio / total_bruto) if total_bruto else 0.0),
            ("ISSQN Retido na Fonte pelo Tomador", float(iss_retido), float(iss_retido / total_bruto) if total_bruto else 0.0),
            ("INSS Retenção Previdenciária (Cessão Mão de Obra)", float(inss_retido), float(inss_retido / total_bruto) if total_bruto else 0.0),
            ("PIS Apurado", float(pis_total), float(pis_total / total_bruto) if total_bruto else 0.0),
            ("COFINS Apurado", float(cofins_total), float(cofins_total / total_bruto) if total_bruto else 0.0),
        ]

        curr_row = header_row + 1
        for desc, val, pct in linhas:
            ws[f"A{curr_row}"] = desc
            ws[f"B{curr_row}"] = val
            ws[f"C{curr_row}"] = pct

            ws[f"A{curr_row}"].font = cls.FONT_BOLD if "Total" in desc else cls.FONT_BODY
            ws[f"B{curr_row}"].font = cls.FONT_BOLD if "Total" in desc else cls.FONT_BODY
            ws[f"C{curr_row}"].font = cls.FONT_BODY

            ws[f"B{curr_row}"].number_format = cls.FORMAT_CURRENCY
            ws[f"C{curr_row}"].number_format = cls.FORMAT_PERCENT

            for col in ("A", "B", "C"):
                ws[f"{col}{curr_row}"].border = cls.BORDER_THIN
            curr_row += 1

        # Quadro de conformidade contábil
        curr_row += 2
        ws[f"A{curr_row}"] = "Status de Auditoria Contábil"
        ws[f"B{curr_row}"] = "Quantidade de Notas"
        ws[f"C{curr_row}"] = "% do Total"
        for col in ("A", "B", "C"):
            cell = ws[f"{col}{curr_row}"]
            cell.fill = cls.SUBHEADER_FILL
            cell.font = cls.FONT_HEADER

        conciliadas = sum(1 for n in notes if n.auditoria.status_conciliacao == "CONCILIADO")
        inconsistentes = len(notes) - conciliadas

        curr_row += 1
        ws[f"A{curr_row}"] = "Notas 100% Conciliadas (vLiq = vServ - vTotalRet)"
        ws[f"B{curr_row}"] = conciliadas
        ws[f"C{curr_row}"] = conciliadas / len(notes) if notes else 0
        ws[f"C{curr_row}"].number_format = cls.FORMAT_PERCENT
        for col in ("A", "B", "C"):
            ws[f"{col}{curr_row}"].border = cls.BORDER_THIN

        curr_row += 1
        ws[f"A{curr_row}"] = "Notas com Inconsistências / Alertas"
        ws[f"B{curr_row}"] = inconsistentes
        ws[f"C{curr_row}"] = inconsistentes / len(notes) if notes else 0
        ws[f"C{curr_row}"].number_format = cls.FORMAT_PERCENT
        for col in ("A", "B", "C"):
            ws[f"{col}{curr_row}"].border = cls.BORDER_THIN

        # Quadro horizontal com as mesmas seis colunas das abas por nota.
        curr_row += 3
        ws.cell(curr_row, 1, "RETENÇÕES POR TRIBUTO — TOTAIS DO RELATÓRIO").font = cls.FONT_SECTION
        curr_row += 1
        totals = dict.fromkeys(TAX_FIELDS, zero)
        for note in notes:
            for field, amount in get_retention_amounts(note).items():
                totals[field] += amount
        identified = sum(totals.values(), zero)
        headers = [*cls.RETENTION_HEADERS, "Total declarado (R$)", "Total identificado (R$)", "Diferença (R$)"]
        values = [*(totals[field] for field in TAX_FIELDS), total_ret, identified, total_ret - identified]
        ws.row_dimensions[curr_row].height = 30
        for column, (header, value) in enumerate(zip(headers, values), start=1):
            cell = ws.cell(curr_row, column, header)
            cell.font = cls.FONT_HEADER
            cell.fill = cls.ACCENT_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = cls.BORDER_THIN
            amount_cell = ws.cell(curr_row + 1, column, float(value))
            amount_cell.font = cls.FONT_BOLD
            amount_cell.number_format = cls.FORMAT_CURRENCY
            amount_cell.alignment = Alignment(horizontal="right")
            amount_cell.border = cls.BORDER_THIN
        ws.cell(curr_row + 3, 1, "Diferença = total declarado nas notas − soma dos seis tributos retidos.").font = cls.FONT_MUTED

        cls._auto_fit_columns(ws)

    @classmethod
    def _build_sheet_detalhado(cls, ws, notes: List[NFSNacionalModel]):
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Número NFS-e",
            "Chave de Acesso",
            "Data/Hora Proc.",
            "Competência",
            "Status",
            "Prestador Razão Social",
            "Prestador CNPJ",
            "Prestador Município",
            "Prestador UF",
            "Tomador Razão Social",
            "Tomador CNPJ/CPF",
            "Tomador Município",
            "Tomador Bairro",
            "Local Prestação",
            "Cód. Trib. Nac.",
            "Desc. Trib. Nac.",
            "Cód. NBS",
            "Valor Serviço (R$)",
            "Base Cálc. ISS (R$)",
            "Alíq. ISS (%)",
            "Valor ISSQN (R$)",
            "Valor PIS (R$)",
            "Valor COFINS (R$)",
            "ISS Retido?",
            *cls.RETENTION_HEADERS,
            "Total Retenções (R$)",
            "Valor Líquido (R$)",
            "Status Auditoria",
            "Descrição do Serviço",
        ]

        # Escreve cabeçalhos
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.fill = cls.HEADER_FILL
            cell.font = cls.FONT_HEADER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws.row_dimensions[1].height = 28

        for row_idx, n in enumerate(notes, start=2):
            is_zebra = row_idx % 2 == 0
            row_fill = cls.ZEBRA_FILL if is_zebra else None

            cells_data = [
                (n.numero_nfse, None, "center"),
                (n.chave_nfse, None, "left"),
                (n.data_hora_processamento.strftime("%d/%m/%Y %H:%M"), None, "center"),
                (n.data_competencia.strftime("%d/%m/%Y"), None, "center"),
                (n.status_descricao, None, "center"),
                (n.emitente.razao_social or "", None, "left"),
                (n.emitente.documento_formatado, None, "center"),
                (n.local_emissao, None, "left"),
                (n.emitente.endereco.uf if n.emitente.endereco else "", None, "center"),
                (n.tomador.razao_social or "", None, "left"),
                (n.tomador.documento_formatado, None, "center"),
                (n.local_prestacao, None, "left"),
                (n.tomador.endereco.bairro if n.tomador.endereco else "", None, "left"),
                (n.local_prestacao, None, "left"),
                (n.codigo_tributacao_nacional, None, "center"),
                (n.tributacao_nacional_desc, None, "left"),
                (n.codigo_nbs or "-", None, "center"),
                (float(n.valor_servico), cls.FORMAT_CURRENCY, "right"),
                (float(n.base_calculo), cls.FORMAT_CURRENCY, "right"),
                (float(n.aliquota_aplicada) / 100.0, cls.FORMAT_PERCENT, "right"),
                (float(n.valor_issqn), cls.FORMAT_CURRENCY, "right"),
                (float(n.tributos_federais.valor_pis), cls.FORMAT_CURRENCY, "right"),
                (float(n.tributos_federais.valor_cofins), cls.FORMAT_CURRENCY, "right"),
                ("Sim (Tomador)" if n.iss_retido_pelo_tomador else "Não (Prestador)", None, "center"),
                *cls._retention_cells(n),
                (float(n.valor_total_retencoes), cls.FORMAT_CURRENCY, "right"),
                (float(n.valor_liquido), cls.FORMAT_CURRENCY, "right"),
                (n.auditoria.status_conciliacao, None, "center"),
                (n.descricao_servico, None, "left"),
            ]

            for col_idx, (val, fmt, align) in enumerate(cells_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = cls.FONT_BODY
                cell.border = cls.BORDER_THIN
                if row_fill:
                    cell.fill = row_fill
                if fmt:
                    cell.number_format = fmt
                if align:
                    cell.alignment = Alignment(horizontal=align, vertical="center")

        cls._auto_fit_columns(ws, max_len_cap=45)

    @classmethod
    def _build_sheet_retencoes(cls, ws, notes: List[NFSNacionalModel]):
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Número NFS-e",
            "Competência",
            "Tomador",
            "CNPJ/CPF Tomador",
            "Valor Serviço (R$)",
            *cls.RETENTION_HEADERS,
            "Total Retenções (R$)",
            "Líquido a Pagar (R$)",
            "Status Conciliação",
            "Observações de Auditoria",
        ]

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.fill = cls.ACCENT_FILL
            cell.font = cls.FONT_HEADER
            cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[1].height = 25

        for row_idx, n in enumerate(notes, start=2):
            is_zebra = row_idx % 2 == 0
            row_fill = cls.ZEBRA_FILL if is_zebra else None

            obs = " | ".join(n.auditoria.detalhes_auditoria)

            cells_data = [
                (n.numero_nfse, None, "center"),
                (n.data_competencia.strftime("%d/%m/%Y"), None, "center"),
                (n.tomador.razao_social or "", None, "left"),
                (n.tomador.documento_formatado, None, "center"),
                (float(n.valor_servico), cls.FORMAT_CURRENCY, "right"),
                *cls._retention_cells(n),
                (float(n.valor_total_retencoes), cls.FORMAT_CURRENCY, "right"),
                (float(n.valor_liquido), cls.FORMAT_CURRENCY, "right"),
                (n.auditoria.status_conciliacao, None, "center"),
                (obs, None, "left"),
            ]

            for col_idx, (val, fmt, align) in enumerate(cells_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = cls.FONT_BODY
                cell.border = cls.BORDER_THIN
                if row_fill:
                    cell.fill = row_fill
                if fmt:
                    cell.number_format = fmt
                if align:
                    cell.alignment = Alignment(horizontal=align, vertical="center")

        cls._auto_fit_columns(ws, max_len_cap=50)

    @classmethod
    def _build_sheet_complementares(cls, ws, notes: List[NFSNacionalModel]):
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Número NFS-e",
            "Tomador",
            "Chave PIX",
            "Tipo PIX",
            "Banco",
            "Agência",
            "Conta Corrente",
            "Contrato",
            "Pedido / PO",
            "Medição",
            "Dedução VT (R$)",
            "Dedução VR (R$)",
            "Dedução Material (R$)",
            "Texto Integral xInfComp",
            *cls.RETENTION_HEADERS,
            "Total Retenções (R$)",
        ]

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.fill = cls.SUBHEADER_FILL
            cell.font = cls.FONT_HEADER
            cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[1].height = 25

        for row_idx, n in enumerate(notes, start=2):
            is_zebra = row_idx % 2 == 0
            row_fill = cls.ZEBRA_FILL if is_zebra else None
            c = n.dados_complementares_extraidos

            cells_data = [
                (n.numero_nfse, None, "center"),
                (n.tomador.razao_social or "", None, "left"),
                (c.chave_pix or "-", None, "left"),
                (c.tipo_pix or "-", None, "center"),
                (c.banco_nome or "-", None, "left"),
                (c.agencia or "-", None, "center"),
                (c.conta_corrente or "-", None, "center"),
                (c.numero_contrato or "-", None, "center"),
                (c.numero_pedido or "-", None, "center"),
                (c.numero_medicao or "-", None, "center"),
                (float(c.deducao_vt) if c.deducao_vt else 0.0, cls.FORMAT_CURRENCY, "right"),
                (float(c.deducao_vr) if c.deducao_vr else 0.0, cls.FORMAT_CURRENCY, "right"),
                (float(c.deducao_material) if c.deducao_material else 0.0, cls.FORMAT_CURRENCY, "right"),
                (n.informacoes_complementares or "", None, "left"),
                *cls._retention_cells(n),
                (float(n.valor_total_retencoes), cls.FORMAT_CURRENCY, "right"),
            ]

            for col_idx, (val, fmt, align) in enumerate(cells_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = cls.FONT_BODY
                cell.border = cls.BORDER_THIN
                if row_fill:
                    cell.fill = row_fill
                if fmt:
                    cell.number_format = fmt
                if align:
                    cell.alignment = Alignment(horizontal=align, vertical="center")

        cls._auto_fit_columns(ws, max_len_cap=45)

    @classmethod
    def generate_csv(cls, notes: List[NFSNacionalModel]) -> bytes:
        """Gera arquivo CSV compatível com Excel em português (delimitador ponto e vírgula e UTF-8 com BOM)."""
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

        headers = [
            "Numero_NFSe",
            "Chave_Acesso",
            "Data_Processamento",
            "Competencia",
            "Status",
            "Emitente_Razao_Social",
            "Emitente_CNPJ",
            "Emitente_Municipio",
            "Tomador_Razao_Social",
            "Tomador_CNPJ_CPF",
            "Tomador_Municipio",
            "Local_Prestacao",
            "Codigo_Tributacao_Nacional",
            "Descricao_Tributacao",
            "Descricao_Servico",
            "Valor_Servico_R$",
            "Base_Calculo_R$",
            "Aliquota_ISS_%",
            "Valor_ISSQN_R$",
            "Tipo_Retencao_ISS",
            "Valor_PIS_R$",
            "Valor_COFINS_R$",
            *(f"Valor_Ret_{field.upper()}_R$" for field in TAX_FIELDS),
            "Total_Retencoes_R$",
            "Valor_Liquido_R$",
            "Status_Conciliacao",
            "Chave_PIX",
            "Banco",
            "Agencia",
            "Conta_Corrente",
        ]
        writer.writerow(headers)

        for n in notes:
            c = n.dados_complementares_extraidos
            retencoes = get_retention_amounts(n)
            writer.writerow([safe_cell(value) for value in [
                n.numero_nfse,
                n.chave_nfse,
                n.data_hora_processamento.strftime("%d/%m/%Y %H:%M:%S"),
                n.data_competencia.strftime("%d/%m/%Y"),
                n.status_descricao,
                n.emitente.razao_social or "",
                n.emitente.documento_formatado,
                n.local_emissao,
                n.tomador.razao_social or "",
                n.tomador.documento_formatado,
                n.tomador.endereco.codigo_municipio if n.tomador.endereco else "",
                n.local_prestacao,
                n.codigo_tributacao_nacional,
                n.tributacao_nacional_desc,
                n.descricao_servico.replace("\n", " ").replace(";", ","),
                f"{float(n.valor_servico):.2f}".replace(".", ","),
                f"{float(n.base_calculo):.2f}".replace(".", ","),
                f"{float(n.aliquota_aplicada):.2f}".replace(".", ","),
                f"{float(n.valor_issqn):.2f}".replace(".", ","),
                "Retido pelo Tomador" if n.iss_retido_pelo_tomador else "Devido pelo Prestador",
                f"{float(n.tributos_federais.valor_pis):.2f}".replace(".", ","),
                f"{float(n.tributos_federais.valor_cofins):.2f}".replace(".", ","),
                *(format(retencoes[field], ".2f").replace(".", ",") for field in TAX_FIELDS),
                f"{float(n.valor_total_retencoes):.2f}".replace(".", ","),
                f"{float(n.valor_liquido):.2f}".replace(".", ","),
                n.auditoria.status_conciliacao,
                c.chave_pix or "",
                c.banco_nome or "",
                c.agencia or "",
                c.conta_corrente or "",
            ]])

        # Adiciona UTF-8 BOM para o Excel abrir sem problemas de acentuação
        return ("\ufeff" + output.getvalue()).encode("utf-8")
