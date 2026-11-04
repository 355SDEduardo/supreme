from __future__ import annotations

import csv
import json
import unicodedata
from dataclasses import asdict
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from typing import Any, Iterable

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.models import ComparisonItem, NfeData, NfeProduct, ParseIssue, ReconciliationNote, ReconciliationDivergence, ZipComparisonResult
from core.zip_comparison import monetary_amount


def parse_number(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip()
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        try:
            return Decimal(text.replace(".", "").replace(",", "."))
        except InvalidOperation:
            return Decimal("0")


def report_payload(
    nfes: list[NfeData], issues: list[ParseIssue] | None = None
) -> dict[str, Any]:
    return {
        "resumo_geral": [_serialize_note(note) for note in nfes],
        "produtos": [
            _serialize_product(note.numero, product)
            for note in nfes
            for product in note.produtos
        ],
        "erros_processamento": [
            {"arquivo": issue.filename, "erro": issue.message}
            for issue in (issues or [])
        ],
    }


def note_rows(nfes: list[NfeData]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for note in nfes:
        cfops = sorted({product.cfop for product in note.produtos if product.cfop})
        csts = sorted({product.cst for product in note.produtos if product.cst})
        rows.append(
            {
                "arquivo": note.filename,
                "chave": note.chave,
                "numero": note.numero,
                "serie": note.serie,
                "cnpj_emissor": note.cnpj_emitente,
                "emissor": note.nome_emitente,
                "cnpj_destinatario": note.cnpj_destinatario,
                "destinatario": note.nome_destinatario,
                "data_emissao": note.data_emissao,
                "cfops": ", ".join(cfops) or "—",
                "csts": ", ".join(csts) or "—",
                "valor_produtos": _float(note.valor_produtos),
                "valor_icms": _float(note.valor_icms),
                "valor_bc_st": _float(note.valor_bc_st),
                "valor_icms_st": _float(note.valor_icms_st),
                "valor_total": _float(note.valor_total),
            }
        )
    return rows


def product_rows(
    nfes: list[NfeData],
    *,
    note_number: str = "",
    operacao: str = "",
    cfop: str = "",
    cst: str = "",
    status: str = "",
    query: str = "",
) -> list[dict[str, Any]]:
    normalized_query = _normalized_search_text(query)
    cfop_prefixes: tuple[str, ...] = ()
    if operacao == "estadual":
        cfop_prefixes = ("5",)
    elif operacao == "interestadual":
        cfop_prefixes = ("6",)
    elif operacao in {"ambos", "ambas"}:
        cfop_prefixes = ("5", "6")
    rows: list[dict[str, Any]] = []
    for note_index, note in enumerate(nfes):
        if note_number and note.numero != note_number:
            continue
        for product_index, product in enumerate(note.produtos):
            if cfop_prefixes and not product.cfop.startswith(cfop_prefixes):
                continue
            if cfop and product.cfop != cfop:
                continue
            if cst and product.cst != cst:
                continue
            if status == "registered" and product.ncm_cadastrado is not True:
                continue
            if status == "unregistered" and product.ncm_cadastrado is not False:
                continue
            if status == "applicable" and not (
                product.ncm_cadastrado is True
                and product.status_st.strip().casefold() == "sim"
            ):
                continue
            if normalized_query and not any(
                normalized_query in _normalized_search_text(value)
                for value in (product.codigo, product.descricao, product.ncm)
            ):
                continue
            rows.append({
                **_product_row(note.numero, product),
                "note_index": note_index,
                "product_index": product_index,
                "note_key": note.chave,
            })
    return rows


def aggregate_rows(nfes: list[NfeData], group: str) -> list[dict[str, Any]]:
    if group not in {"cfop", "cst"}:
        raise ValueError("Agrupamento deve ser 'cfop' ou 'cst'.")

    aggregates: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "quantidade_itens": 0,
            "notas": set(),
            "valor_produtos": Decimal("0"),
            "valor_icms": Decimal("0"),
            "valor_bc_st": Decimal("0"),
            "valor_icms_st": Decimal("0"),
        }
    )
    for note in nfes:
        for product in note.produtos:
            key = getattr(product, group).strip() or "Não informado"
            row = aggregates[key]
            row["quantidade_itens"] += 1
            row["notas"].add(note.numero)
            row["valor_produtos"] += parse_number(product.valor_total)
            row["valor_icms"] += parse_number(product.valor_icms)
            row["valor_bc_st"] += parse_number(product.valor_bc_st)
            row["valor_icms_st"] += parse_number(product.valor_icms_st)

    result: list[dict[str, Any]] = []
    for code in sorted(aggregates):
        row = aggregates[code]
        result.append(
            {
                group: code,
                "quantidade_itens": row["quantidade_itens"],
                "quantidade_notas": len(row["notas"]),
                "valor_produtos": float(row["valor_produtos"]),
                "valor_icms": float(row["valor_icms"]),
                "valor_bc_st": float(row["valor_bc_st"]),
                "valor_icms_st": float(row["valor_icms_st"]),
                "valor_total": float(row["valor_produtos"] + row["valor_icms_st"]),
            }
        )
    return result


