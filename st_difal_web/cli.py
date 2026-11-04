#!/usr/bin/env python3
"""Análise de NF-es e produtos a partir de XMLs avulsos e ZIPs com leitura segura."""

from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from core.models import ComparisonSummary, NfeData, ParseIssue
from core.ncm_comparison import (
    ANALYZED_CFOP_PREFIXES,
    ESTADUAL_CFOP_PREFIXES,
    compare_nfes,
    load_fiscal_catalog,
)
from core.nfe_parser import NfeParser
from core.zip_extractor import extract_xmls_from_zip
from core.zip_comparison import compare_nfe_zips
from core.reporting import (
    csv_download,
    excel_download,
    json_download,
    parse_number,
    product_rows,
    report_payload,
    zip_comparison_excel,
    zip_comparison_payload,
    zip_comparison_csv,
    zip_comparison_divergences_csv,
)
from core.nfse_pipeline import path_inputs, process_nfse_batch
from core.nfse_models import FindingSeverity
from core.nfse_reporting import (
    build_nfse_json_payload, generate_nfse_excel_report, generate_nfse_csv_notes,
    generate_nfse_csv_findings,
)

DEFAULT_FISCAL_PATH = Path(__file__).resolve().parent / "data" / "fiscal_data.json"

OPERATION_CHOICES = ("interestadual", "estadual", "ambos")


def confirm_operation(default: str = "ambos") -> str:
    """Solicita ao usuário a confirmação do tipo de operação quando não informado via CLI."""
    print("\n" + "=" * 62)
    print("SELEÇÃO DE OPERAÇÃO DOS PRODUTOS")
    print("=" * 62)
    print(" [1] Interestadual (CFOP 6xxx)")
    print(" [2] Estadual (CFOP 5xxx)")
    print(" [3] Ambos (Estaduais e Interestaduais)")
    print("=" * 62)

    prompt = f"Escolha uma opção [1/2/3] (padrão: 3 - Ambos): "
    try:
        user_input = input(prompt).strip().casefold()
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada pelo usuário.")
        sys.exit(0)

    mapping = {
        "1": "interestadual",
        "interestadual": "interestadual",
        "inter": "interestadual",
        "2": "estadual",
        "estadual": "estadual",
        "intra": "estadual",
        "3": "ambos",
        "ambos": "ambos",
        "ambas": "ambos",
        "": default,
    }

    selected = mapping.get(user_input)
    if not selected:
        print(f"Opção '{user_input}' inválida. Utilizando padrão: {default.title()}.")
        return default
    return selected


def find_xml_files(targets: Iterable[str | Path], recursive: bool = True) -> list[Path]:
    """Descobre XMLs e ZIPs, mantendo o nome da função para compatibilidade."""
    found: list[Path] = []
    seen: set[Path] = set()

    for target in targets:
        path = Path(target).resolve()
        if not path.exists():
            print(f"Aviso: Caminho não encontrado: {path}", file=sys.stderr)
            continue

        if path.is_file():
            if path.suffix.casefold() in {".xml", ".zip"} and path not in seen:
                found.append(path)
                seen.add(path)
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            for file_path in path.glob(pattern):
                if (
                    file_path.is_file()
                    and file_path.suffix.casefold() in {".xml", ".zip"}
                    and file_path not in seen
                ):
                    found.append(file_path)
                    seen.add(file_path)

    return sorted(found)


