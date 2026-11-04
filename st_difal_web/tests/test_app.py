from __future__ import annotations

import csv
import json
from html.parser import HTMLParser
from io import BytesIO, StringIO
from pathlib import Path

import openpyxl
import pytest

from app import create_app
from tests.sample_data import SAMPLE_XML, fiscal_record
from tests.test_zip_extractor import make_zip
from tests.test_zip_comparison import package, xml, company_xml


class StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.label_targets: list[str] = []
        self.inline_scripts = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"])
        if tag == "label" and attributes.get("for"):
            self.label_targets.append(attributes["for"])
        if tag == "script" and not attributes.get("src"):
            self.inline_scripts += 1


@pytest.fixture
def app(tmp_path):
    fiscal_path = tmp_path / "fiscal.json"
    fiscal_path.write_text(
        json.dumps([fiscal_record()], ensure_ascii=False),
        encoding="utf-8",
    )
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "FISCAL_DATA_PATH": fiscal_path,
            "STATE_TTL_SECONDS": 300,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client) -> str:
    client.get("/")
    with client.session_transaction() as current_session:
        current_session["csrf_token"] = "csrf-test"
    return "csrf-test"


def process_sample(client) -> None:
    response = client.post(
        "/processar",
        data={
            "csrf_token": csrf(client),
            "xml_files": (BytesIO(SAMPLE_XML), "nfe.xml"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302


def compare_packages(client, cliente=None, portal=None, **extra):
    return client.post("/comparar-zips", data={
        "csrf_token": csrf(client),
        "zip_cliente": (BytesIO(cliente if cliente is not None else package(xml(1), xml(2))), "cliente.ZIP"),
        "zip_portal": (BytesIO(portal if portal is not None else package(xml(2, "120"), xml(3))), "portal.zip"),
        **extra,
    }, content_type="multipart/form-data")


def test_comparison_upload_page_and_all_downloads(client):
    response = compare_packages(client)
    assert response.status_code == 302
    assert response.location.endswith("tab=conciliacao-zips")
    page = client.get(response.location).get_data(as_text=True)
    assert "Conciliação concluída: 2 notas no cliente, 2 no portal, 1 em comum." in page
    assert 'id="conciliacao-zips"' in page
    assert 'data-reconciliation-filter="zip-common"' in page
    assert "R$ 20,00" in page
    excel = client.get("/download/conciliacao-zips.xlsx")
    assert excel.status_code == 200
    assert excel.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(openpyxl.load_workbook(BytesIO(excel.data)).sheetnames) == 5
    payload = client.get("/download/conciliacao-zips.json").get_json()
    assert payload["resumo"]["total_divergencias"] == 1
    assert payload["cnpjs_empresa"] == ["12345678000195", "98765432000110"]
    assert "Empresa validada." in page
    assert "5.000 XMLs por ZIP" in page
    for group in ("apenas-cliente", "apenas-portal", "em-ambos", "divergencias"):
        response = client.get(f"/download/conciliacao-zips/{group}.csv")
        assert response.status_code == 200
        assert response.data.startswith(b"\xef\xbb\xbf")
        assert response.mimetype == "text/csv"
    assert client.get("/download/conciliacao-zips/outro.csv").status_code == 404


@pytest.mark.parametrize("zip_bytes", [b"invalido", b"", make_zip([]), package(b"<xml>")])
def test_comparison_errors_are_friendly_and_preserve_previous_result(client, zip_bytes):
    compare_packages(client)
    original = client.get("/download/conciliacao-zips.json").get_json()
    response = compare_packages(client, portal=zip_bytes)
    assert response.status_code == 302
    assert response.location.endswith("tab=conciliacao-zips")
    page = client.get(response.location).get_data(as_text=True)
    assert 'message-error' in page
    assert client.get("/download/conciliacao-zips.json").get_json() == original


def test_comparison_rejects_unrelated_companies_and_preserves_state(client):
    process_sample(client)
    compare_packages(client)
    before = client.get("/download/conciliacao-zips.json").get_json()
    original_import = client.get("/download/relatorio.json").get_json()
    response = compare_packages(client, portal=package(company_xml(1, "11111111000191", "22222222000191")))
    assert response.status_code == 302
    page = client.get(response.location).get_data(as_text=True)
    assert "não pertencem à mesma empresa" in page
    assert 'message-error' in page
    assert client.get("/download/conciliacao-zips.json").get_json() == before
    assert client.get("/download/relatorio.json").get_json() == original_import


def test_comparison_accepts_mixed_incoming_and_outgoing_notes(client):
    company = "12345678000195"
    response = compare_packages(
        client,
        cliente=package(company_xml(1, company, "11111111000191"), company_xml(2, "22222222000191", company)),
        portal=package(company_xml(1, company, "11111111000191")),
    )
    assert response.status_code == 302
    assert client.get("/download/conciliacao-zips.json").get_json()["cnpjs_empresa"] == [company]


def test_comparison_rejects_more_than_5000_xmls_on_web(client):
    archive = make_zip([(f"nota-{index}.xml", b"invalido") for index in range(5001)])
    response = compare_packages(client, cliente=archive)
    assert response.status_code == 302
    assert "5000 arquivos XML" in client.get(response.location).get_data(as_text=True)
    assert client.get("/download/conciliacao-zips.json").status_code == 404


def test_comparison_requires_csrf_files_and_zip_extension(client):
    assert client.post("/comparar-zips").status_code == 400
    missing = client.post("/comparar-zips", data={"csrf_token": csrf(client)})
    assert missing.status_code == 302
    assert "Selecione os dois arquivos" in client.get(missing.location).get_data(as_text=True)
    invalid = compare_packages(client, zip_cliente=(BytesIO(package(xml())), "cliente.xml"))
    assert invalid.status_code == 302
    assert "extensão .zip" in client.get(invalid.location).get_data(as_text=True)


def test_comparison_and_xml_import_are_independent_in_both_directions(client):
    process_sample(client)
    before = client.get("/download/relatorio.json").get_json()
    compare_packages(client)
    comparison = client.get("/download/conciliacao-zips.json").get_json()
    assert client.get("/download/relatorio.json").get_json() == before
    process_sample(client)
    assert client.get("/download/conciliacao-zips.json").get_json() == comparison


def test_comparison_is_session_private_and_clearable(app, client):
    for suffix in ("xlsx", "json", "apenas-cliente.csv"):
        url = f"/download/conciliacao-zips/{suffix}" if suffix.endswith("csv") else f"/download/conciliacao-zips.{suffix}"
        assert client.get(url).status_code == 404
    compare_packages(client)
    other = app.test_client()
    assert other.get("/download/conciliacao-zips.json").status_code == 404
    assert "Limpar sessão" in client.get("/").get_data(as_text=True)
    assert client.post("/limpar-sessao", data={"csrf_token": csrf(client)}).status_code == 302
    assert client.get("/download/conciliacao-zips.json").status_code == 404


def test_comparison_upload_limit_and_memory_stream(app, client, monkeypatch):
    from app import MemoryUploadRequest
    from unittest.mock import patch
    stream = MemoryUploadRequest({})._get_file_stream(1000000, "application/zip", "arquivo.zip")
    assert isinstance(stream, BytesIO)
    csrf(client)
    with patch("tempfile.SpooledTemporaryFile", side_effect=AssertionError("Disco não permitido")):
        assert compare_packages(client).status_code == 302
    app.config["MAX_CONTENT_LENGTH"] = 200
    response = compare_packages(client)
    assert response.status_code == 413
    assert "Upload muito grande" in response.get_data(as_text=True)


def test_comparison_escapes_uploaded_data_and_reports_rejections(client):
    malicious = xml().replace(b"EMPRESA TESTE LTDA", b"&lt;script&gt;alert(1)&lt;/script&gt;")
    result = compare_packages(client, cliente=package(malicious, b"<erro>"), portal=package(xml()))
    page = client.get(result.location).get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)</script>" not in page
    assert "Avisos e rejeições (1)" in page


def test_process_page_and_downloads(client) -> None:
    process_sample(client)

    page = client.get("/?tab=resumo")
    assert page.status_code == 200
    assert b"12345" in page.data
    assert b"PRODUTO TESTE" in page.data

    json_response = client.get("/download/relatorio.json")
    payload = json.loads(json_response.data)
    assert payload["produtos"][0]["mva"] == "40%"

    excel_response = client.get("/download/relatorio.xlsx")
    workbook = openpyxl.load_workbook(BytesIO(excel_response.data), data_only=False)
    assert workbook["Produtos"].cell(2, 3).value == "'=FORMULA"

    csv_response = client.get("/download/produtos.csv?status=applicable")
    assert csv_response.status_code == 200
    assert b"'=FORMULA" in csv_response.data


def test_product_operation_filter_is_available_and_applies_to_csv(client) -> None:
    process_sample(client)

    page = client.get("/?tab=produtos")
    assert b'id="filter-operacao"' in page.data
    assert b'value="estadual"' in page.data
    assert b'value="interestadual"' in page.data

    interestadual = client.get("/download/produtos.csv?operacao=interestadual")
    estadual = client.get("/download/produtos.csv?operacao=estadual")
    combinado = client.get("/download/produtos.csv?operacao=estadual&cfop=6102")

    assert interestadual.status_code == estadual.status_code == combinado.status_code == 200
    assert "6102" in interestadual.get_data(as_text=True)
    assert "6102" not in estadual.get_data(as_text=True)
    assert "6102" not in combinado.get_data(as_text=True)


def test_product_destination_is_saved_and_exported(client) -> None:
    process_sample(client)
    page = client.get("/?tab=produtos").get_data(as_text=True)
    assert 'data-destination-url="/produtos/destinacao"' in page
    assert 'value="Comercialização"' in page
    assert 'value="Uso e Consumo"' in page
    assert 'value="Imobilizado"' in page
    products_panel = page.split('<section id="produtos"', 1)[1].split('<section id="comparacao"', 1)[0]
    assert '<th scope="col">Destinação</th>' in products_panel
    assert '<dialog id="destination-dialog"' in products_panel
    assert 'value="all">Aplicar a todos</button>' in products_panel
    assert 'value="one" autofocus>Somente este produto</button>' in products_panel
    for removed in ("Cadastro", "ST", "MVA", "CEST"):
        assert f">{removed}</th>" not in products_panel

    payload = {
        "csrf_token": "csrf-test",
        "note_index": "0",
        "product_index": "0",
        "note_key": "35210000000000000000550010000000011000000001",
        "item": "1",
        "destinacao": "Uso e Consumo",
    }
    for destination in ("Comercialização", "Imobilizado", "Uso e Consumo"):
        assert client.post(
            "/produtos/destinacao", data={**payload, "destinacao": destination}
        ).status_code == 204
    assert 'data-saved-value="Uso e Consumo"' in client.get("/?tab=produtos").get_data(as_text=True)
    csv_rows = list(csv.reader(StringIO(client.get("/download/produtos.csv").get_data(as_text=True)), delimiter=";"))
    assert csv_rows[0][-1] == "Destinação"
    assert csv_rows[1][-1] == "Uso e Consumo"
    assert "Cadastrado" not in csv_rows[0]
    assert "Status ST" not in csv_rows[0]
    assert "MVA" not in csv_rows[0]
    assert "CEST" not in csv_rows[0]
    assert json.loads(client.get("/download/relatorio.json").data)["produtos"][0]["destinacao"] == "Uso e Consumo"
    workbook = openpyxl.load_workbook(BytesIO(client.get("/download/relatorio.xlsx").data))
    headers = [cell.value for cell in workbook["Produtos"][1]]
    assert workbook["Produtos"].cell(2, headers.index("Destinação") + 1).value == "Uso e Consumo"

    for invalid in ("", "Revenda", "Imobilizado e outros"):
        assert client.post("/produtos/destinacao", data={**payload, "destinacao": invalid}).status_code == 400
    assert client.post("/produtos/destinacao", data={**payload, "csrf_token": "errado"}).status_code == 400
    assert client.post("/produtos/destinacao", data={**payload, "product_index": "1"}).status_code == 404
    assert client.post("/produtos/destinacao", data={**payload, "note_key": "outra"}).status_code == 409


def test_product_destination_can_be_applied_to_matching_ncm_across_notes(client) -> None:
    extra_products = b"""
      <det nItem="2"><prod><cProd>IGUAL</cProd><xProd>MESMO NCM</xProd>
        <NCM>21069090</NCM><CFOP>6102</CFOP><uCom>UN</uCom>
        <qCom>1</qCom><vUnCom>1</vUnCom><vProd>1</vProd></prod></det>
      <det nItem="3"><prod><cProd>DIFERENTE</cProd><xProd>OUTRO NCM</xProd>
        <NCM>22029900</NCM><CFOP>6102</CFOP><uCom>UN</uCom>
        <qCom>1</qCom><vUnCom>1</vUnCom><vProd>1</vProd></prod></det>
    """
    first_note = SAMPLE_XML.replace(b"</det>", b"</det>" + extra_products, 1)
    second_note = SAMPLE_XML.replace(
        b"35210000000000000000550010000000011000000001",
        b"35210000000000000000550010000000011000000002",
    ).replace(b"<nNF>12345</nNF>", b"<nNF>12346</nNF>")
    response = client.post(
        "/processar",
        data={
            "csrf_token": csrf(client),
            "xml_files": [(BytesIO(first_note), "primeira.xml"), (BytesIO(second_note), "segunda.xml")],
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    page = client.get("/?tab=produtos").get_data(as_text=True)
    assert page.count('data-ncm="21069090"') == 3

    payload = {
        "csrf_token": "csrf-test",
        "note_index": "0",
        "product_index": "0",
        "note_key": "35210000000000000000550010000000011000000001",
        "item": "1",
        "destinacao": "Uso e Consumo",
    }
    assert client.post("/produtos/destinacao", data=payload).status_code == 204
    products = json.loads(client.get("/download/relatorio.json").data)["produtos"]
    assert [item["destinacao"] for item in products] == ["Uso e Consumo", "", "", ""]

    assert client.post(
        "/produtos/destinacao",
        data={**payload, "destinacao": "Imobilizado", "aplicar_ncm": "1"},
    ).status_code == 204
    products = json.loads(client.get("/download/relatorio.json").data)["produtos"]
    assert [item["destinacao"] for item in products] == [
        "Imobilizado", "Imobilizado", "", "Imobilizado"
    ]
    assert client.post(
        "/produtos/destinacao", data={**payload, "aplicar_ncm": "sim"}
    ).status_code == 400


def test_rejects_post_without_csrf(client) -> None:
    response = client.post(
        "/processar",
        data={"xml_files": (BytesIO(SAMPLE_XML), "nfe.xml")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert b"Requisi" in response.data


def test_page_structure_and_security_headers(client) -> None:
    response = client.get("/")
    parser = StructureParser()
    parser.feed(response.get_data(as_text=True))

    assert len(parser.ids) == len(set(parser.ids))
    assert set(parser.label_targets) <= set(parser.ids)
    assert parser.inline_scripts == 0
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_all_tables_are_sortable_and_filters_expose_interactive_status() -> None:
    template = Path("templates/index.html").read_text(encoding="utf-8")

    assert template.count("<table") == template.count(
        '<table class="sortable-table"'
    )
    assert 'id="table-sort-status"' in template
    assert 'id="active-filters"' in template
    assert 'id="product-filter-empty"' in template


def test_register_fiscal_item_uses_temporary_catalog(app, client) -> None:
    response = client.post(
        "/base-fiscal/cadastrar",
        data={
            "csrf_token": csrf(client),
            "ncm": "88888888",
            "state": "DF",
            "internal_rate": "18%",
            "reduced_base": "Não se aplica",
            "deferral": "Não se aplica",
            "fcp": "Não se aplica",
            "exemption": "Consultar",
            "non_incidence": "Não se aplica",
            "st": "Sim",
            "mva": "40,5",
            "cest": "12.345.67",
            "suspension": "Não se aplica",
        },
    )
    assert response.status_code == 302
    records = json.loads(
        app.config["FISCAL_DATA_PATH"].read_text(encoding="utf-8")
    )
    assert len(records) == 2
    assert records[1]["MVA"] == "40,5%"


def test_processar_upload_zip(client) -> None:
    payload = make_zip([("sub/nota1.xml", SAMPLE_XML), ("nota2.XML", SAMPLE_XML)])
    response = client.post(
        "/processar",
        data={"csrf_token": csrf(client), "xml_files": (BytesIO(payload), "lote.ZIP")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert "tab=resumo" in response.location
    page = client.get(response.location).get_data(as_text=True)
    assert "2 nota(s) processada(s) com sucesso" in page
    assert "ZIP processado: lote.ZIP (2 XML(s) extraídos)" in page
    report = json.loads(client.get("/download/relatorio.json").data)
    assert len(report["produtos"]) == 2


def test_processar_invalid_zip_has_friendly_error(client) -> None:
    response = client.post(
        "/processar",
        data={"csrf_token": csrf(client), "xml_files": (BytesIO(b"falso"), "lote.zip")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "não é um ZIP válido" in page
    assert "Nenhuma NF-e válida" in page


def test_processar_mixed_files_preserves_valid_notes_and_reports_rejections(client) -> None:
    payload = make_zip([
        ("../../compactada.xml", SAMPLE_XML),
        ("invalido.xml", b"<xml>"),
        ("leia-me.txt", b"ignore"),
    ])
    response = client.post(
        "/processar",
        data={
            "csrf_token": csrf(client),
            "xml_files": [
                (BytesIO(SAMPLE_XML), "avulsa.xml"),
                (BytesIO(payload), "lote.zip"),
                (BytesIO(b"falso"), "corrompido.zip"),
            ],
        },
        content_type="multipart/form-data",
    )
    assert "tab=resumo" in response.location
    page = client.get(response.location).get_data(as_text=True)
    assert "2 nota(s) processada(s) com sucesso" in page
    assert "invalido.xml" in page
    assert "corrompido.zip" in page
    assert "../../compactada.xml" not in page


def test_processar_zip_limits_and_empty_archives(client, monkeypatch) -> None:
    monkeypatch.setattr("app.MAX_ZIP_ENTRIES", 1)
    payload = make_zip([("a.xml", SAMPLE_XML), ("b.xml", SAMPLE_XML)])
    response = client.post(
        "/processar",
        data={"csrf_token": csrf(client), "xml_folder": (BytesIO(payload), "lote.zip")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "entradas demais" in response.get_data(as_text=True)
    empty = client.post(
        "/processar",
        data={"csrf_token": csrf(client), "xml_files": (BytesIO(make_zip([])), "vazio.zip")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "O ZIP não contém arquivos XML" in empty.get_data(as_text=True)


def test_processar_enforces_total_budget_across_archives(client, monkeypatch) -> None:
    monkeypatch.setattr("app.MAX_ZIP_TOTAL_BYTES", len(SAMPLE_XML))
    payload = make_zip([("nota.xml", SAMPLE_XML)])
    response = client.post(
        "/processar",
        data={
            "csrf_token": csrf(client),
            "xml_files": [(BytesIO(payload), "primeiro.zip"), (BytesIO(payload), "segundo.zip")],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)
    assert "1 nota(s) processada(s) com sucesso" in page
    assert "descompactado total" in page


def test_large_zip_upload_stays_in_memory(client, monkeypatch) -> None:
    from zipfile import ZIP_STORED
    from core.zip_extractor import extract_xmls_from_zip

    streams = []

    def inspect_stream(source, **kwargs):
        assert isinstance(source, BytesIO)
        streams.append(source)
        return extract_xmls_from_zip(source, **kwargs)

    monkeypatch.setattr("app.extract_xmls_from_zip", inspect_stream)
    payload = make_zip([("nota.xml", SAMPLE_XML + b"<!--" + b"x" * 600_000 + b"-->")], ZIP_STORED)
    response = client.post(
        "/processar",
        data={"csrf_token": csrf(client), "xml_files": (BytesIO(payload), "grande.zip")},
        content_type="multipart/form-data",
    )
    assert "tab=resumo" in response.location
    assert len(streams) == 1
    assert streams[0].closed


def test_zip_upload_respects_request_size_limit(app, client) -> None:
    token = csrf(client)
    app.config["MAX_CONTENT_LENGTH"] = 100
    response = client.post(
        "/processar",
        data={"csrf_token": token, "xml_files": (BytesIO(make_zip([("n.xml", SAMPLE_XML)])), "lote.zip")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 413


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_zip_xml_dtd_cannot_bypass_parser(client, encoding) -> None:
    hostile = (" " * 5000 + '<!DOCTYPE foo [<!ENTITY x "hostil">]><foo>&x;</foo>').encode(encoding)
    response = client.post(
        "/processar",
        data={
            "csrf_token": csrf(client),
            "xml_files": (BytesIO(make_zip([("hostil.xml", hostile)])), "lote.zip"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "XML com DTD ou entidade não é aceito" in response.get_data(as_text=True)