def totals(nfes: list[NfeData]) -> dict[str, Any]:
    return {
        "notas": len(nfes),
        "valor_produtos": float(sum((parse_number(n.valor_produtos) for n in nfes), Decimal("0"))),
        "valor_icms": float(sum((parse_number(n.valor_icms) for n in nfes), Decimal("0"))),
        "valor_icms_st": float(sum((parse_number(n.valor_icms_st) for n in nfes), Decimal("0"))),
        "valor_total": float(sum((parse_number(n.valor_total) for n in nfes), Decimal("0"))),
    }


def comparison_payload(items: list[ComparisonItem]) -> dict[str, Any]:
    return {"ncms": [item.to_dict() for item in items]}


def json_download(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )


def csv_download(
    rows: Iterable[dict[str, Any]], columns: list[tuple[str, str]]
) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow(
            [sanitize_spreadsheet_value(row.get(key, "")) for key, _ in columns]
        )
    return output.getvalue().encode("utf-8-sig")


def excel_download(nfes: list[NfeData]) -> bytes:
    workbook = openpyxl.Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "Resumo Geral"
    summary_columns = [
        ("arquivo", "Arquivo"),
        ("chave", "Chave de Acesso"),
        ("numero", "Número"),
        ("serie", "Série"),
        ("cnpj_emissor", "CNPJ Emissor"),
        ("emissor", "Emissor"),
        ("cnpj_destinatario", "CNPJ Destinatário"),
        ("destinatario", "Destinatário"),
        ("data_emissao", "Data Emissão"),
        ("valor_produtos", "Valor Produtos"),
        ("valor_icms", "Valor ICMS"),
        ("valor_bc_st", "Valor BC ST"),
        ("valor_icms_st", "Valor ICMS ST"),
        ("valor_total", "Valor Total"),
    ]
    _write_sheet(summary_sheet, note_rows(nfes), summary_columns)

    product_sheet = workbook.create_sheet("Produtos")
    product_columns = [
        ("nfe", "NF-e"),
        ("item", "Item"),
        ("codigo", "Código"),
        ("descricao", "Descrição"),
        ("ncm", "NCM"),
        ("cst", "CST"),
        ("cfop", "CFOP"),
        ("ncm_cadastrado", "NCM Cadastrado"),
        ("st", "ST"),
        ("mva", "MVA"),
        ("cest", "CEST"),
        ("destinacao", "Destinação"),
        ("quantidade", "Qtd"),
        ("unidade", "UN"),
        ("valor_unitario", "Valor Unit."),
        ("valor_total", "Valor Total"),
        ("valor_icms", "Valor ICMS"),
        ("valor_bc_st", "Valor BC ST"),
        ("valor_icms_st", "Valor ICMS ST"),
    ]
    _write_sheet(product_sheet, product_rows(nfes), product_columns)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def sanitize_spreadsheet_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


def _write_sheet(
    worksheet: Any,
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]],
) -> None:
    for column_index, (_, label) in enumerate(columns, start=1):
        worksheet.cell(row=1, column=column_index, value=label)

    for row_index, row in enumerate(rows, start=2):
        for column_index, (key, _) in enumerate(columns, start=1):
            worksheet.cell(
                row=row_index,
                column=column_index,
                value=sanitize_spreadsheet_value(row.get(key, "")),
            )

    header_fill = PatternFill("solid", fgColor="315B7D")
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column in worksheet.columns:
        width = min(max((len(str(cell.value or "")) for cell in column), default=0) + 2, 40)
        worksheet.column_dimensions[get_column_letter(column[0].column)].width = width