def parse_xml_files(
    xml_paths: list[Path],
    show_progress: bool = True,
) -> tuple[list[NfeData], list[ParseIssue]]:
    """Processa XMLs avulsos e ZIPs com limites de descompressão por pacote."""
    parser = NfeParser()
    nfes: list[NfeData] = []
    issues: list[ParseIssue] = []
    total = len(xml_paths)

    for index, file_path in enumerate(xml_paths, start=1):
        if show_progress and (index % 25 == 0 or index == total or total < 50):
            sys.stdout.write(f"\rProcessando XMLs: {index}/{total} ({(index/total)*100:.1f}%)")
            sys.stdout.flush()

        try:
            if file_path.suffix.casefold() == ".zip":
                with file_path.open("rb") as stream:
                    extracted = extract_xmls_from_zip(stream, zip_filename=file_path.name)
                issues.extend(extracted.issues)
                xml_files = extracted.xml_files
                print(f"\nZIP processado: {file_path.name} ({len(xml_files)} XML(s) localizados).")
                if not xml_files and not extracted.issues:
                    issues.append(ParseIssue(file_path.name, "O ZIP não contém arquivos XML."))
            else:
                xml_files = [(file_path.name, file_path.read_bytes())]
            for filename, content in xml_files:
                try:
                    nfes.append(parser.parse_bytes(content, filename))
                except ValueError as exc:
                    issues.append(ParseIssue(filename, str(exc)))
        except (OSError, ValueError) as exc:
            issues.append(ParseIssue(file_path.name, str(exc)))

    if show_progress and total > 0:
        sys.stdout.write("\n")
        sys.stdout.flush()

    return nfes, issues


def format_currency_br(value: object) -> str:
    """Formata valor numérico como moeda brasileira."""
    try:
        val = float(parse_number(value))
        formatted = f"{val:,.2f}"
    except (TypeError, ValueError):
        formatted = "0.00"
    return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_decimal_br(value: object) -> str:
    """Formata quantidade ou número com duas casas decimais no padrão brasileiro."""
    try:
        val = float(parse_number(value))
        formatted = f"{val:,.2f}"
    except (TypeError, ValueError):
        formatted = "0.00"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def print_products_table(products: list[dict[str, Any]], limit: int | None = None) -> None:
    """Exibe no terminal a listagem de produtos formatada em tabela."""
    if not products:
        print("\nNenhum produto encontrado para os critérios selecionados.")
        return

    items_to_display = products if (limit is None or limit <= 0) else products[:limit]

    # Cabeçalho da tabela
    headers = [
        ("NF-e", 7),
        ("Item", 4),
        ("Código", 12),
        ("Descrição", 32),
        ("NCM", 9),
        ("CFOP", 5),
        ("CST", 4),
        ("Qtd", 8),
        ("UN", 3),
        ("Vlr Unit", 11),
        ("Vlr Total", 12),
        ("ICMS", 10),
        ("BC ST", 10),
        ("ICMS ST", 10),
        ("ST", 5),
        ("Cadastrado", 10),
    ]

    header_line = " | ".join(label.ljust(width) for label, width in headers)
    separator = "-+-".join("-" * width for _, width in headers)

    print("\n" + separator)
    print(header_line)
    print(separator)

    for item in items_to_display:
        desc = str(item.get("descricao", ""))
        if len(desc) > 32:
            desc = desc[:29] + "..."

        row_fields = [
            str(item.get("nfe", "")).ljust(7),
            str(item.get("item", "")).rjust(4),
            str(item.get("codigo", "")[:12]).ljust(12),
            desc.ljust(32),
            str(item.get("ncm", "")).ljust(9),
            str(item.get("cfop", "")).ljust(5),
            str(item.get("cst", "")).ljust(4),
            format_decimal_br(item.get("quantidade", 0)).rjust(8),
            str(item.get("unidade", "")[:3]).ljust(3),
            format_currency_br(item.get("valor_unitario", 0)).rjust(11),
            format_currency_br(item.get("valor_total", 0)).rjust(12),
            format_currency_br(item.get("valor_icms", 0)).rjust(10),
            format_currency_br(item.get("valor_bc_st", 0)).rjust(10),
            format_currency_br(item.get("valor_icms_st", 0)).rjust(10),
            str(item.get("st", "")[:5]).center(5),
            str(item.get("ncm_cadastrado", "")[:10]).center(10),
        ]
        print(" | ".join(row_fields))

    print(separator)

    if limit and limit > 0 and len(products) > limit:
        print(
            f"Exibindo os primeiros {limit} produtos de um total de {len(products)}. "
            "Use '--limite 0' para exibir todos ou exporte para Excel/CSV."
        )


