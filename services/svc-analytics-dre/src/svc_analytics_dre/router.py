"""FastAPI Router for Feature 07: Fluxo de Caixa, DRE e Dashboards."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from svc_analytics_dre.database import get_db

from .schemas import (
    DreResponse, CashFlowResponse, KpisResponse, ExportReportInput
)
from .calculations import (
    get_company_dre, get_company_cash_flow, get_company_kpis
)

router = APIRouter(prefix="/analytics", tags=["Feature 07: Fluxo de Caixa, DRE e Dashboards"])


@router.get("/companies/{company_id}/dre", response_model=DreResponse)
def get_dre(
    company_id: str,
    competence: str = Query("2026-09"),
    db: Session = Depends(get_db)
):
    """Retrieve dynamic DRE with vertical and horizontal analysis."""
    return get_company_dre(db=db, company_id=company_id, competence=competence)


@router.get("/companies/{company_id}/cash-flow", response_model=CashFlowResponse)
def get_cash_flow(
    company_id: str,
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db)
):
    """Retrieve daily cash flow projection and deficit alerts."""
    return get_company_cash_flow(db=db, company_id=company_id, days_forward=days)


@router.get("/companies/{company_id}/kpis", response_model=KpisResponse)
def get_kpis(
    company_id: str,
    competence: str = Query("2026-09"),
    db: Session = Depends(get_db)
):
    """Retrieve executive financial ratios (PMR, PMP, Financial Cycle, Break-even, Liquidity)."""
    return get_company_kpis(db=db, company_id=company_id, competence=competence)


@router.post("/companies/{company_id}/export-pdf")
async def export_executive_report(
    company_id: str,
    payload: ExportReportInput,
    db: Session = Depends(get_db)
):
    """Generates executive financial report."""
    from supreme_common.http_client import service_request
    from fastapi.responses import Response
    dre = get_company_dre(db, company_id, payload.competence)
    response = await service_request('pdf-tools', 'POST', '/pdf/render-report', json={
        'title': f'DRE {company_id} - {payload.competence}',
        'lines': [f'{key}: {value}' for key, value in dre.model_dump(mode='json').items()]})
    return Response(response.content, media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename=dre.pdf'})