def _serialize_note(note: NfeData) -> dict[str, Any]:
    return {
        "arquivo": note.filename,
        "chave_acesso": note.chave,
        "numero": note.numero,
        "serie": note.serie,
        "cnpj_emissor": note.cnpj_emitente,
        "emissor": note.nome_emitente,
        "cnpj_destinatario": note.cnpj_destinatario,
        "destinatario": note.nome_destinatario,
        "data_emissao": note.data_emissao,
        "valor_produtos": _float(note.valor_produtos),
        "valor_icms": _float(note.valor_icms),
        "valor_bc_st": _float(note.valor_bc_st),
        "valor_icms_st": _float(note.valor_icms_st),
        "valor_ipi": _float(note.valor_ipi),
        "valor_pis": _float(note.valor_pis),
        "valor_cofins": _float(note.valor_cofins),
        "v_frete": _float(note.v_frete),
        "v_seg": _float(note.v_seg),
        "v_desc": _float(note.v_desc),
        "v_outro": _float(note.v_outro),
        "valor_total": _float(note.valor_total),
    }


def _serialize_product(note_number: str, product: NfeProduct) -> dict[str, Any]:
    row = _product_row(note_number, product)
    return {
        "nfe_numero": row["nfe"],
        "item_num": row["item"],
        "codigo": row["codigo"],
        "descricao": row["descricao"],
        "ncm": row["ncm"],
        "cst": row["cst"],
        "cfop": row["cfop"],
        "qtd": row["quantidade"],
        "un": row["unidade"],
        "valor_unitario": row["valor_unitario"],
        "valor_total": row["valor_total"],
        "valor_icms": row["valor_icms"],
        "valor_bc_st": row["valor_bc_st"],
        "valor_icms_st": row["valor_icms_st"],
        "valor_bc_st_ret": _float(product.valor_bc_st_ret),
        "valor_icms_st_ret": _float(product.valor_icms_st_ret),
        "valor_ipi": _float(product.valor_ipi),
        "valor_pis": _float(product.valor_pis),
        "valor_cofins": _float(product.valor_cofins),
        "ncm_cadastrado": product.ncm_cadastrado,
        "st": product.status_st,
        "mva": product.mva,
        "cest": product.cest,
        "destinacao": product.destinacao,
    }


def _product_row(note_number: str, product: NfeProduct) -> dict[str, Any]:
    if product.ncm_cadastrado is True:
        registration = "Sim"
    elif product.ncm_cadastrado is False:
        registration = "Não"
    else:
        registration = "Não analisado"
    return {
        "nfe": note_number,
        "item": product.numero,
        "codigo": product.codigo,
        "descricao": product.descricao,
        "ncm": product.ncm,
        "cst": product.cst,
        "cfop": product.cfop,
        "quantidade": _float(product.quantidade),
        "unidade": product.unidade,
        "valor_unitario": _float(product.valor_unitario),
        "valor_total": _float(product.valor_total),
        "valor_icms": _float(product.valor_icms),
        "valor_bc_st": _float(product.valor_bc_st),
        "valor_icms_st": _float(product.valor_icms_st),
        "ncm_cadastrado": registration,
        "st": product.status_st,
        "mva": product.mva,
        "cest": product.cest,
        "destinacao": product.destinacao,
    }


def _float(value: object) -> float:
    return float(parse_number(value))


def _normalized_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


RECONCILIATION_COLUMNS = [
    ("chave", "Chave"), ("numero", "Número"), ("serie", "Série"),
    ("data_emissao", "Data Emissão"), ("cnpj_emitente", "CNPJ Emitente"),
    ("nome_emitente", "Emitente"), ("cnpj_destinatario", "CNPJ Destinatário"),
    ("nome_destinatario", "Destinatário"), ("valor_total", "Valor Total"),
    ("valor_icms", "ICMS"), ("valor_icms_st", "ICMS ST"), ("filename", "Arquivo"),
]
DIVERGENCE_COLUMNS = [
    ("chave", "Chave Cliente"), ("chave_portal", "Chave Portal"),
    ("numero", "Número"), ("serie", "Série"), ("valor_cliente", "Valor no Cliente"),
    ("valor_portal", "Valor no Portal"), ("diferenca", "Diferença (R$)"),
    ("icms_cliente", "ICMS Cliente"), ("icms_portal", "ICMS Portal"),
    ("st_cliente", "ICMS ST Cliente"), ("st_portal", "ICMS ST Portal"),
    ("campos_divergentes", "Campos divergentes"),
    ("arquivo_cliente", "Arquivo Cliente"), ("arquivo_portal", "Arquivo Portal"),
]


