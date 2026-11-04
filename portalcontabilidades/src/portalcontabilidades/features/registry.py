"""Explicit feature registration, with stable identifiers for API discovery."""
from dataclasses import dataclass

from fastapi import APIRouter

from .analytics.router import router as analytics_router
from .automacao_ia.router import router as automation_router
from .conciliacao.router import router as reconciliation_router
from .documentos.router import router as documents_router
from .financeiro.router import router as finance_router
from .integracoes_fiscais.router import router as fiscal_router
from .multiempresa.router import router as companies_router
from .obrigacoes.router import router as obligations_router
from .portal_cliente.router import router as client_router
from .seguranca.router import cert_router, router as security_router


@dataclass(frozen=True)
class Feature:
    folder: str
    label: str
    routers: tuple[APIRouter, ...]


# Folder identifiers remain stable even though the Python packages were renamed.
FEATURES = (
    Feature("10-seguranca-lgpd-e-certificados", "10. Segurança, LGPD e Certificados", (security_router, cert_router)),
    Feature("09-gestao-multiempresa", "09. Gestão Multiempresa", (companies_router,)),
    Feature("01-central-de-obrigacoes-tarefas-e-prazos", "01. Central de Obrigações e Prazos", (obligations_router,)),
    Feature("02-gestao-inteligente-de-documentos", "02. Gestão Inteligente de Documentos", (documents_router,)),
    Feature("03-conciliacao-bancaria-automatica", "03. Conciliação Bancária Automática", (reconciliation_router,)),
    Feature("04-contas-a-pagar-e-receber", "04. Contas a Pagar e Receber", (finance_router,)),
    Feature("05-integracoes-fiscais-e-governamentais", "05. Integrações Fiscais e Governamentais", (fiscal_router,)),
    Feature("06-portal-do-cliente-e-comunicacao", "06. Portal do Cliente e Comunicação", (client_router,)),
    Feature("07-fluxo-de-caixa-dre-e-dashboards", "07. Fluxo de Caixa, DRE e Dashboards", (analytics_router,)),
    Feature("08-automacao-e-ia-contabil", "08. Automação e IA Contábil", (automation_router,)),
)