def calculate_product_totals(products: list[dict[str, Any]]) -> dict[str, Decimal]:
    """Calcula os totais consolidados para a listagem de produtos."""
    tot_qtd = Decimal("0")
    tot_produtos = Decimal("0")
    tot_icms = Decimal("0")
    tot_bc_st = Decimal("0")
    tot_icms_st = Decimal("0")

    for p in products:
        tot_qtd += parse_number(p.get("quantidade", 0))
        tot_produtos += parse_number(p.get("valor_total", 0))
        tot_icms += parse_number(p.get("valor_icms", 0))
        tot_bc_st += parse_number(p.get("valor_bc_st", 0))
        tot_icms_st += parse_number(p.get("valor_icms_st", 0))

    return {
        "quantidade": tot_qtd,
        "valor_produtos": tot_produtos,
        "valor_icms": tot_icms,
        "valor_bc_st": tot_bc_st,
        "valor_icms_st": tot_icms_st,
        "valor_total": tot_produtos + tot_icms_st,
    }


def print_totals_summary(products: list[dict[str, Any]], nfes_count: int, issues_count: int) -> None:
    """Exibe o resumo estatístico e financeiro consolidado."""
    tot = calculate_product_totals(products)

    print("\n" + "=" * 50)
    print("RESUMO CONSOLIDADO")
    print("=" * 50)
    print(f"NF-es Processadas com Sucesso: {nfes_count}")
    if issues_count > 0:
        print(f"Rejeições / Erros de Leitura : {issues_count}")
    print(f"Total de Produtos Listados   : {len(products)}")
    print(f"Quantidade Total de Itens    : {format_decimal_br(tot['quantidade'])}")
    print("-" * 50)
    print(f"Valor Total dos Produtos     : {format_currency_br(tot['valor_produtos'])}")
    print(f"Total ICMS Próprio           : {format_currency_br(tot['valor_icms'])}")
    print(f"Total Base de Cálculo ST     : {format_currency_br(tot['valor_bc_st'])}")
    print(f"Total ICMS ST                : {format_currency_br(tot['valor_icms_st'])}")
    print(f"Valor Total Geral (Prod + ST): {format_currency_br(tot['valor_total'])}")
    print("=" * 50 + "\n")


def export_results(
    nfes: list[NfeData],
    products: list[dict[str, Any]],
    issues: list[ParseIssue],
    *,
    excel_path: Path | None = None,
    csv_path: Path | None = None,
    json_path: Path | None = None,
) -> None:
    """Exporta os resultados para Excel, CSV ou JSON."""
    if excel_path:
        excel_path.parent.mkdir(parents=True, exist_ok=True)
        excel_bytes = excel_download(nfes)
        excel_path.write_bytes(excel_bytes)
        print(f"Relatório Excel salvo com sucesso em: {excel_path.resolve()}")

    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        columns = [
            ("nfe", "NF-e"),
            ("item", "Item"),
            ("codigo", "Código"),
            ("descricao", "Descrição"),
            ("ncm", "NCM"),
            ("cst", "CST"),
            ("cfop", "CFOP"),
            ("quantidade", "Qtd."),
            ("unidade", "UN"),
            ("valor_unitario", "Valor Unit."),
            ("valor_total", "Valor Total"),
            ("valor_icms", "ICMS"),
            ("valor_bc_st", "BC ST"),
            ("valor_icms_st", "ICMS ST"),
            ("ncm_cadastrado", "Cadastrado"),
            ("st", "Status ST"),
            ("mva", "MVA"),
            ("cest", "CEST"),
            ("destinacao", "Destinação"),
        ]
        csv_bytes = csv_download(products, columns)
        csv_path.write_bytes(csv_bytes)
        print(f"Relatório CSV salvo com sucesso em: {csv_path.resolve()}")

    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = report_payload(nfes, issues)
        payload["produtos_filtrados"] = products
        json_bytes = json_download(payload)
        json_path.write_bytes(json_bytes)
        print(f"Relatório JSON salvo com sucesso em: {json_path.resolve()}")