def _reconciliation_rows(notes: list[ReconciliationNote]) -> list[dict[str, Any]]:
    return [{**asdict(note), **{field: float(monetary_amount(getattr(note, field)))
                              for field in ("valor_total", "valor_icms", "valor_icms_st")}}
            for note in notes]


def _divergence_rows(items: list[ReconciliationDivergence]) -> list[dict[str, Any]]:
    return [{
        "chave": item.chave, "chave_portal": item.nota_portal.chave,
        "numero": item.numero, "serie": item.serie,
        "valor_cliente": item.valor_cliente, "valor_portal": item.valor_portal,
        "diferenca": item.diferenca,
        "icms_cliente": float(monetary_amount(item.nota_cliente.valor_icms)),
        "icms_portal": float(monetary_amount(item.nota_portal.valor_icms)),
        "st_cliente": float(monetary_amount(item.nota_cliente.valor_icms_st)),
        "st_portal": float(monetary_amount(item.nota_portal.valor_icms_st)),
        "campos_divergentes": ", ".join(item.campos_divergentes),
        "arquivo_cliente": item.nota_cliente.filename, "arquivo_portal": item.nota_portal.filename,
    } for item in items]


def zip_comparison_payload(result: ZipComparisonResult) -> dict[str, Any]:
    return asdict(result)


def zip_comparison_csv(notes: list[ReconciliationNote]) -> bytes:
    rows = _reconciliation_rows(notes)
    for row in rows:
        for field in ("valor_total", "valor_icms", "valor_icms_st"):
            row[field] = f"{row[field]:.2f}".replace(".", ",")
    return csv_download(rows, RECONCILIATION_COLUMNS)


def zip_comparison_divergences_csv(items: list[ReconciliationDivergence]) -> bytes:
    rows = _divergence_rows(items)
    for row in rows:
        for key, value in row.items():
            if isinstance(value, float):
                row[key] = f"{value:.2f}".replace(".", ",")
    return csv_download(rows, DIVERGENCE_COLUMNS)


def zip_comparison_excel(result: ZipComparisonResult) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    summary_rows = []
    labels = {
        "cliente": "Total Cliente", "portal": "Total Portal",
        "apenas_cliente": "Apenas no Cliente", "apenas_portal": "Apenas no Portal",
        "em_ambos": "Conciliadas (valores Cliente)", "em_ambos_portal": "Conciliadas (valores Portal)",
        "divergencias": "Divergências (valores Cliente)", "divergencias_portal": "Divergências (valores Portal)",
    }
    for key, label in labels.items():
        summary_rows.append({"grupo": label, **result.resumo.totais_por_grupo.get(key, {})})
    sheets = [
        ("Resumo Consolidado", summary_rows, [("grupo", "Grupo"), ("quantidade", "Quantidade"),
          ("valor_total", "Valor Total"), ("valor_icms", "ICMS"), ("valor_icms_st", "ICMS ST")]),
        ("Apenas no Cliente", _reconciliation_rows(result.apenas_cliente), RECONCILIATION_COLUMNS),
        ("Apenas no Portal", _reconciliation_rows(result.apenas_portal), RECONCILIATION_COLUMNS),
        ("Conciliadas", _reconciliation_rows(result.em_ambos), RECONCILIATION_COLUMNS),
        ("Divergências de Valores", _divergence_rows(result.divergencias), DIVERGENCE_COLUMNS),
    ]
    for title, rows, columns in sheets:
        sheet = workbook.create_sheet(title)
        _write_sheet(sheet, rows, columns)
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, float):
                    cell.number_format = '"R$" #,##0.00'
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
    # Avisos acompanham a exportação sem adicionar uma sexta aba.
    summary = workbook["Resumo Consolidado"]
    summary.append([])
    summary.append(["Empresa validada: CNPJ(s) em todas as NF-es", ", ".join(result.cnpjs_empresa)])
    summary.append([])
    summary.append(["Pacote", "Arquivo", "Aviso / rejeição"])
    for label, issues in (("Cliente", result.issues_cliente), ("Portal", result.issues_portal)):
        for issue in issues:
            summary.append([label, sanitize_spreadsheet_value(issue.filename), sanitize_spreadsheet_value(issue.message)])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
