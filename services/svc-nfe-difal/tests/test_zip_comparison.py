from io import BytesIO
import csv
import json
from unittest.mock import patch

import openpyxl
import pytest

from svc_nfe_difal.core.zip_comparison import compare_nfe_zips, monetary_amount
from svc_nfe_difal.core.nfe_parser import NfeParser
from svc_nfe_difal.core.reporting import (
    json_download, zip_comparison_excel, zip_comparison_csv,
    zip_comparison_divergences_csv, zip_comparison_payload,
)
from .sample_data import SAMPLE_XML
from .test_zip_extractor import make_zip

KEY = b"35210000000000000000550010000000011000000001"


def xml(number=1, value="100.00", *, key=True, serie="1", cnpj="12345678000195", icms="3.78", st="5.00"):
    content = SAMPLE_XML.replace(KEY, str(number).zfill(44).encode() if key else b"invalida")
    return (content.replace(b"<nNF>12345</nNF>", f"<nNF>{number}</nNF>".encode())
            .replace(b"<serie>1</serie>", f"<serie>{serie}</serie>".encode())
            .replace(b"12345678000195", cnpj.encode())
            .replace(b"<vNF>26.00</vNF>", f"<vNF>{value}</vNF>".encode())
            .replace(b"<vICMS>3.78</vICMS>", f"<vICMS>{icms}</vICMS>".encode())
            .replace(b"<vST>5.00</vST>", f"<vST>{st}</vST>".encode()))


def package(*notes):
    return make_zip([(f"sub/nota-{index}.xml", content) for index, content in enumerate(notes)])


def company_xml(number, emitente, destinatario):
    return xml(number, cnpj=emitente).replace(b"98765432000110", destinatario.encode())


def test_accepts_5000_xmls_per_zip_with_directories_and_other_files():
    entries = [(f"sub/nota-{index}.xml", xml(index + 1)) for index in range(5000)]
    entries.extend([("sub/", b""), ("readme.txt", b"ignorar")])
    archive = make_zip(entries)
    result = compare_nfe_zips(archive, archive)
    assert result.resumo.total_cliente == result.resumo.total_portal == 5000
    assert result.resumo.total_comuns == 5000
    assert result.cnpjs_empresa == ["12345678000195", "98765432000110"]


@pytest.mark.parametrize("side", ["cliente", "portal"])
def test_5001_xmls_fail_before_parsing_even_when_duplicates(side):
    archive = make_zip([(f"nota-{index}.XML", b"<erro>") for index in range(5001)])
    with patch("svc_nfe_difal.core.zip_comparison.NfeParser.parse_bytes", wraps=NfeParser().parse_bytes) as parse:
        with pytest.raises(ValueError, match="5000 arquivos XML"):
            compare_nfe_zips(archive if side == "cliente" else package(xml()),
                             archive if side == "portal" else archive)
        assert parse.call_count == (0 if side == "cliente" else 1)


def test_company_can_be_emitter_or_recipient_in_both_packages():
    empresa, fornecedor, comprador = "12345678000195", "98765432000110", "11111111000191"
    cliente = package(company_xml(1, empresa, comprador), company_xml(2, fornecedor, empresa))
    portal = package(company_xml(3, empresa, fornecedor), company_xml(4, comprador, empresa))
    result = compare_nfe_zips(cliente, portal)
    assert result.cnpjs_empresa == [empresa]
    assert result.resumo.total_cliente == result.resumo.total_portal == 2


def test_company_cnpj_is_normalized_and_cpf_does_not_count_as_company():
    cliente = package(company_xml(1, "12.345.678/0001-95", "12345678901"))
    portal = package(company_xml(2, "11111111000191", "12345678000195"))
    assert compare_nfe_zips(cliente, portal).cnpjs_empresa == ["12345678000195"]


@pytest.mark.parametrize("side", ["cliente", "portal"])
def test_mixed_companies_in_one_package_are_rejected(side):
    mixed = package(company_xml(1, "12345678000195", "98765432000110"),
                    company_xml(2, "11111111000191", "22222222000191"))
    with pytest.raises(ValueError, match="mesma empresa"):
        compare_nfe_zips(mixed if side == "cliente" else package(xml()),
                         mixed if side == "portal" else package(xml()))


def test_packages_of_different_companies_are_rejected():
    with pytest.raises(ValueError, match="mesma empresa"):
        compare_nfe_zips(package(xml()), package(company_xml(2, "11111111000191", "22222222000191")))


def test_company_validation_includes_duplicates_before_deduplication():
    duplicate = company_xml(1, "11111111000191", "22222222000191")
    with pytest.raises(ValueError, match="mesma empresa"):
        compare_nfe_zips(package(xml(), duplicate), package(xml()))