def view_csv(
    csv_path: str | Path,
    *,
    limit: int | None = 50,
    search: str = "",
) -> int:
    """Lê e exibe o conteúdo de um arquivo CSV gerado formatado em tabela no terminal."""
    path = Path(csv_path).resolve()
    if not path.exists() or not path.is_file():
        print(f"Erro: Arquivo CSV não encontrado: {path}", file=sys.stderr)
        return 1

    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        print(f"Erro ao abrir arquivo CSV: {exc}", file=sys.stderr)
        return 1

    reader = csv.reader(content.splitlines(), delimiter=";")
    rows = [row for row in reader if row]
    if not rows:
        print(f"\nO arquivo CSV '{path.name}' está vazio.")
        return 0

    header = rows[0]
    data_rows = rows[1:]

    # Filtro opcional por termo de busca
    if search:
        term = search.casefold()
        data_rows = [row for row in data_rows if any(term in str(cell).casefold() for cell in row)]

    total_rows = len(data_rows)
    print("\n" + "=" * 90)
    print(f"VISUALIZAÇÃO DO CSV: {path.name}")
    print(f"Arquivo : {path}")
    print(f"Total   : {total_rows} produto(s) listado(s) | {len(header)} coluna(s)")
    print("=" * 90)

    if not data_rows:
        if search:
            print(f"Nenhum registro encontrado contendo o termo: '{search}'")
        else:
            print("Nenhum registro cadastrado no CSV.")
        print("=" * 90 + "\n")
        return 0

    displayed_rows = data_rows if (limit is None or limit <= 0) else data_rows[:limit]

    def clean_cell(val: str) -> str:
        # Remove caractere de escape de planilha (') se presente no início
        if val.startswith("'") and len(val) > 1 and val[1] in ("=", "+", "-", "@"):
            return val[1:]
        return val

    num_cols = len(header)
    col_widths = []
    for col_idx in range(num_cols):
        h_name = header[col_idx]
        max_len = len(h_name)
        for r in displayed_rows:
            if col_idx < len(r):
                cell_text = clean_cell(r[col_idx])
                if len(cell_text) > max_len:
                    max_len = len(cell_text)
        if "descri" in h_name.casefold():
            width = min(max(max_len, 10), 32)
        else:
            width = min(max(max_len, 4), 16)
        col_widths.append(width)

    header_cells = [header[i][:col_widths[i]].center(col_widths[i]) for i in range(num_cols)]
    header_line = " | ".join(header_cells)
    sep_line = "-+-".join("-" * col_widths[i] for i in range(num_cols))

    print(sep_line)
    print(header_line)
    print(sep_line)

    for r in displayed_rows:
        row_cells = []
        for i in range(num_cols):
            val = clean_cell(r[i]) if i < len(r) else ""
            w = col_widths[i]
            if len(val) > w:
                val = val[:w - 3] + "..."
            h_lower = header[i].casefold()
            if any(k in h_lower for k in ("valor", "qtd", "icms", "st", "bc", "item")):
                row_cells.append(val.rjust(w))
            else:
                row_cells.append(val.ljust(w))
        print(" | ".join(row_cells))

    print(sep_line)

    if limit and limit > 0 and total_rows > limit:
        print(
            f"Exibindo os primeiros {limit} de {total_rows} produtos. "
            f"Use '--limite 0' para visualizar todos os registros do CSV."
        )
    print("=" * 90 + "\n")
    return 0


class FiscalArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        tokens = list(sys.argv[1:] if args is None else args)
        # Preserve NF-e's historical -o/--operacao; in NFS-e mode -o exports Excel.
        if '--nfse' in tokens:
            tokens = ['--output-excel' if token == '-o' else token for token in tokens]
        return super().parse_args(tokens, namespace)


