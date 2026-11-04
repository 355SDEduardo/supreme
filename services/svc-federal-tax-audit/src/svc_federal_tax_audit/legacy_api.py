"""
FastAPI Server for Federal Tax Audit System
(Servidor Web e API de Auditoria de Impostos Federais)
Conforme API-01, API-02, API-03, API-04 e API-05:
- Snapshot atômico de dados com endpoint POST /api/reload
- Validação estrita via Pydantic para simulação e parâmetros
- Relatório técnico preliminar dinâmico e moderado com limitações de escopo
- Enriquecimento analítico das NFS-e com situação documental
- CORS restrito e binding local seguro
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, HTTPException, Body, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Local tools setup
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(WORKSPACE_DIR, "tools"))
from audit_engine import FederalTaxAuditEngine, format_competencia_display
from agent_tools import FederalTaxAuditTools

app = FastAPI(
    title="Sistema de Auditoria de Impostos Federais",
    description="API de Auditoria Fiscal e Tributária Federal - Receita Federal do Brasil",
    version="2.1.0"
)

# API-05: Restrição de CORS para ambiente local de auditoria
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# API-03: Gestão de Snapshot Atômico
class AuditSnapshot:
    def __init__(self, workspace_path: str):
        self.version_id = str(uuid.uuid4())
        self.timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.engine = FederalTaxAuditEngine(workspace_path)
        self.engine.load_all()
        self.tools = FederalTaxAuditTools(workspace_path)
        self.audit_result = self.engine.run_full_audit()

# Inicialização global do snapshot
current_snapshot = AuditSnapshot(WORKSPACE_DIR)

# API-02: Modelo Pydantic de validação para simulação
class SimulationRequest(BaseModel):
    presuncao_pct: float = Field(
        32.0, ge=1.0, le=100.0, 
        description="Percentual de Presunção de Lucro (1.0% a 100.0%)"
    )
    multa_oficio_pct: float = Field(
        75.0, ge=0.0, le=150.0, 
        description="Percentual de Multa de Ofício da RFB (0.0% a 150.0%)"
    )
    taxa_selic_pct: float = Field(
        9.5, ge=0.0, le=100.0, 
        description="Taxa Selic Acumulada no Período (0.0% a 100.0%)"
    )
    base_calculo_custom: Optional[float] = Field(
        None, ge=0.0,
        description="Base de cálculo customizada para simulação de faturamento"
    )

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "snapshot_version": current_snapshot.version_id,
        "snapshot_timestamp": current_snapshot.timestamp,
        "empresa": "LIDER PRESTADORA DE SERVICOS LTDA",
        "cnpj": "12.665.182/0001-07"
    }

@app.post("/api/reload")
def reload_data():
    """Recarrega atomicamente todos os arquivos do repositório gerando novo snapshot."""
    global current_snapshot
    try:
        new_snapshot = AuditSnapshot(WORKSPACE_DIR)
        current_snapshot = new_snapshot
        return {
            "status": "success",
            "message": "Dados fiscais e contábeis recarregados com sucesso.",
            "snapshot_version": new_snapshot.version_id,
            "snapshot_timestamp": new_snapshot.timestamp,
            "total_nfse": len(new_snapshot.engine.nfse_data),
            "total_darfs": len(new_snapshot.engine.darfs_data)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao recarregar snapshot: {str(e)}"
        )

@app.get("/api/audit")
def get_full_audit():
    """Retorna o relatório completo de auditoria com cruzamentos e achados do snapshot atual."""
    return current_snapshot.audit_result

@app.get("/api/documents")
def get_documents():
    """Retorna o catálogo de documentos segregados por tipo e metadados."""
    return {
        "snapshot_version": current_snapshot.version_id,
        "total": len(current_snapshot.engine.document_catalog),
        "documentos": current_snapshot.engine.document_catalog
    }

@app.get("/api/nfse")
def get_nfse_list(
    busca: Optional[str] = Query(None, description="Busca por número, tomador ou CNPJ"),
    apenas_omitidas: bool = Query(False, description="Filtrar apenas notas ausentes no livro fiscal"),
    competencia: Optional[str] = Query(None, description="Filtrar por competência (ex: 2026-08 ou 08/2026)"),
    com_retencao: bool = Query(False, description="Apenas notas com retenção na fonte de qualquer tributo")
):
    """
    Lista analítica das 172 Notas Fiscais Eletrônicas com enriquecimento documental:
    status original, ciclo de vida, CSRF desagregada e situação perante o Livro Fiscal.
    """
    res = []
    comp_filter_canon = ""
    if competencia:
        s = competencia.strip()
        if len(s) == 7 and s[2] == '/': # MM/YYYY
            comp_filter_canon = f"{s[3:]}-{s[:2]}"
        else:
            comp_filter_canon = s[:7]

    for n in current_snapshot.engine.nfse_data:
        num = n.get("numero_nfse")
        situacao = n.get("situacao_livro", "")
        is_missing = situacao.startswith("NAO_LOCALIZADA")

        if apenas_omitidas and not is_missing:
            continue

        comp_canonica = n.get("competencia_canonica", "")
        if comp_filter_canon and comp_canonica != comp_filter_canon:
            continue

        ret = n.get("retencoes", {})
        has_ret = any(float(ret.get(k, 0) or 0) > 0 for k in ['inss', 'irrf', 'iss', 'csll', 'pis', 'cofins'])
        if com_retencao and not has_ret:
            continue

        tomador_nome = n.get("tomador", {}).get("razao_social", "") or ""
        tomador_cnpj = n.get("tomador", {}).get("cnpj", "") or ""

        if busca:
            b = busca.lower()
            if b not in str(num).lower() and b not in tomador_nome.lower() and b not in tomador_cnpj.lower():
                continue

        res.append({
            "numero_nfse": num,
            "chave_nfse": n.get("chave_nfse"),
            "data_competencia": n.get("data_competencia_iso"),
            "competencia_mes": comp_canonica,
            "competencia_exibicao": format_competencia_display(comp_canonica),
            "mes_emissao": n.get("mes_emissao_canonico"),
            "data_emissao": n.get("data_emissao_iso"),
            "valor_servico": n.get("valor_servico", 0.0),
            "valor_liquido": n.get("valor_liquido", 0.0),
            "tomador": tomador_nome,
            "cnpj_tomador": tomador_cnpj,
            "municipio_prestacao": n.get("local_prestacao"),
            "descricao_servico": n.get("tributacao_nacional_desc") or n.get("nbs_desc"),
            "status_codigo": n.get("status_codigo", 100),
            "status_descricao": n.get("status_descricao", "100 - Autorizada"),
            "csrf_desagregada": n.get("csrf_desagregada", False),
            "retencoes": {
                "inss": ret.get("inss", 0.0),
                "irrf": ret.get("irrf", 0.0),
                "iss": ret.get("iss", 0.0),
                "csll": ret.get("csll", 0.0),
                "pis": ret.get("pis", 0.0),
                "cofins": ret.get("cofins", 0.0)
            },
            "situacao_livro": situacao,
            "situacao_livro_descricao": n.get("situacao_livro_descricao", "")
        })

    return {
        "snapshot_version": current_snapshot.version_id,
        "total_filtrado": len(res),
        "total_base": len(current_snapshot.engine.nfse_data),
        "notas": res
    }

@app.get("/api/crosscheck/monthly")
def get_monthly_crosscheck():
    """Retorna o confronto mensal de PIS e COFINS com DARFs pagos pelo PA."""
    return current_snapshot.audit_result["cruzamento_mensal_pis_cofins"]

@app.get("/api/crosscheck/quarterly")
def get_quarterly_crosscheck():
    """Retorna o confronto trimestral de IRPJ e CSLL com aplicação da LC 224/2025."""
    return current_snapshot.audit_result["cruzamento_trimestral_irpj_csll"]

@app.get("/api/darfs")
def get_darfs():
    """Retorna todos os 117 itens e 17 documentos de arrecadação de DARF da RFB."""
    return {
        "snapshot_version": current_snapshot.version_id,
        "total_itens": len(current_snapshot.engine.darfs_data),
        "total_arrecadado": current_snapshot.audit_result["total_arrecadado_darfs"],
        "resumo_por_tributo": current_snapshot.audit_result["resumo_darfs_pagos"],
        "comprovantes": current_snapshot.engine.darfs_data
    }

@app.post("/api/simulate")
def simulate_tax(payload: SimulationRequest):
    """
    Simula passivo tributário potencial com validação estrita via Pydantic
    e segregação metodológica do eixo de créditos previdenciários de INSS.
    """
    res = current_snapshot.tools.simulate_tax_scenario(
        presuncao_pct=payload.presuncao_pct,
        multa_oficio_pct=payload.multa_oficio_pct,
        taxa_selic_acumulada_pct=payload.taxa_selic_pct,
        base_calculo_custom=payload.base_calculo_custom
    )
    if res.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=res.get("mensagem")
        )
    return res

@app.get("/api/report/markdown")
def get_markdown_report():
    """
    API-01: Gera o Relatório Técnico Preliminar de Conciliação Fiscal Digital
    com valores dinâmicos do snapshot e seção explícita de limitações de escopo.
    """
    audit = current_snapshot.audit_result
    rf = audit["resumo_faturamento"]
    aus = audit["notas_ausentes_no_livro"]
    corte = aus.get("segregacao_corte_temporal", {})
    pos = corte.get("posterior_ao_fechamento_31_08", {})
    cob = corte.get("pendente_no_periodo_coberto", {})
    inv = audit.get("confronto_inverso_livro", {})

    sim_ref = current_snapshot.tools.simulate_tax_scenario(32.0, 75.0, 9.5)
    passivo_est = sim_ref["passivo_tributario_bruto"]

    md = f"""# RELATÓRIO TÉCNICO PRELIMINAR DE CONCILIAÇÃO FISCAL DIGITAL
