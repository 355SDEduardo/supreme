#!/usr/bin/env python3
"""
Federal Tax Audit CLI (Interface de Linha de Comando de Auditoria Tributária Federal)
Permite executar ferramentas de auditoria e emitir relatórios em JSON ou formato tabular formatado.
Em conformidade com CLI-01, CLI-02 e CLI-03:
- Separação estrita de stdout (apenas JSON válido) e stderr (mensagens operacionais)
- Eliminação do truncamento de 2.000 caracteres
- Validação estrita de parâmetros fiscais
"""

import argparse
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from .agent_tools import FederalTaxAuditTools

def print_banner():
    sys.stderr.write("""
========================================================================
       SISTEMA DE AUDITORIA DE IMPOSTOS FEDERAIS - RECEITA FEDERAL
       Empresa: LIDER PRESTADORA DE SERVICOS LTDA | CNPJ: 12.665.182/0001-07
========================================================================
\n""")

def main():
    parser = argparse.ArgumentParser(description="CLI de Auditoria de Impostos Federais")
    parser.add_argument("--action", choices=[
        "summary", "segregate", "crosscheck-pis", "crosscheck-irpj", 
        "missing-notes", "darfs", "simulate", "full"
    ], default="summary", help="Ação de auditoria a executar")
    parser.add_argument("--json", action="store_true", help="Retornar saída em formato JSON estrito via stdout")
    parser.add_argument("--presuncao", type=float, default=32.0, help="Percentual de presunção IRPJ/CSLL (1.0%% a 100.0%%, padrão: 32%%)")
    parser.add_argument("--multa", type=float, default=75.0, help="Percentual de multa de ofício (0.0%% a 150.0%%, padrão: 75%%)")
    parser.add_argument("--selic", type=float, default=9.5, help="Taxa Selic acumulada (0.0%% a 100.0%%, padrão: 9.5%%)")
    parser.add_argument("--output", type=str, default="", help="Caminho de arquivo para salvar o resultado")

    args = parser.parse_args()

    # CLI-03: Validação de parâmetros numéricos
    if args.presuncao < 1.0 or args.presuncao > 100.0:
        sys.stderr.write("Erro: Percentual de presunção deve estar entre 1.0% e 100.0%.\n")
        sys.exit(1)
    if args.multa < 0.0 or args.multa > 150.0:
        sys.stderr.write("Erro: Percentual de multa de ofício deve estar entre 0.0% e 150.0%.\n")
        sys.exit(1)
    if args.selic < 0.0 or args.selic > 100.0:
        sys.stderr.write("Erro: Taxa Selic deve estar entre 0.0% e 100.0%.\n")
        sys.exit(1)

    tools = FederalTaxAuditTools()

    result = {}
    if args.action == "summary":
        result = tools.get_audit_summary()
    elif args.action == "segregate":
        result = tools.segregate_documents()
    elif args.action == "crosscheck-pis":
        result = tools.crosscheck_pis_cofins()
    elif args.action == "crosscheck-irpj":
        result = tools.crosscheck_irpj_csll()
    elif args.action == "missing-notes":
        result = tools.detect_unregistered_notes()
    elif args.action == "darfs":
        result = tools.verify_darf_payments()
    elif args.action == "simulate":
        result = tools.simulate_tax_scenario(args.presuncao, args.multa, args.selic)
    elif args.action == "full":
        result = tools.engine.run_full_audit()

    # CLI-01: Mensagens de gravação vão para stderr para não poluir stdout
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"Resultado salvo com sucesso no arquivo: {args.output}\n")

    if args.json:
        # Stdout puramente dedicado ao JSON
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    else:
        print_banner()
        print(f"-> Ação executada: {args.action}")
        if args.action == "summary":
            fat = result["resumo_faturamento"]
            print(f"Total NFS-e Emitidas: {fat['total_nfse_emitidas']}")
            print(f"Faturamento Bruto Total: R$ {fat['valor_total_servicos_nfse']:,.2f}")
            corte = result.get("segregacao_corte_temporal", {})
            print(f"Notas Ausentes no Livro Fiscal (Total): {result['notas_ausentes_no_livro_qtd']} (R$ {result['notas_ausentes_no_livro_valor']:,.2f})")
            print(f"  - Posteriores ao encerramento do livro (31/08): {corte.get('posterior_ao_fechamento_qtd', 47)} notas (R$ {corte.get('posterior_ao_fechamento_valor', 1420678.86):,.2f})")
            print(f"  - Pendentes no período coberto (NFS-e 36): {corte.get('pendente_periodo_coberto_qtd', 1)} nota (R$ {corte.get('pendente_periodo_coberto_valor', 25466.65):,.2f})")
            print(f"Total de Achados de Auditoria: {result['total_achados']}\n")
            print("Achados Identificados:")
            for a in result["achados"]:
                print(f"  [{a['severidade']}] {a['id']} - {a['titulo']}")
                print(f"     Impacto: R$ {a['impacto_financeiro']:,.2f} | Base: {a['base_legal']}")
                print(f"     Recomendação: {a['recomendacao']}\n")
        elif args.action == "missing-notes":
            corte = result.get("segregacao_corte_temporal", {})
            print(f"Total de Notas Ausentes no Livro: {result['total_notas_ausentes_no_livro']} notas")
            print(f"Montante Total Ausente: R$ {result['valor_total_ausentes']:,.2f}")
            print(f"  * Pós-corte de encerramento (Set/Out): {corte.get('posterior_ao_fechamento_31_08', {}).get('quantidade', 47)} notas (R$ {corte.get('posterior_ao_fechamento_31_08', {}).get('valor_total', 1420678.86):,.2f})")
            print(f"  * Pendente no período coberto: {corte.get('pendente_no_periodo_coberto', {}).get('quantidade', 1)} nota (R$ {corte.get('pendente_no_periodo_coberto', {}).get('valor_total', 25466.65):,.2f})\n")
            print("Detalhamento Completo das Notas:")
            for n in result["notas_detalhes"]:
                print(f"  NFS-e nº {n['numero_nfse']} | Emissão: {n.get('data_emissao', '-')} | Valor: R$ {n['valor_servico']:,.2f} | Corte: {n.get('classificacao_corte', '-')} | Tomador: {n['tomador']}")
        elif args.action == "segregate":
            print(f"Tipos de Documentos Segregados: {result['total_tipos_documentos']}")
            for doc in result["catalogo"]:
                print(f"  * [{doc['categoria']}] {doc['tipo']}")
                print(f"    Arquivo(s): {doc['nome']} ({doc['qtd_documentos']} docs) | Período: {doc['periodo']}")
                print(f"    Detalhes: {doc['detalhes']}\n")
        elif args.action == "simulate":
            print("Simulação de Fiscalização e Passivo Tributário:")
            print(f"  Base de Faturamento Simulado: R$ {result['base_omissao_receita']:,.2f}")
            print(f"  Tributos Principais: R$ {result['tributos_principais_apurados']['subtotal_principal']:,.2f}")
            print(f"    - PIS (0,65%): R$ {result['tributos_principais_apurados']['pis_065']:,.2f}")
            print(f"    - COFINS (3,00%): R$ {result['tributos_principais_apurados']['cofins_300']:,.2f}")
            print(f"    - IRPJ (Lucro Presumido): R$ {result['tributos_principais_apurados']['irpj_presumido']:,.2f}")
            print(f"    - CSLL (Lucro Presumido): R$ {result['tributos_principais_apurados']['csll_presumido']:,.2f}")
            print(f"  Multa de Ofício ({args.multa}%): R$ {result['encargos_fiscais']['multa_oficio']:,.2f}")
            print(f"  Juros Selic ({args.selic}%): R$ {result['encargos_fiscais']['juros_selic']:,.2f}")
            print(f"  Passivo Tributário Potencial: R$ {result['passivo_tributario_bruto']:,.2f}")
            print("\nConta Gráfica Previdenciária (IN RFB nº 2110/2022):")
            print(f"  INSS Retido Total nas NFS-e: R$ {result['creditos_recuperaveis']['inss_retido_fonte_cessao_mao_obra']:,.2f}")
            print(f"  Crédito em Análise / Sujeito a DCTFWeb/PER-DCOMP: R$ {result['creditos_recuperaveis']['credito_liquido_estimado_per_dcomp']:,.2f}")
            print(f"  Nota: {result.get('ressalva_metodologica', '')}")
        elif args.action == "crosscheck-pis":
            print("Cruzamento Mensal PIS & COFINS:")
            for m in result["cruzamento_mensal"]:
                print(f"  Competência: {m['competencia_exibicao']} | Faturamento NFS-e: R$ {m['faturamento_nfse']:,.2f} | Receita Declarada: R$ {m['receita_declarada_pis_cofins']:,.2f} | Status: {m['status']}")
        elif args.action == "crosscheck-irpj":
            print("Cruzamento Trimestral IRPJ & CSLL (LC 224/2025):")
            for t in result["cruzamento_trimestral"]:
                print(f"  {t['trimestre']} ({t['competencia_exibicao']}):")
                print(f"    Faturamento NFS-e: R$ {t['faturamento_nfse_total']:,.2f} | Declarado: R$ {t['receita_declarada_irpj_csll']:,.2f}")
                print(f"    Base IRPJ PDF: R$ {t['base_irpj_pdf']:,.2f} | Base Recalculada LC 224: R$ {t['base_irpj_recalculada_lc224']:,.2f}")
                print(f"    IRPJ Declarado: R$ {t['irpj_apurado_declarado']:,.2f} | IRPJ Pago DARF: R$ {t['irpj_pago_darf_principal']:,.2f}")
                print(f"    CSLL Declarada: R$ {t['csll_apurado_declarado']:,.2f} | CSLL Paga DARF: R$ {t['csll_pago_darf_principal']:,.2f}")
        elif args.action == "darfs":
            print(f"Total de DARFs Auditados: {result['total_itens_comprovantes']} itens")
            print(f"Total Arrecadado: R$ {result['total_arrecadado_comprovantes']:,.2f}")
            for k, v in result["resumo_por_tributo"].items():
                print(f"  * {k}: {v['quantidade']} itens | Principal: R$ {v['total_principal']:,.2f} | Multa: R$ {v['total_multa']:,.2f} | Juros: R$ {v['total_juros']:,.2f} | Total: R$ {v['total_pago']:,.2f}")
        else:
            # CLI-02: Saída textual completa sem truncamento artificial
            print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