def build_parser() -> argparse.ArgumentParser:
    """Constrói o parser de argumentos de linha de comando."""
    parser = FiscalArgumentParser(
        description="Conferidor NF-e CLI: Análise em lote de XMLs e ZIPs com listagem de produtos e descompressão segura.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "caminho",
        nargs="*",
        help="Caminho para arquivo(s) XML/ZIP ou pasta(s) contendo XMLs e ZIPs. Se omitido, busca na pasta atual.",
    )
    parser.add_argument(
        "-p",
        "--path",
        dest="target_path",
        help="Caminho explícito para pasta ou arquivo XML/ZIP.",
    )
    parser.add_argument(
        "-o",
        "--operacao",
        choices=OPERATION_CHOICES,
        help="Tipo de operação: interestadual (CFOP 6xxx), estadual (CFOP 5xxx) ou ambos. Se omitido, solicita confirmação.",
    )
    parser.add_argument(
        "-b",
        "--base-fiscal",
        type=Path,
        default=DEFAULT_FISCAL_PATH,
        help="Caminho para arquivo JSON da base fiscal para comparação de NCM/ST.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Desativa busca recursiva de XMLs e ZIPs em subpastas.",
    )
    parser.add_argument(
        "--excel",
        type=Path,
        help="Caminho para exportar relatório completo em Excel (.xlsx).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Caminho para exportar lista de produtos em CSV (.csv).",
    )
    parser.add_argument(
        "--visualizar-csv",
        type=Path,
        dest="visualizar_csv",
        help="Caminho para arquivo CSV a ser visualizado formatado no terminal.",
    )
    parser.add_argument(
        "--visualizar",
        action="store_true",
        help="Exibe o CSV gerado no terminal imediatamente após a exportação.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Caminho para exportar dados completos em JSON (.json).",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=100,
        help="Limite de produtos exibidos no terminal (use 0 para exibir todos).",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Modo silencioso: omite a tabela de produtos e exibe apenas o resumo.",
    )
    parser.add_argument(
        "--filtro-ncm",
        help="Filtrar produtos por NCM específico.",
    )
    parser.add_argument(
        "--filtro-cfop",
        help="Filtrar produtos por CFOP específico.",
    )
    parser.add_argument(
        "--filtro-cst",
        help="Filtrar produtos por CST específico.",
    )
    parser.add_argument(
        "--filtro-status",
        choices=["registered", "unregistered", "applicable"],
        help="Filtrar por status do NCM: registered (cadastrado), unregistered (não cadastrado) ou applicable (sujeito à ST).",
    )
    parser.add_argument(
        "--busca",
        help="Busca textual por código ou descrição do produto.",
    )

    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--nfse', action='store_true', help='Auditoria de NFS-e (XML/ZIP/pasta). -o exporta Excel neste modo.')
    parser.add_argument('--input', '-i', type=Path, help='Entrada do modo --nfse.')
    parser.add_argument('--output-excel', type=Path, help='Relatório Excel de NFS-e.')
    parser.add_argument('--output-csv', type=Path, help='Prefixo para CSVs de notas e apontamentos NFS-e.')
    parser.add_argument('--output-json', type=Path, help='Relatório JSON de NFS-e.')
    parser.add_argument('--min-severity', choices=['CRITICAL', 'HIGH', 'WARNING', 'INFO'], default='WARNING',
                        help='Severidade mínima exibida no console NFS-e; exportações contêm todos os apontamentos.')
    modes.add_argument(
        "--comparar-zips", nargs=2, type=Path, metavar=("CLIENTE", "PORTAL"),
        help="Concilia dois ZIPs de NF-e. --csv gera quatro arquivos por grupo.",
    )
    return parser