**CLIENTE / EMPRESA AUDITADA:** {audit['empresa']['razao_social']}  
**CNPJ:** {audit['empresa']['cnpj']}  
**REGIME TRIBUTÁRIO:** {audit['empresa']['regime_tributario']}  
**ATIVIDADES:** {audit['empresa']['atividades']}  
**PERÍODO AUDITADO:** {audit['empresa']['periodo_auditado']}  
**DATA DE EMISSÃO:** {current_snapshot.timestamp}  
**VERSÃO DO SNAPSHOT:** `{current_snapshot.version_id}`  
**STATUS DA AUDITORIA:** PRELIMINAR - DIVERGÊNCIAS DOCUMENTAIS EM ANÁLISE  

---

## 1. SUMÁRIO EXECUTIVO E METODOLOGIA
Este laudo técnico preliminar consolida os procedimentos de cruzamento eletrônico de dados fiscais realizados entre:
1. **Documentos Fiscais Primários:** {rf['total_nfse_emitidas']} Notas Fiscais de Serviços Eletrônicas emitidas no Ambiente Nacional (SPED), perfazendo R$ {rf['valor_total_servicos_nfse']:,.2f};
2. **Demonstrativos Contábeis Mensais:** 16 arquivos de apuração de PIS (0,65%) e COFINS (3,00%) das competências de 01/2026 a 08/2026;
3. **Apurações Trimestrais:** Demonstrativos de IRPJ e CSLL do 1º, 2º e 3º Trimestres de 2026 com aplicação das regras da Lei Complementar nº 224/2025;
4. **Livro de Registro de Serviços:** Relatório fiscal 'Serviços.pdf' contendo {inv.get('total_notas_livro', 134)} notas escrituradas (R$ {inv.get('valor_contabil_total_livro', 0.0):,.2f}), encerrado em 31/08/2026;
5. **Comprovantes de Arrecadação:** 117 itens em 17 guias DARF da Secretaria Especial da Receita Federal do Brasil, somando R$ {audit['total_arrecadado_darfs']:,.2f}.

