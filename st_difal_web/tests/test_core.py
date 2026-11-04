from __future__ import annotations

import json

import pytest

from core.document_comparison import compare_products_to_pdf
from core.fiscal_registration import FiscalRegistration, FiscalRegistrationService
from core.ncm_comparison import compare_nfes, load_fiscal_catalog_bytes
from core.nfe_parser import NfeParser
from core.reporting import csv_download, product_rows, sanitize_spreadsheet_value
from tests.sample_data import SAMPLE_XML, fiscal_record


def test_parser_and_comparison_preserve_icms_cst() -> None:
    note = NfeParser().parse_bytes(SAMPLE_XML, "nfe.xml")
    catalog = load_fiscal_catalog_bytes(
        json.dumps([fiscal_record()], ensure_ascii=False).encode()
    )

    items, summary = compare_nfes([note], catalog)

    assert note.numero == "12345"
    assert note.produtos[0].cst == "10"
    assert note.produtos[0].valor_ipi == "1.00"
    assert summary.registered_ncms == 1
    assert items[0].mva == "40%"


def test_parser_rejects_dtd() -> None:
    with pytest.raises(ValueError, match="DTD"):
        NfeParser().parse_bytes(b"<!DOCTYPE foo><foo />", "hostil.xml")


def test_parser_reports_malformed_xml() -> None:
    with pytest.raises(ValueError, match="bem-formado"):
        NfeParser().parse_bytes(b"<nfe>", "incompleto.xml")


def test_fiscal_registration_rejects_formatted_duplicate(tmp_path) -> None:
    path = tmp_path / "fiscal.json"
    path.write_text(
        json.dumps([fiscal_record("2106.90.90")], ensure_ascii=False),
        encoding="utf-8",
    )
    item = FiscalRegistration(
        ncm="21069090",
        state="DF",
        internal_rate="20%",
        reduced_base="Não se aplica",
        deferral="Não se aplica",
        fcp="Não se aplica",
        exemption="Consultar",
        non_incidence="Não se aplica",
        st="Sim",
        suspension="Não se aplica",
    )

    with pytest.raises(ValueError, match="já está cadastrado"):
        FiscalRegistrationService().add(path, item)


def test_spreadsheet_exports_neutralize_formula() -> None:
    assert sanitize_spreadsheet_value("=CMD()") == "'=CMD()"
    exported = csv_download([{"codigo": "=CMD()"}], [("codigo", "Código")])
    assert b"'=CMD()" in exported


def test_product_search_ignores_case_and_accents() -> None:
    note = NfeParser().parse_bytes(SAMPLE_XML, "nfe.xml")
    note.produtos[0].descricao = "Preparação alimentícia"

    rows = product_rows([note], query="PREPARACAO ALIMENTICIA")

    assert len(rows) == 1


def test_product_rows_filter_by_operation_and_combine_with_cfop() -> None:
    note = NfeParser().parse_bytes(SAMPLE_XML, "nfe.xml")
    estadual = NfeParser().parse_bytes(SAMPLE_XML, "estadual.xml").produtos[0]
    estadual.cfop = "5102"
    outro = NfeParser().parse_bytes(SAMPLE_XML, "outro.xml").produtos[0]
    outro.cfop = "7102"
    note.produtos.extend([estadual, outro])

    assert [row["cfop"] for row in product_rows([note])] == ["6102", "5102", "7102"]
    assert [row["cfop"] for row in product_rows([note], operacao="estadual")] == ["5102"]
    assert [row["cfop"] for row in product_rows([note], operacao="interestadual")] == ["6102"]
    assert product_rows([note], operacao="estadual", cfop="6102") == []


def test_document_comparison_finds_product_in_pdf() -> None:
    fitz = pytest.importorskip("pymupdf")
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "PRODUTO TESTE")
        pdf = document.tobytes()

    result = compare_products_to_pdf(
        b"PRODUTO TESTE\nAUSENTE\n",
        pdf,
        txt_filename="produtos.txt",
        pdf_filename="relatorio.pdf",
    )

    assert result["resumo"]["total_encontrados"] == 1
    assert result["nao_encontrados"] == [{"produto": "AUSENTE"}]