def run_cli(args: argparse.Namespace) -> int:
    """Executa a lógica principal da CLI."""
    if args.nfse:
        return run_nfse_cli(args)
    if args.comparar_zips:
        return run_zip_comparison(args)
    # Se o usuário solicitou apenas a visualização de um CSV existente
    if args.visualizar_csv:
        return view_csv(args.visualizar_csv, limit=args.limite, search=args.busca or "")

    # 1. Definir caminhos alvo
    targets = []
    if args.target_path:
        targets.append(args.target_path)
    if args.caminho:
        targets.extend(args.caminho)
    if not targets:
        # Se nada for informado, pergunta se estiver em terminal ou usa diretório atual
        if sys.stdin.isatty():
            try:
                entered = input("Informe o caminho da pasta, XML ou ZIP [Enter para pasta atual '.']: ").strip()
                targets = [entered if entered else "."]
            except (EOFError, KeyboardInterrupt):
                print("\nOperação cancelada.")
                return 0
        else:
            targets = ["."]

    recursive = not args.no_recursive
    xml_files = find_xml_files(targets, recursive=recursive)

    if not xml_files:
        print("Erro: Nenhum arquivo XML encontrado e nenhum ZIP localizado nos caminhos informados.", file=sys.stderr)
        return 1

    file_types = "XML/ZIP" if any(path.suffix.casefold() == ".zip" for path in xml_files) else "XML"
    print(f"\nLocalizado(s) {len(xml_files)} arquivo(s) {file_types} para processamento.")

    # 2. Confirmar tipo de operação (Interestadual, Estadual ou Ambos)
    operacao = args.operacao
    if not operacao:
        if sys.stdin.isatty():
            operacao = confirm_operation(default="ambos")
        else:
            operacao = "ambos"
            print(f"Modo não interativo: assumindo operação '{operacao}'.")

    print(f"\n-> Operação selecionada: {operacao.upper()}")

    # 3. Carregar base fiscal
    catalog = {}
    fiscal_path = args.base_fiscal
    if fiscal_path and fiscal_path.exists():
        try:
            catalog = load_fiscal_catalog(fiscal_path)
            print(f"-> Base fiscal carregada: {len(catalog)} NCM(s) cadastrado(s) em '{fiscal_path.name}'.")
        except (OSError, ValueError) as exc:
            print(f"Aviso ao ler base fiscal: {exc}", file=sys.stderr)
    else:
        print("-> Nenhuma base fiscal ativa encontrada. A análise de NCM prosseguirá sem status cadastral.")

    # 4. Processar XMLs (sem limite de quantidade)
    print("Iniciando leitura e processamento dos XMLs...")
    nfes, issues = parse_xml_files(xml_files, show_progress=not args.quiet)

    if issues:
        print("\nErros encontrados:")
        for issue in issues[:10]:
            print(f" - {issue.filename}: {issue.message}")
        if len(issues) > 10:
            print(f" ... e mais {len(issues) - 10} arquivo(s) com erro.")
    if not nfes:
        print("\nErro: Nenhuma NF-e válida pôde ser lida.", file=sys.stderr)
        return 1

    # 5. Comparação fiscal com a base
    # Selecionar prefixos conforme a operação escolhida
    if operacao == "interestadual":
        cfop_prefixes = ANALYZED_CFOP_PREFIXES
    elif operacao == "estadual":
        cfop_prefixes = ESTADUAL_CFOP_PREFIXES
    else:
        cfop_prefixes = ANALYZED_CFOP_PREFIXES + ESTADUAL_CFOP_PREFIXES

    items, summary = compare_nfes(nfes, catalog, cfop_prefixes=cfop_prefixes)

    # 6. Listagem de produtos filtrada
    products = product_rows(
        nfes,
        operacao=operacao,
        cfop=args.filtro_cfop or "",
        cst=args.filtro_cst or "",
        status=args.filtro_status or "",
        query=args.busca or "",
    )

    if args.filtro_ncm:
        clean_ncm = "".join(c for c in args.filtro_ncm if c.isdigit())
        products = [p for p in products if clean_ncm in p.get("ncm", "")]

    # 7. Exibição da tabela de produtos
    if not args.quiet:
        print_products_table(products, limit=args.limite)

    # 8. Exibição dos totais consolidados
    print_totals_summary(products, nfes_count=len(nfes), issues_count=len(issues))

    # 9. Exportações (se especificadas via argumentos)
    excel_path = args.excel
    csv_path = args.csv
    json_path = args.json

    # Se em terminal interativo e nenhuma flag foi passada, oferece opção de exportar
    if sys.stdin.isatty() and not (excel_path or csv_path or json_path) and products:
        try:
            exp_prompt = "Deseja exportar a lista de produtos? [1] Excel (.xlsx) [2] CSV (.csv) [3] Ambos [N] Não: "
            exp_choice = input(exp_prompt).strip().casefold()
            if exp_choice in {"1", "excel"}:
                excel_path = Path("relatorio_produtos.xlsx")
            elif exp_choice in {"2", "csv"}:
                csv_path = Path("produtos.csv")
            elif exp_choice in {"3", "ambos", "ambas"}:
                excel_path = Path("relatorio_produtos.xlsx")
                csv_path = Path("produtos.csv")
        except (EOFError, KeyboardInterrupt):
            pass

    if excel_path or csv_path or json_path:
        export_results(
            nfes,
            products,
            issues,
            excel_path=excel_path,
            csv_path=csv_path,
            json_path=json_path,
        )

        if csv_path and csv_path.exists():
            if args.visualizar:
                view_csv(csv_path, limit=args.limite, search=args.busca or "")
            elif sys.stdin.isatty():
                try:
                    view_prompt = "\nDeseja visualizar o CSV gerado agora no terminal? [S/n]: "
                    view_ans = input(view_prompt).strip().casefold()
                    if view_ans in {"", "s", "sim", "y", "yes"}:
                        view_csv(csv_path, limit=args.limite, search=args.busca or "")
                except (EOFError, KeyboardInterrupt):
                    pass

    return 0


