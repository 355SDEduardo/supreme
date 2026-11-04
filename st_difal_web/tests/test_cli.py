from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cli import (
    build_parser,
    confirm_operation,
    find_xml_files,
    parse_xml_files,
    run_cli,
)
from tests.sample_data import SAMPLE_XML, fiscal_record
from tests.test_zip_extractor import make_zip
from tests.test_zip_comparison import package, xml, company_xml


def test_cli_zip_comparison_exports_and_summary(tmp_path, capsys):
    from io import BytesIO
    import openpyxl
    cliente, portal = tmp_path / "cliente.zip", tmp_path / "portal.zip"
    cliente.write_bytes(package(xml(1), xml(2)))
    portal.write_bytes(package(xml(2, "120"), xml(3)))
    excel, report, csv = tmp_path / "out.xlsx", tmp_path / "out.json", tmp_path / "out.csv"
    args = build_parser().parse_args(["--comparar-zips", str(cliente), str(portal), "--excel", str(excel), "--json", str(report), "--csv", str(csv)])
    assert run_cli(args) == 0
    assert len(openpyxl.load_workbook(BytesIO(excel.read_bytes())).sheetnames) == 5
    assert json.loads(report.read_text(encoding="utf-8"))["resumo"]["total_comuns"] == 1
    for group in ("apenas-cliente", "apenas-portal", "em-ambos", "divergencias"):
        assert (tmp_path / f"out_{group}.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    output = capsys.readouterr().out
    assert "CONCILIAÇÃO FISCAL" in output
    assert "Empresa validada" in output
    assert "Apenas no Portal (Faltando no Cliente): 1 notas" in output


@pytest.mark.parametrize("bad", [b"corrompido", make_zip([])])
def test_cli_comparison_rejects_invalid_zip_without_output(tmp_path, capsys, bad):
    cliente, portal, excel = tmp_path / "cliente.zip", tmp_path / "portal.zip", tmp_path / "out.xlsx"
    cliente.write_bytes(bad)
    portal.write_bytes(package(xml()))
    args = build_parser().parse_args(["--comparar-zips", str(cliente), str(portal), "--excel", str(excel)])
    assert run_cli(args) == 1
    assert "Erro na conciliação" in capsys.readouterr().err
    assert not excel.exists()


def test_cli_comparison_rejects_unrelated_companies_without_export(tmp_path, capsys):
    cliente, portal, output = tmp_path / "cliente.zip", tmp_path / "portal.zip", tmp_path / "out.xlsx"
    cliente.write_bytes(package(xml()))
    portal.write_bytes(package(company_xml(2, "11111111000191", "22222222000191")))
    args = build_parser().parse_args(["--comparar-zips", str(cliente), str(portal), "--excel", str(output)])
    assert run_cli(args) == 1
    assert "não pertencem à mesma empresa" in capsys.readouterr().err
    assert not output.exists()


def test_cli_comparison_handles_missing_file_output_error_and_wrong_extension(tmp_path, capsys):
    cliente, portal = tmp_path / "cliente.zip", tmp_path / "portal.zip"
    portal.write_bytes(package(xml()))
    args = build_parser().parse_args(["--comparar-zips", str(cliente), str(portal)])
    assert run_cli(args) == 1
    cliente.write_bytes(package(xml()))
    args.excel = tmp_path / "inexistente" / "out.xlsx"
    assert run_cli(args) == 1
    args.comparar_zips[0] = tmp_path / "cliente.xml"
    assert run_cli(args) == 1


def test_cli_comparison_prevents_overwriting_inputs_or_colliding_outputs(tmp_path):
    cliente, portal = tmp_path / "cliente.zip", tmp_path / "portal.zip"
    cliente.write_bytes(package(xml()))
    portal.write_bytes(package(xml()))
    original = cliente.read_bytes()
    args = build_parser().parse_args(["--comparar-zips", str(cliente), str(portal), "--excel", str(cliente)])
    assert run_cli(args) == 1
    assert cliente.read_bytes() == original
    args.excel = tmp_path / "out.xlsx"
    args.json = args.excel
    assert run_cli(args) == 1


def test_cli_comparison_subprocess_exit_code(tmp_path):
    import subprocess
    import sys
    cliente, portal, excel = tmp_path / "cliente.zip", tmp_path / "portal.zip", tmp_path / "out.xlsx"
    cliente.write_bytes(package(xml()))
    portal.write_bytes(package(xml()))
    process = subprocess.run([sys.executable, "cli.py", "--comparar-zips", str(cliente), str(portal), "--excel", str(excel)], capture_output=True)
    assert process.returncode == 0, process.stderr
    assert excel.exists()


def test_find_xml_files_in_folder_and_recursive(tmp_path: Path) -> None:
    sub = tmp_path / "subfolder"
    sub.mkdir()

    file1 = tmp_path / "nfe1.xml"
    file1.write_bytes(SAMPLE_XML)

    file2 = sub / "nfe2.xml"
    file2.write_bytes(SAMPLE_XML)

    file_txt = tmp_path / "other.txt"
    file_txt.write_text("ignorar")

    # Busca recursiva
    found_recursive = find_xml_files([tmp_path], recursive=True)
    assert len(found_recursive) == 2
    assert file1 in found_recursive
    assert file2 in found_recursive

    # Busca não recursiva
    found_flat = find_xml_files([tmp_path], recursive=False)
    assert len(found_flat) == 1
    assert file1 in found_flat


def test_parse_xml_files_processes_batch_and_reports_issues(tmp_path: Path) -> None:
    valid_file = tmp_path / "valido.xml"
    valid_file.write_bytes(SAMPLE_XML)

    broken_file = tmp_path / "invalido.xml"
    broken_file.write_bytes(b"<xml>corrompido sem fechar")

    files = [valid_file, broken_file]
    nfes, issues = parse_xml_files(files, show_progress=False)

    assert len(nfes) == 1
    assert nfes[0].numero == "12345"
    assert len(issues) == 1
    assert issues[0].filename == "invalido.xml"


def test_confirm_operation_interactive_inputs() -> None:
    with patch("builtins.input", return_value="1"):
        assert confirm_operation() == "interestadual"

    with patch("builtins.input", return_value="2"):
        assert confirm_operation() == "estadual"

    with patch("builtins.input", return_value="3"):
        assert confirm_operation() == "ambos"

    with patch("builtins.input", return_value=""):
        assert confirm_operation(default="ambos") == "ambos"

    with patch("builtins.input", return_value="opcao_invalida"):
        assert confirm_operation(default="estadual") == "estadual"


def test_run_cli_with_operation_and_exports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Cria XML interestadual (CFOP 6102)
    xml_inter = tmp_path / "nfe_inter.xml"
    xml_inter.write_bytes(SAMPLE_XML)

    # Cria XML estadual (modificando CFOP para 5102)
    xml_estadual_content = SAMPLE_XML.replace(b"<CFOP>6102</CFOP>", b"<CFOP>5102</CFOP>").replace(
        b"<nNF>12345</nNF>", b"<nNF>54321</nNF>"
    )
    xml_intra = tmp_path / "nfe_intra.xml"
    xml_intra.write_bytes(xml_estadual_content)

    # Cria base fiscal
    fiscal_path = tmp_path / "fiscal.json"
    fiscal_path.write_text(json.dumps([fiscal_record()], ensure_ascii=False), encoding="utf-8")

    csv_out = tmp_path / "out.csv"
    excel_out = tmp_path / "out.xlsx"
    json_out = tmp_path / "out.json"

    parser = build_parser()

    # 1. Testar listagem apenas estadual
    args_estadual = parser.parse_args([
        str(tmp_path),
        "--operacao", "estadual",
        "--base-fiscal", str(fiscal_path),
        "--csv", str(csv_out),
    ])
    code = run_cli(args_estadual)
    assert code == 0
    captured = capsys.readouterr().out
    assert "SELECIONADA: ESTADUAL" in captured.upper()
    assert "54321" in captured
    assert "12345" not in captured  # A nota interestadual não deve aparecer na tabela
    assert csv_out.exists()

    # 2. Testar listagem apenas interestadual
    args_inter = parser.parse_args([
        str(tmp_path),
        "--operacao", "interestadual",
        "--base-fiscal", str(fiscal_path),
        "--excel", str(excel_out),
    ])
    code = run_cli(args_inter)
    assert code == 0
    captured = capsys.readouterr().out
    assert "SELECIONADA: INTERESTADUAL" in captured.upper()
    assert "12345" in captured
    assert "54321" not in captured
    assert excel_out.exists()

    # 3. Testar listagem ambos
    args_ambos = parser.parse_args([
        str(tmp_path),
        "--operacao", "ambos",
        "--base-fiscal", str(fiscal_path),
        "--json", str(json_out),
    ])
    code = run_cli(args_ambos)
    assert code == 0
    captured = capsys.readouterr().out
    assert "SELECIONADA: AMBOS" in captured.upper()
    assert "12345" in captured
    assert "54321" in captured
    assert json_out.exists()


def test_run_cli_no_xmls_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty_folder = tmp_path / "vazia"
    empty_folder.mkdir()

    parser = build_parser()
    args = parser.parse_args([str(empty_folder), "--operacao", "ambos"])
    code = run_cli(args)
    assert code == 1
    err = capsys.readouterr().err
    assert "Nenhum arquivo XML encontrado" in err


def test_run_cli_processes_large_batch_beyond_web_limit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    batch_folder = tmp_path / "lote_grande"
    batch_folder.mkdir()

    total_xmls = 250  # O web app limita em 200; o CLI não possui limite
    xml_data = SAMPLE_XML
    for i in range(total_xmls):
        file_path = batch_folder / f"nfe_{i:04d}.xml"
        file_path.write_bytes(xml_data)

    parser = build_parser()
    args = parser.parse_args([str(batch_folder), "--operacao", "ambos", "--quiet"])
    code = run_cli(args)
    assert code == 0

    captured = capsys.readouterr().out
    assert f"Localizado(s) {total_xmls} arquivo(s) XML" in captured
    assert f"NF-es Processadas com Sucesso: {total_xmls}" in captured


def test_view_csv_formats_table_and_respects_limits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from cli import view_csv

    csv_file = tmp_path / "produtos_teste.csv"
    csv_file.write_text(
        "NF-e;Item;Código;Descrição;NCM;CST;CFOP;Qtd.;UN;Valor Unit.;Valor Total;ICMS;BC ST;ICMS ST;Cadastrado;Status ST;MVA;CEST;Destinação\r\n"
        "12345;1;P001;PRODUTO PARAFUSO;21069090;10;6102;2,00;UN;10,50;21,00;3,78;30,00;5,00;Sim;Sim;40%;1234567;Comercialização\r\n"
        "54321;1;P002;OUTRO ITEM;21069090;10;5102;1,00;UN;15,00;15,00;2,70;0,00;0,00;Sim;Não;0%;;Uso e Consumo\r\n",
        encoding="utf-8-sig",
    )

    # 1. Visualização normal
    code = view_csv(csv_file)
    assert code == 0
    out = capsys.readouterr().out
    assert "VISUALIZAÇÃO DO CSV: PRODUTOS_TESTE.CSV" in out.upper() or "PRODUTOS_TESTE.CSV" in out
    assert "PRODUTO PARAFUSO" in out
    assert "OUTRO ITEM" in out

    # 2. Busca por termo
    code_search = view_csv(csv_file, search="PARAFUSO")
    assert code_search == 0
    out_search = capsys.readouterr().out
    assert "PRODUTO PARAFUSO" in out_search
    assert "OUTRO ITEM" not in out_search

    # 3. Limite de linhas
    code_limit = view_csv(csv_file, limit=1)
    assert code_limit == 0
    out_limit = capsys.readouterr().out
    assert "PRODUTO PARAFUSO" in out_limit
    assert "OUTRO ITEM" not in out_limit
    assert "Exibindo os primeiros 1 de 2 produtos" in out_limit


def test_view_csv_nonexistent_and_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from cli import view_csv

    missing = tmp_path / "inexistente.csv"
    code = view_csv(missing)
    assert code == 1
    err = capsys.readouterr().err
    assert "Arquivo CSV não encontrado" in err

    empty = tmp_path / "vazio.csv"
    empty.write_text("", encoding="utf-8-sig")
    code_empty = view_csv(empty)
    assert code_empty == 0
    out = capsys.readouterr().out
    assert "está vazio" in out


def test_run_cli_with_visualizar_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from cli import build_parser, run_cli

    csv_file = tmp_path / "produtos.csv"
    csv_file.write_text(
        "NF-e;Item;Código;Descrição;NCM;CST;CFOP;Qtd.;UN;Valor Unit.;Valor Total;ICMS;BC ST;ICMS ST;Cadastrado;Status ST;MVA;CEST;Destinação\r\n"
        "12345;1;P001;TESTE VISUALIZAR;21069090;10;6102;1,00;UN;10,00;10,00;1,80;0,00;0,00;Sim;Não;;;\r\n",
        encoding="utf-8-sig",
    )

    parser = build_parser()
    args = parser.parse_args(["--visualizar-csv", str(csv_file)])
    code = run_cli(args)
    assert code == 0
    out = capsys.readouterr().out
    assert "TESTE VISUALIZAR" in out


def test_run_cli_processes_zip_and_exports_products(tmp_path, capsys) -> None:
    archive = tmp_path / "lote.ZIP"
    archive.write_bytes(make_zip([("sub/nota.xml", SAMPLE_XML), ("erro.xml", b"<xml>")]))
    output = tmp_path / "out.json"
    args = build_parser().parse_args([str(archive), "--operacao", "ambos", "--json", str(output)])
    assert run_cli(args) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["produtos"][0]["nfe_numero"] == "12345"
    captured = capsys.readouterr().out
    assert "2 XML(s) localizados" in captured
    assert "erro.xml" in captured
    assert "PRODUTO TESTE" in captured


def test_find_zip_in_folders_and_deduplicate_targets(tmp_path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    archive = sub / "lote.ZIP"
    archive.write_bytes(make_zip([("nota.xml", SAMPLE_XML)]))
    assert find_xml_files([tmp_path, archive]) == [archive]
    assert find_xml_files([tmp_path], recursive=False) == []


def test_parse_zip_rejections_do_not_drop_other_sources(tmp_path) -> None:
    archive = tmp_path / "falso.zip"
    archive.write_bytes(b"falso")
    xml = tmp_path / "avulsa.xml"
    xml.write_bytes(SAMPLE_XML)
    nfes, issues = parse_xml_files([archive, xml], show_progress=False)
    assert len(nfes) == 1
    assert issues[0].filename == "falso.zip"
    assert "ZIP válido" in issues[0].message


def test_run_cli_invalid_zip_returns_failure(tmp_path, capsys) -> None:
    archive = tmp_path / "falso.zip"
    archive.write_bytes(b"falso")
    args = build_parser().parse_args([str(archive), "--operacao", "ambos"])
    assert run_cli(args) == 1
    captured = capsys.readouterr()
    assert "ZIP válido" in captured.out
    assert "Nenhuma NF-e válida" in captured.err