### 1.1 Indicadores Consolidados da Conciliação
- **Faturamento Bruto em NFS-e:** R$ {rf['valor_total_servicos_nfse']:,.2f} ({rf['total_nfse_emitidas']} notas)
- **Notas Ausentes no Livro Fiscal Fornecido:** {aus['quantidade']} notas (R$ {aus['valor_total']:,.2f})
  - *Corte Temporal (Pós-Encerramento de 31/08/2026):* {pos.get('quantidade', 47)} notas emitidas em setembro/outubro de 2026 (R$ {pos.get('valor_total', 1420678.86):,.2f}), aguardando escrituração no livro do 3º trimestre.
  - *Item Pendente no Período Coberto:* 1 nota (NFS-e nº 36 de R$ {cob.get('valor_total', 25466.65):,.2f}), com forte indício de substituição pela NFS-e nº 56 (status 101).
- **Confronto Inverso:** {inv.get('notas_apenas_no_livro_qtd', 10)} notas presentes no livro não constam no arquivo JSON consolidado (nº 7 a 15 e 17, totalizando R$ 233.350,29).
- **Retenções Previdenciárias Sofridas (INSS 11%):** R$ {rf['total_inss_retido_nfse']:,.2f}
- **Retenções de IRRF Sofridas:** R$ {rf['total_irrf_retido_nfse']:,.2f}
- **Retenções de Contribuições Sociais (CSRF desmembrada):** PIS: R$ {rf['total_pis_retido_nfse']:,.2f} | COFINS: R$ {rf['total_cofins_retido_nfse']:,.2f} | CSLL: R$ {rf['total_csll_retido_nfse']:,.2f}