def test_company_validation_requires_valid_cnpj_in_each_note():
    invalid = company_xml(1, "", "12345678901")
    with pytest.raises(ValueError, match="CNPJ válido"):
        compare_nfe_zips(package(invalid), package(xml()))


def test_overlap_and_exact_tax_totals():
    result = compare_nfe_zips(package(xml(1), xml(2), xml(3)), package(xml(2), xml(3), xml(4)))
    assert [n.numero for n in result.apenas_cliente] == ["1"]
    assert [n.numero for n in result.apenas_portal] == ["4"]
    assert [n.numero for n in result.em_ambos] == ["2", "3"]
    assert result.resumo.total_cliente == result.resumo.total_portal == 3
    assert result.resumo.valor_total_cliente == result.resumo.valor_total_portal == 300
    assert result.resumo.valor_apenas_cliente == result.resumo.valor_apenas_portal == 100
    assert result.resumo.valor_comuns == 200
    assert result.resumo.totais_por_grupo["cliente"]["valor_icms"] == 11.34
    assert result.resumo.totais_por_grupo["em_ambos"]["valor_icms_st"] == 10


@pytest.mark.parametrize("value,expected", [("120.00", 1), ("100.01", 0), ("99.99", 0), ("99.98", 1)])
def test_divergence_and_decimal_cent_boundary(value, expected):
    result = compare_nfe_zips(package(xml()), package(xml(value=value)))
    assert len(result.em_ambos) == 1
    assert len(result.divergencias) == expected
    if value == "120.00":
        item = result.divergencias[0]
        assert item.diferenca == 20
        assert item.nota_cliente.valor_total_float == 100
        assert item.nota_portal.valor_total_float == 120
        assert result.resumo.totais_por_grupo["divergencias_portal"]["valor_total"] == 120


def test_tax_only_divergence_preserves_both_sides():
    result = compare_nfe_zips(package(xml()), package(xml(icms="6.00", st="7.00")))
    assert result.divergencias[0].campos_divergentes == ("valor_icms", "valor_icms_st")
    assert result.divergencias[0].diferenca == 0


@pytest.mark.parametrize("cliente,portal,common", [([1, 2], [1, 2], 2), ([1], [2], 0)])
def test_identical_and_disjoint(cliente, portal, common):
    result = compare_nfe_zips(package(*(xml(n) for n in cliente)), package(*(xml(n) for n in portal)))
    assert len(result.em_ambos) == common
    assert len(result.apenas_cliente) == len(cliente) - common
    assert len(result.apenas_portal) == len(portal) - common


@pytest.mark.parametrize("client_key,portal_key", [(False, False), (False, True), (True, False)])
def test_fallback_normalizes_and_matches_valid_key_on_other_side(client_key, portal_key):
    result = compare_nfe_zips(package(xml("0001", key=client_key, serie="001", cnpj="12.345.678/0001-95")),
                              package(xml(1, key=portal_key)))
    assert len(result.em_ambos) == 1
    assert not result.apenas_cliente and not result.apenas_portal
    if not client_key:
        assert result.em_ambos[0].chave == "CHAVE_INCOMPLETA_12345678000195_1_1"


def test_different_valid_keys_never_match_by_secondary_identity():
    other = xml().replace(str(1).zfill(44).encode(), str(2).zfill(44).encode())
    result = compare_nfe_zips(package(xml()), package(other))
    assert len(result.apenas_cliente) == len(result.apenas_portal) == 1
    assert not result.em_ambos


def test_valid_primary_key_matches_without_fallback_metadata():
    content = xml(cnpj="", serie="")
    result = compare_nfe_zips(package(content), package(content))
    assert len(result.em_ambos) == 1
    assert not result.apenas_cliente


def test_ambiguous_fallback_is_not_matched():
    other = xml().replace(str(1).zfill(44).encode(), str(2).zfill(44).encode())
    result = compare_nfe_zips(package(xml(key=False)), package(xml(), other))
    assert not result.em_ambos
    assert len(result.apenas_portal) == 2
    assert any("ambígua" in i.message for i in result.issues_cliente)


def test_ambiguous_fallback_with_already_matched_key_keeps_exact_match():
    other = xml().replace(str(1).zfill(44).encode(), str(2).zfill(44).encode())
    result = compare_nfe_zips(package(xml(), xml(key=False)), package(xml(), other))
    assert len(result.em_ambos) == 1
    assert len(result.apenas_cliente) == len(result.apenas_portal) == 1
    assert any("ambígua" in issue.message for issue in result.issues_cliente)


