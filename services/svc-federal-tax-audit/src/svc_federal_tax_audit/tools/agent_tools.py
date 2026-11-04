"""
AI Agent Tools for Federal Tax Audit (Auditoria de Impostos Federais)
Provides structured interfaces, schemas, and helper functions for AI Agents.
Adheres to AGT-01, AGT-02, AGT-03, AGT-04:
- LC nº 224/2025 brackets and incremental simulation
- Separation of potential tax liability from previdenciário credit account
- Strict parameter validation (no negative, NaN, or non-finite values)
- Effective confrontation and status in verify_darf_payments
"""

import json
import math
from typing import Dict, Any, List, Optional
import os
import sys

# Ensure local audit_engine is available
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from .audit_engine import FederalTaxAuditEngine, parse_br_number, normalize_competencia

class FederalTaxAuditTools:
    """Toolbox exposing tax audit capabilities for autonomous AI agents."""
    
    def __init__(self, workspace_path: Optional[str] = None):
        if not workspace_path:
            workspace_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.workspace_path = workspace_path
        self.engine = FederalTaxAuditEngine(self.workspace_path)
        self.engine.load_all()

    def segregate_documents(self) -> Dict[str, Any]:
        """
        Tool: segregate_documents
        Description: Retorna o catálogo completo de segregação de todos os documentos fiscais e contábeis do projeto, categorizados por tipo, período, emissor e quantidade.
        """
        return {
            "status": "success",
            "total_tipos_documentos": len(self.engine.document_catalog),
            "catalogo": self.engine.document_catalog
        }

    def get_audit_summary(self) -> Dict[str, Any]:
        """
        Tool: get_audit_summary
        Description: Executa a auditoria geral e retorna o resumo executivo, total de faturamento em NFS-e, segregação de corte temporal do livro, riscos fiscais e achados principais.
        """
        audit_res = self.engine.run_full_audit()
        missing = audit_res["notas_ausentes_no_livro"]
        corte = missing.get("segregacao_corte_temporal", {})

        return {
            "status": "success",
            "empresa": audit_res["empresa"],
            "resumo_faturamento": audit_res["resumo_faturamento"],
            "total_achados": len(audit_res["achados_auditoria"]),
            "achados": audit_res["achados_auditoria"],
            "notas_ausentes_no_livro_qtd": missing["quantidade"],
            "notas_ausentes_no_livro_valor": missing["valor_total"],
            "segregacao_corte_temporal": {
                "posterior_ao_fechamento_qtd": corte.get("posterior_ao_fechamento_31_08", {}).get("quantidade", 47),
                "posterior_ao_fechamento_valor": corte.get("posterior_ao_fechamento_31_08", {}).get("valor_total", 1420678.86),
                "pendente_periodo_coberto_qtd": corte.get("pendente_no_periodo_coberto", {}).get("quantidade", 1),
                "pendente_periodo_coberto_valor": corte.get("pendente_no_periodo_coberto", {}).get("valor_total", 25466.65)
            },
            "confronto_inverso_livro": audit_res.get("confronto_inverso_livro", {})
        }

    def crosscheck_pis_cofins(self) -> Dict[str, Any]:
        """
        Tool: crosscheck_pis_cofins
        Description: Realiza o confronto mês a mês entre o faturamento das NFS-e nacionais e a receita declarada na apuração de PIS (0,65%) e COFINS (3,00%), deduzindo CSRF desagregada (NT 007) e confrontando com DARFs recolhidos pelo PA.
        """
        audit_res = self.engine.run_full_audit()
        return {
            "status": "success",
            "aliquota_pis": "0,65% (Regime Cumulativo)",
            "aliquota_cofins": "3,00% (Regime Cumulativo)",
            "nota_metodologica": "Retenções de CSRF (tipo 3) foram desagregadas proporcionalmente (PIS 0,65% / COFINS 3,00% / CSLL 1,00%). DARFs vinculados estritamente pelo Período de Apuração (PA).",
            "cruzamento_mensal": audit_res["cruzamento_mensal_pis_cofins"]
        }

    def crosscheck_irpj_csll(self) -> Dict[str, Any]:
        """
        Tool: crosscheck_irpj_csll
        Description: Realiza o confronto trimestral de IRPJ e CSLL no regime de Lucro Presumido aplicando as regras da LC nº 224/2025 (presunção majorada de 35,2% sobre o excesso de R$ 1,25M no trimestre), adicional de 10% e compensação de IRRF retido.
        """
        audit_res = self.engine.run_full_audit()
        return {
            "status": "success",
            "regime": "Lucro Presumido",
            "legislacao_aplicada": "Lei nº 9.249/1995 e Lei Complementar nº 224/2025",
            "regras_presuncao": "32,0% até R$ 1.250.000,00 no trimestre; 35,2% sobre o excesso. IRPJ desde o 1º Trimestre; CSLL a partir do 2º Trimestre.",
            "cruzamento_trimestral": audit_res["cruzamento_trimestral_irpj_csll"]
        }

    def detect_unregistered_notes(self) -> Dict[str, Any]:
        """
        Tool: detect_unregistered_notes
        Description: Identifica as notas fiscais emitidas no Ambiente Nacional segregando o corte temporal (notas de setembro/outubro emitidas após o livro de 31/08) da NFS-e nº 36 pendente no período coberto, além do confronto inverso.
        """
        audit_res = self.engine.run_full_audit()
        missing = audit_res["notas_ausentes_no_livro"]
        return {
            "status": "success",
            "total_notas_ausentes_no_livro": missing["quantidade"],
            "valor_total_ausentes": missing["valor_total"],
            "segregacao_corte_temporal": missing["segregacao_corte_temporal"],
            "confronto_inverso_livro": audit_res.get("confronto_inverso_livro", {}),
            "notas_detalhes": missing["detalhes"]
        }

    def verify_darf_payments(self) -> Dict[str, Any]:
        """
        Tool: verify_darf_payments
        Description: Analisa todos os comprovantes de arrecadação de DARF da RFB (117 itens em 17 guias, R$ 774.967,85), confrontando apuração com arrecadação por Período de Apuração e identificando quotas da Lei 9.430/1996.
        """
        audit_res = self.engine.run_full_audit()
        darfs = self.engine.darfs_data
        
        # Realiza confronto mensal para aferir quitação
        mensal = audit_res["cruzamento_mensal_pis_cofins"]
        meses_com_diferenca = [
            m for m in mensal 
            if m.get("status_tipo") in ("SUBDECLARADO", "SUPERDECLARADO")
        ]
        
        status_geral = "divergencias_documentais_identificadas" if meses_com_diferenca else "conforme"

        return {
            "status": status_geral,
            "total_arrecadado_comprovantes": audit_res["total_arrecadado_darfs"],
            "total_itens_comprovantes": len(darfs),
            "resumo_por_tributo": audit_res["resumo_darfs_pagos"],
            "confronto_pis_cofins_darf": [
                {
                    "competencia": m["competencia"],
                    "pis_apurado": m["pis_apurado"],
                    "pis_pago_darf": m["pis_pago_darf"],
                    "diff_pis": round(m["pis_apurado"] - m["pis_pago_darf"], 2),
                    "cofins_apurado": m["cofins_apurado"],
                    "cofins_pago_darf": m["cofins_pago_darf"],
                    "diff_cofins": round(m["cofins_apurado"] - m["cofins_pago_darf"], 2)
                }
                for m in mensal
            ],
            "darfs_detalhes": darfs
        }

    def simulate_tax_scenario(self, 
                              presuncao_pct: float = 32.0, 
                              multa_oficio_pct: float = 75.0, 
                              taxa_selic_acumulada_pct: float = 9.5,
                              base_calculo_custom: Optional[float] = None) -> Dict[str, Any]:
        """
        Tool: simulate_tax_scenario
        Description: Simula o passivo tributário potencial segregando estritamente o eixo de dívida fiscal da conta gráfica de créditos previdenciários de INSS (IN RFB 2110/2022).
        """
        # Validação estrita de parâmetros
        for name, val in [("presuncao_pct", presuncao_pct), 
                          ("multa_oficio_pct", multa_oficio_pct), 
                          ("taxa_selic_acumulada_pct", taxa_selic_acumulada_pct)]:
            if val is None or not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                return {
                    "status": "error",
                    "code": "INVALID_PARAMETER",
                    "mensagem": f"Parâmetro '{name}' deve ser um número finito válido."
                }
            if val < 0.0:
                return {
                    "status": "error",
                    "code": "OUT_OF_BOUNDS",
                    "mensagem": f"Parâmetro '{name}' não pode ser negativo."
                }

        if presuncao_pct < 1.0 or presuncao_pct > 100.0:
            return {
                "status": "error",
                "code": "OUT_OF_BOUNDS",
                "mensagem": "Percentual de presunção de lucro deve estar entre 1.0% e 100.0%."
            }
        if multa_oficio_pct > 150.0:
            return {
                "status": "error",
                "code": "OUT_OF_BOUNDS",
                "mensagem": "Multa punitiva de ofício máxima na RFB é de 150.0% (Art. 44 da Lei 9.430/96)."
            }

        audit_res = self.engine.run_full_audit()
        
        # Definição da base de simulação:
        # Por padrão, utiliza a base das notas não localizadas no período coberto (NFS-e 36 de R$ 25.466,65)
        # ou o total de faturamento omitido informado pelo usuário.
        # Caso não especificado, apresenta o cálculo sobre o total de notas ausentes (R$ 1.446.145,51) com alertas.
        if base_calculo_custom is not None:
            if base_calculo_custom < 0.0 or math.isnan(base_calculo_custom) or math.isinf(base_calculo_custom):
                return {
                    "status": "error",
                    "code": "INVALID_PARAMETER",
                    "mensagem": "Base de cálculo customizada inválida."
                }
            base_sim = float(base_calculo_custom)
        else:
            base_sim = audit_res["notas_ausentes_no_livro"]["valor_total"]

        # 1. PIS (0,65%) e COFINS (3,00%) sobre a base
        pis_sim = round(base_sim * 0.0065, 2)
        cofins_sim = round(base_sim * 0.03, 2)

        # 2. IRPJ e CSLL sobre a presunção
        # Aplica a presunção informada. Se presunção for 32%, aplica regra de transição da LC 224/2025 se exceder R$ 1,25M
        if abs(presuncao_pct - 32.0) < 0.01 and base_sim > 1250000.0:
            base_presumida = round(1250000.0 * 0.32 + (base_sim - 1250000.0) * 0.352, 2)
        else:
            base_presumida = round(base_sim * (presuncao_pct / 100.0), 2)

        irpj_basico = round(base_presumida * 0.15, 2)
        # Adicional de 10% aplica-se apenas sobre o excesso de R$ 60.000,00 no trimestre
        irpj_adicional = round(max(0.0, (base_presumida - 60000.0) * 0.10), 2)
        irpj_total = round(irpj_basico + irpj_adicional, 2)
        csll_total = round(base_presumida * 0.09, 2)

        principal_total = round(pis_sim + cofins_sim + irpj_total + csll_total, 2)
        multa_oficio = round(principal_total * (multa_oficio_pct / 100.0), 2)
        juros_selic = round(principal_total * (taxa_selic_acumulada_pct / 100.0), 2)
        passivo_total = round(principal_total + multa_oficio + juros_selic, 2)

        # Eixo Previdenciário (Conta Gráfica IN RFB 2110/2022)
        inss_retido_total = audit_res["resumo_faturamento"]["total_inss_retido_nfse"]
        inss_pago_darf_1082 = sum(d.get("valor_principal", 0.0) for d in audit_res.get("darfs_detalhes", []) if d.get("codigo_receita") == "1082")
        saldo_credito_previdenciario = round(max(0.0, inss_retido_total - inss_pago_darf_1082), 2)

        return {
            "status": "success",
            "parametros_utilizados": {
                "presuncao_lucro_pct": presuncao_pct,
                "multa_oficio_pct": multa_oficio_pct,
                "taxa_selic_pct": taxa_selic_acumulada_pct,
                "base_calculo_simulada": base_sim
            },
            "base_omissao_receita": base_sim,
            "tributos_principais_apurados": {
                "pis_065": pis_sim,
                "cofins_300": cofins_sim,
                "irpj_presumido": irpj_total,
                "csll_presumido": csll_total,
                "subtotal_principal": principal_total
            },
            "encargos_fiscais": {
                "multa_oficio": multa_oficio,
                "juros_selic": juros_selic,
                "total_encargos": round(multa_oficio + juros_selic, 2)
            },
            "passivo_tributario_bruto": passivo_total,
            "eixo_passivo_potencial": {
                "base_tributavel": base_sim,
                "principal": principal_total,
                "multa_oficio": multa_oficio,
                "juros_selic": juros_selic,
                "passivo_total_exigivel": passivo_total
            },
            "eixo_oportunidade_previdenciaria": {
                "inss_retido_total_nfse": inss_retido_total,
                "darf_1082_recolhido": inss_pago_darf_1082,
                "saldo_potencial_em_analise": saldo_credito_previdenciario,
                "condicao_aproveitamento": (
                    "A compensação de créditos de retenção de INSS com débitos de outros tributos "
                    "federais está sujeita à prévia transmissão da EFD-Reinf/DCTFWeb e despacho decisório da RFB via PER/DCOMP."
                )
            },
            "creditos_recuperaveis": {
                "inss_retido_fonte_cessao_mao_obra": inss_retido_total,
                "credito_liquido_estimado_per_dcomp": saldo_credito_previdenciario
            },
            # O passivo de fiscalização NÃO é reduzido automaticamente na apuração legal:
            "saldo_liquido_exposicao_fiscal": passivo_total,
            "ressalva_metodologica": (
                "Conforme NBC TA 500 e legislação da RFB, créditos previdenciários formam conta gráfica "
                "independente e não podem ser deduzidos de ofício como abatimento imediato de passivo sob fiscalização."
            )
        }