---

## 2. LIMITAÇÕES DE ESCOPO E EVIDÊNCIAS DOCUMENTAIS COMPLEMENTARES
Em consonância com as normas brasileiras de auditoria (NBC TA 500 e NBC TA 230):
> **Ressalva Metodológica Obrigatória:** As divergências aritméticas apontadas neste relatório preliminar não constituem, por si sós, prova de omissão dolosa de receitas nem de créditos líquidos e certos exigíveis de imediato. A conclusão definitiva de passivo fiscal ou habilitação de restituição requer o cotejo com as seguintes fontes documentais:

1. **Livro Fiscal de Prestação de Serviços de Setembro/2026:** Necessário para conferir a escrituração das 47 notas fiscais emitidas após 31/08/2026;
2. **Declarações Federais Transmitidas:** Recibos e arquivos originais da EFD-Contribuições, EFD-Reinf, Escrituração Contábil Fiscal (ECF) e DCTFWeb;
3. **Consulta de Situação Fiscal no e-CAC:** Extrato oficial de pagamentos e compensações processadas pela RFB, vinculando PAs e quotas;
4. **Conta Gráfica de Retenções Previdenciárias:** Demonstração dos créditos escriturados no evento R-2020 da EFD-Reinf, abatimentos na DCTFWeb contra a contribuição patronal e histórico de pedidos PER/DCOMP anteriores.

---

## 3. ACHADOS DE AUDITORIA E ENQUADRAMENTO LEGAL

"""
    for a in audit["achados_auditoria"]:
        md += f"""### [{a['severidade']}] {a['id']}: {a['titulo']}
- **Categoria:** {a['categoria']}
- **Base Legal:** {a['base_legal']}
- **Impacto Financeiro Estimado:** R$ {a['impacto_financeiro']:,.2f}
- **Descrição Detalhada:** {a['descricao']}
- **Recomendação Técnica:** {a['recomendacao']}

"""

    md += f"""---

## 4. SIMULAÇÃO DE CENÁRIOS E EXPOSIÇÃO FISCAL
- **Eixo Passivo sob Fiscalização:** Aplicando presunção básica de 32% (majorada para 35,2% no excedente trimestral conforme LC 224/2025), multa de ofício de 75% e juros Selic de 9,5%, o passivo potencial bruto é estimado em **R$ {passivo_est:,.2f}**.
- **Eixo Créditos Previdenciários:** O saldo de retenções de INSS não compensadas em folha de pagamento totaliza **R$ {sim_ref['creditos_recuperaveis']['credito_liquido_estimado_per_dcomp']:,.2f}**.
- **Regra de Homologação:** Esses dois eixos não se anulam contabilmente de forma automática. O aproveitamento dos créditos exige procedimento formal via PER/DCOMP Web e reconhecimento pela autoridade fazendária.

---

## 5. PLANO DE AÇÃO RECOMENDADO
1. **Diligência Documental Imediata:** Obter o Livro Fiscal de Serviços referente ao 3º Trimestre (01/07 a 30/09/2026) para sanar o corte temporal das 47 notas fiscais.
2. **Validação da NFS-e nº 36:** Solicitar certidão ao emissor municipal/nacional confirmando se o serviço foi faturado e substituído pela NFS-e nº 56 (status 101).
3. **Auditoria da EFD-Contribuições em 08/2026:** Averiguar junto ao departamento fiscal o motivo da divergência de faturamento no demonstrativo de agosto/2026 (base declarada de R$ 12.820,08 vs faturamento de R$ 576.410,74).
4. **Habilitação de Saldo de Retenção de INSS:** Auditar a conta gráfica previdenciária na DCTFWeb e, havendo saldo credor residual, formular pleito via PER/DCOMP Web para compensação com débitos federais correntes.
"""
    return {"markdown": md}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