def run_nfse_cli(args: argparse.Namespace) -> int:
    try:
        if args.input is None:
            raise ValueError('Informe --input/-i no modo --nfse.')
        if not args.input.exists():
            raise ValueError(f'Caminho de entrada não encontrado: {args.input}')
        paths = find_xml_files([args.input], recursive=not args.no_recursive)
        if not paths:
            raise ValueError('Nenhum arquivo XML/ZIP localizado na entrada NFS-e.')
        excel_path = args.output_excel or args.excel
        json_path = args.output_json or args.json
        csv_prefix = args.output_csv or args.csv
        csv_paths = [csv_prefix.with_name(f'{csv_prefix.stem}_{group}.csv') for group in ('notas', 'apontamentos')] if csv_prefix else []
        outputs = [p for p in (excel_path, json_path, *csv_paths) if p]
        resolved = [p.resolve() for p in outputs]
        input_paths = {p.resolve() for p in paths}
        if len(set(resolved)) != len(resolved) or input_paths.intersection(resolved):
            raise ValueError('Saídas devem ser distintas e não podem substituir arquivos de entrada.')
        state = process_nfse_batch(path_inputs(paths))
        print(f'NFS-e: {state.total_processed} XML(s), {state.total_valid} documento(s), '
              f'{len(state.events)} evento(s), {len(state.orphan_events)} órfão(s), {len(state.issues)} ocorrência(s).')
        def currency(value):
            return 'R$ ' + f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        print(f'Bruto vigente: {currency(state.total_gross_amount)} | ISS: {currency(state.total_iss_amount)} | '
              f'ISS retido: {currency(state.total_iss_withheld)} | Federais: {currency(state.total_federal_withheld)} | '
              f'Líquido auditado: {currency(state.total_net_amount)}')
        print('Totais financeiros: somente NFS-e autorizadas vigentes.')
        ranks = {'INFO': 0, 'WARNING': 1, 'HIGH': 2, 'CRITICAL': 3}
        if not args.quiet:
            for document in state.documents:
                print(f'{document.kind.value} {document.identity.nfse_number or document.identity.dps_number} | '
                      f'{document.status.value} | {document.provider.name}')
                for finding in document.findings:
                    if ranks[finding.severity.value] >= ranks[args.min_severity]:
                        print(f'  [{finding.severity.value}] {finding.code}: {finding.title}')
                        print(f'    Reportado: {finding.reported} | Esperado: {finding.expected} | Base: {finding.legal_basis}')
        for issue in state.issues:
            print(f"Aviso {issue['filename']}: {issue['message']}", file=sys.stderr)
        exports = []
        if excel_path:
            exports.append((excel_path, generate_nfse_excel_report(state).getvalue()))
        if json_path:
            exports.append((json_path, json_download(build_nfse_json_payload(state))))
        if csv_prefix:
            exports.extend(zip(csv_paths, [generate_nfse_csv_notes(state).encode('utf-8'),
                                           generate_nfse_csv_findings(state).encode('utf-8')]))
        for path, content in exports:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if not args.quiet:
                print(f'Relatório salvo: {path}')
        if any(f.severity == FindingSeverity.CRITICAL for d in state.documents for f in d.findings):
            return 2
        if not state.documents and not state.events:
            return 1
        if any('ignorado' not in i['message'].casefold() for i in state.issues):
            return 1
        return 0
    except (OSError, ValueError) as exc:
        print(f'Erro na auditoria NFS-e: {exc}', file=sys.stderr)
        return 1