def test_duplicate_is_counted_once_with_warning():
    result = compare_nfe_zips(package(xml(), xml(value="200")), package(xml()))
    assert result.resumo.total_cliente == 1
    assert result.resumo.valor_total_cliente == 100
    assert any("duplicada" in i.message for i in result.issues_cliente)


def test_non_xml_and_invalid_xml_are_ignored_but_reported():
    mixed = make_zip([("a.pdf", b"PDF"), ("foto.jpg", b"JPEG"), ("bad.xml", b"<bad>"),
                      ("event.xml", b"<evento/>"), ("ok.xml", xml()),
                      ("incomplete.xml", xml(key=False, cnpj=""))])
    result = compare_nfe_zips(mixed, package(xml()))
    assert result.resumo.total_cliente == 1
    assert len(result.issues_cliente) == 3


@pytest.mark.parametrize("bad", [b"", b"corrompido", make_zip([]), make_zip([("a.txt", b"txt")]), package(b"<bad>")])
@pytest.mark.parametrize("side", ["cliente", "portal"])
def test_empty_or_corrupt_packages_fail(bad, side):
    with pytest.raises(ValueError):
        compare_nfe_zips(bad if side == "cliente" else package(xml()), bad if side == "portal" else package(xml()))


@pytest.mark.parametrize("value", ["", "abc", "NaN", "Infinity", "1e100", "-Infinity", "1e9999999", "1e9999999999999999999"])
def test_invalid_amounts_are_finite_and_warn(value):
    result = compare_nfe_zips(package(xml(value=value)), package(xml(value="0")))
    assert result.resumo.valor_total_cliente == 0
    assert not result.divergencias
    assert result.issues_cliente
    json.dumps(zip_comparison_payload(result), allow_nan=False)


def test_brazilian_amounts_and_decimal_sum():
    result = compare_nfe_zips(package(xml(1, "1.234,56"), xml(2, "0.10"), xml(3, "0.20")),
                              package(xml(1, "1234.56"), xml(2, "0.10"), xml(3, "0.20")))
    assert result.resumo.valor_total_cliente == 1234.86
    assert not result.divergencias
    assert monetary_amount("abc") == monetary_amount("") == 0


def test_exclusively_in_memory_preserves_stream_position_and_ownership():
    client, portal = BytesIO(package(xml())), BytesIO(package(xml()))
    client.seek(3)
    portal.seek(5)
    with patch("builtins.open", side_effect=AssertionError("Disco não permitido")), \
         patch("tempfile.TemporaryFile", side_effect=AssertionError("Temporário não permitido")), \
         patch("zipfile.ZipFile.extractall", side_effect=AssertionError("Extração não permitida")):
        result = compare_nfe_zips(client, portal)
    assert result.resumo.total_comuns == 1
    assert (client.tell(), portal.tell()) == (3, 5)
    assert not client.closed and not portal.closed


def test_reports_structure_currency_sanitization_and_identifiers():
    bad_name = xml().replace(b"EMPRESA TESTE LTDA", b"=HYPERLINK(1)")
    result = compare_nfe_zips(package(bad_name, xml(key=False)), package(xml(value="120")))
    workbook = openpyxl.load_workbook(BytesIO(zip_comparison_excel(result)))
    assert workbook.sheetnames == ["Resumo Consolidado", "Apenas no Cliente", "Apenas no Portal", "Conciliadas", "Divergências de Valores"]
    sheet = workbook["Conciliadas"]
    assert sheet["A2"].value == str(1).zfill(44)
    assert sheet["A2"].data_type == "s"
    assert sheet["F2"].value.startswith("'=HYPERLINK")
    assert sheet["I2"].value == 100
    assert "R$" in sheet["I2"].number_format
    assert sheet.freeze_panes == "A2" and sheet.auto_filter.ref
    assert workbook["Divergências de Valores"]["G2"].value == 20
    csv_bytes = zip_comparison_csv(result.em_ambos)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(csv_bytes.decode("utf-8-sig").splitlines(), delimiter=";"))
    assert rows[1][0] == str(1).zfill(44)
    assert rows[1][5].startswith("'=HYPERLINK")
    assert rows[1][8] == "100,00"
    divergence = zip_comparison_divergences_csv(result.divergencias).decode("utf-8-sig")
    assert "120,00;20,00" in divergence
    payload = json.loads(json_download(zip_comparison_payload(result)))
    assert payload["em_ambos_portal"][0]["valor_total_float"] == 120
    assert payload["divergencias"][0]["nota_portal"]["filename"]