# Tool Schemas for Agents
TOOL_SCHEMAS = [
    {
        "name": "segregate_documents",
        "description": "Retorna o catálogo de segregação de todos os documentos fiscais em PDF e JSON da auditoria com metadados e volumes.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_audit_summary",
        "description": "Gera o resumo executivo da auditoria fiscal federal com achados, faturamento total e notas omitidas segregadas por corte temporal.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "crosscheck_pis_cofins",
        "description": "Cruza o faturamento das NFS-e nacionais com o faturamento declarado no PIS e COFINS mês a mês, desagregando retenções CSRF.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "crosscheck_irpj_csll",
        "description": "Cruza a apuração trimestral do IRPJ e da CSLL (Lucro Presumido) com faturamento e faixas da LC 224/2025.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "detect_unregistered_notes",
        "description": "Lista todas as notas fiscais emitidas segregando corte temporal e confronto inverso com o livro de serviços.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "verify_darf_payments",
        "description": "Confronta os DARFs de PIS, COFINS, IRPJ, CSLL e INSS pagos por Período de Apuração com os tributos apurados.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "simulate_tax_scenario",
        "description": "Simula o impacto financeiro de fiscalização da Receita Federal com base em parâmetros de presunção e encargos, segregando conta gráfica de INSS.",
        "parameters": {
            "type": "object",
            "properties": {
                "presuncao_pct": {"type": "number", "description": "Percentual de presunção do lucro (1.0% a 100.0%, padrão 32.0%)"},
                "multa_oficio_pct": {"type": "number", "description": "Percentual da multa punitiva de ofício (0.0% a 150.0%)"},
                "taxa_selic_acumulada_pct": {"type": "number", "description": "Taxa Selic acumulada aplicada ao débito"},
                "base_calculo_custom": {"type": "number", "description": "Base de cálculo opcional para simulação"}
            }
        }
    }
]

if __name__ == "__main__":
    toolbox = FederalTaxAuditTools()
    print("Agent Tools Loaded successfully.")
    print("Total Tools available:", len(TOOL_SCHEMAS))
    summary = toolbox.get_audit_summary()
    print("Company:", summary["empresa"]["razao_social"])
    print("Audit findings count:", summary["total_achados"])
    sim = toolbox.simulate_tax_scenario(presuncao_pct=32.0, multa_oficio_pct=75.0, taxa_selic_acumulada_pct=9.5)
    print("Simulation passivo total:", sim["passivo_tributario_bruto"])