def run_zip_comparison(args: argparse.Namespace) -> int:
    cliente, portal = args.comparar_zips
    try:
        if any(path.suffix.casefold() != ".zip" for path in (cliente, portal)):
            raise ValueError("Os dois arquivos devem ter extensão .zip.")
        outputs = [path for path in (args.excel, args.json) if path]
        csv_groups = ("apenas-cliente", "apenas-portal", "em-ambos", "divergencias")
        csv_paths = [args.csv.with_name(f"{args.csv.stem}_{group}.csv") for group in csv_groups] if args.csv else []
        outputs.extend(csv_paths)
        resolved = [path.resolve() for path in outputs]
        if len(set(resolved)) != len(resolved) or any(path in {cliente.resolve(), portal.resolve()} for path in resolved):
            raise ValueError("As saídas devem ter caminhos distintos e não podem substituir os ZIPs de entrada.")
        with cliente.open("rb") as cs, portal.open("rb") as ps:
            result = compare_nfe_zips(cs, ps, nome_cliente=cliente.name, nome_portal=portal.name)
        summary = result.resumo
        print("=" * 62)
        print("CONCILIAÇÃO FISCAL DE NOTAS: CLIENTE × PORTAL")
        print("Empresa validada — CNPJ(s) em todas as NF-es: " + ", ".join(result.cnpjs_empresa))
        print("=" * 62)
        for label, count, value in (
            ("Total no arquivo do Cliente", summary.total_cliente, summary.valor_total_cliente),
            ("Total no arquivo do Portal", summary.total_portal, summary.valor_total_portal),
            ("Presentes em ambos (valores Cliente)", summary.total_comuns, summary.valor_comuns),
            ("Apenas no Cliente (Faltando no Portal)", summary.total_apenas_cliente, summary.valor_apenas_cliente),
            ("Apenas no Portal (Faltando no Cliente)", summary.total_apenas_portal, summary.valor_apenas_portal),
        ):
            print(f"{label}: {count} notas ({format_currency_br(value)})")
        print(f"Divergências de valores (vNF, ICMS ou ST): {summary.total_divergencias} notas")
        print("=" * 62)
        for label, issues in (("Cliente", result.issues_cliente), ("Portal", result.issues_portal)):
            for issue in issues:
                print(f"Aviso [{label}] {issue.filename}: {issue.message}", file=sys.stderr)
        if args.excel:
            args.excel.write_bytes(zip_comparison_excel(result))
        if args.json:
            args.json.write_bytes(json_download(zip_comparison_payload(result)))
        if args.csv:
            notes = (result.apenas_cliente, result.apenas_portal, result.em_ambos)
            for path, group_notes in zip(csv_paths, notes):
                path.write_bytes(zip_comparison_csv(group_notes))
            csv_paths[-1].write_bytes(zip_comparison_divergences_csv(result.divergencias))
        return 0
    except (OSError, ValueError) as exc:
        print(f"Erro na conciliação: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    """Ponto de entrada da CLI."""
    parser = build_parser()
    args = parser.parse_args()
    code = run_cli(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
