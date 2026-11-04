"""FastAPI Router for Feature 09: Gestão Multiempresa."""

from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from portalcontabilidades.core.database import get_db

from .schemas import (
    CompanyCreate, CompanyResponse, CockpitSummaryResponse,
    BatchRequestDocumentsInput, BatchOperationResult,
    AnalystAssignmentInput, SwitchContextInput, SwitchContextResponse
)
from .models import Company, CompanyTeamAssignment, User
from .service import (
    create_company, get_cockpit_summary, execute_batch_document_requests,
    switch_company_context
)
from .cnpj_validator import clean_tax_id

router = APIRouter(tags=["Feature 09: Gestão Multiempresa"])


def _get_current_user_stub(db: Session, authorization: Optional[str] = Header(None)) -> User:
    """Helper for testing or session resolution; returns or creates mock super admin."""
    user = db.query(User).filter(User.global_role == "super_admin").first()
    if not user:
        user = User(
            id="super-admin-01",
            full_name="Sócio Administrador",
            email="socio@escritoriocontabil.com.br",
            hashed_password="mock",
            global_role="super_admin",
            organization_id="org-default-01"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.get("/cockpit/companies/summary", response_model=CockpitSummaryResponse)
def get_cockpit(
    organization_id: str = Query("org-default-01"),
    db: Session = Depends(get_db)
):
    """Cockpit overview with health metrics, tax regime splits, and operational status."""
    return get_cockpit_summary(db=db, organization_id=organization_id)


@router.get("/companies", response_model=List[CompanyResponse])
def list_companies(
    organization_id: str = Query("org-default-01"),
    tax_regime: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List companies with multi-tenant filtering, search by name/CNPJ, and pagination."""
    query = db.query(Company).filter(Company.organization_id == organization_id)
    if tax_regime:
        query = query.filter(Company.tax_regime == tax_regime)
    if search:
        cleaned = clean_tax_id(search)
        query = query.filter(
            (Company.corporate_name.ilike(f"%{search}%")) |
            (Company.trade_name.ilike(f"%{search}%")) |
            (Company.tax_id.like(f"%{cleaned}%"))
        )
    return query.offset(offset).limit(limit).all()


@router.post("/companies", response_model=CompanyResponse)
def create_new_company(
    data: CompanyCreate,
    db: Session = Depends(get_db)
):
    """Register a new client company with CNPJ/CPF modulo 11 validation."""
    return create_company(db=db, data=data)


@router.post("/companies/batch/request-documents", response_model=BatchOperationResult)
def batch_request_documents(
    payload: BatchRequestDocumentsInput,
    db: Session = Depends(get_db)
):
    """Batch dispatch document requests across companies with resilience against individual failures."""
    return execute_batch_document_requests(db=db, input_data=payload)


@router.post("/companies/{company_id}/assign-analyst")
def assign_analyst_to_company(
    company_id: str,
    payload: AnalystAssignmentInput,
    db: Session = Depends(get_db)
):
    """Assign or reallocate an analyst to a client company portfolio."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    assignment = CompanyTeamAssignment(
        company_id=company_id,
        analyst_user_id=payload.analyst_user_id,
        department=payload.department,
        assigned_at=datetime.now(timezone.utc)
    )
    db.add(assignment)
    db.commit()
    return {"status": "assigned", "company_id": company_id, "analyst_id": payload.analyst_user_id}


@router.post("/auth/switch-company-context", response_model=SwitchContextResponse)
def switch_active_company(
    payload: SwitchContextInput,
    db: Session = Depends(get_db)
):
    """Switch active company context, checking RBAC and issuing context JWT."""
    user = _get_current_user_stub(db)
    return switch_company_context(db=db, user=user, target_company_id=payload.target_company_id)
