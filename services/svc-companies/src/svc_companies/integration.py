from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from supreme_common.auth_context import context, create_access_token, require_role, delegated_company
from .database import get_db
from .models import Company
from .schemas import SwitchContextInput, BatchRequestDocumentsInput, AnalystAssignmentInput

integration_router = APIRouter()

@integration_router.post('/companies/{company_id}/assign-analyst')
async def assign(company_id: str, payload: AnalystAssignmentInput, db: Session = Depends(get_db)):
    from supreme_common.http_client import service_request
    from .models import User, CompanyTeamAssignment
    require_role('super_admin','supervisor')
    if not db.query(Company).filter(Company.id==company_id).first():
        raise HTTPException(404,'Empresa não encontrada.')
    response=await service_request('security-iam','GET','/security/auth/users/'+payload.analyst_user_id)
    identity=response.json()
    if identity['role'] not in {'super_admin','supervisor','analyst','bpo_operator'}:
        raise HTTPException(403,'O usuário não possui perfil de equipe contábil.')
    user=db.query(User).filter(User.id==identity['id']).first()
    if not user:
        # Compatibility projection only; authentication and password hashes stay in IAM.
        db.add(User(id=identity['id'],organization_id=identity['organization_id'],
            full_name=identity['email'],email=identity['email'],hashed_password='!',global_role=identity['role']))
        db.flush()
    assignment=db.query(CompanyTeamAssignment).filter(CompanyTeamAssignment.company_id==company_id,
        CompanyTeamAssignment.analyst_user_id==identity['id'],CompanyTeamAssignment.department==payload.department).first()
    if not assignment:
        db.add(CompanyTeamAssignment(company_id=company_id,analyst_user_id=identity['id'],department=payload.department))
    db.commit()
    return {'status':'assigned','company_id':company_id,'analyst_id':identity['id']}

@integration_router.get('/cockpit/companies/summary')
def cockpit(competence: str | None = None, db: Session = Depends(get_db)):
    from collections import Counter
    from .events import PortfolioResource
    require_role('super_admin','supervisor')
    companies=db.query(Company).all()
    identities={company.id for company in companies}
    query=db.query(PortfolioResource).filter(PortfolioResource.company_id.in_(identities))
    if competence:
        query=query.filter((PortfolioResource.competence==competence)|(PortfolioResource.competence.is_(None)))
    resources=query.all()
    pending_documents={r.company_id for r in resources if r.kind=='document' and r.status!='fulfilled'}
    tasks=[r for r in resources if r.kind=='task']
    observed={r.company_id for r in resources}
    pending={r.company_id for r in resources if (r.kind=='task' and r.status!='completed') or
        (r.kind=='document' and r.status!='fulfilled') or (r.kind=='bank' and r.status=='pending')}
    return {'total_companies':len(companies),'active_companies':sum(c.status=='active' for c in companies),
        'by_tax_regime':dict(Counter(c.tax_regime for c in companies)),
        'companies_in_good_standing':len(observed-pending) if resources else None,
        'companies_with_pending_documents':len(pending_documents) if resources else None,
        'companies_without_operational_data':len(identities-observed),
        'average_closing_progress_pct':round(100*sum(t.status=='completed' for t in tasks)/len(tasks),2) if tasks else None,
        'cnd_alerts_count':None,
        'unreconciled_transactions_total':sum(r.kind=='bank' and r.status=='pending' for r in resources)}

@integration_router.post('/companies/batch/request-documents')
async def batch(payload: BatchRequestDocumentsInput, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    from supreme_common.http_client import service_request
    require_role('super_admin','supervisor')
    query = db.query(Company)
    if payload.target_tax_regime:
        query = query.filter(Company.tax_regime == payload.target_tax_regime)
    if payload.company_ids:
        query = query.filter(Company.id.in_(payload.company_ids))
    companies = query.limit(201).all()
    if len(companies) > 200 or (payload.company_ids and set(payload.company_ids) != {c.id for c in companies}):
        raise HTTPException(403,'Lote deve conter até 200 empresas autorizadas.')
    errors, success = [], 0
    for company in companies:
        try:
            if company.status != 'active':
                raise HTTPException(409,'Empresa inativa.')
            with delegated_company(company.id):
                await service_request('documents','POST','/documents/checklists/request',
                    json={'company_id':company.id,'competence':payload.competence})
            success += 1
        except HTTPException as exc:
            errors.append({'company_id':company.id,'error':str(exc.detail)})
    return {'total_requested':len(companies),'success_count':success,'failed_count':len(errors),
            'errors':errors,'completed_at':datetime.now(timezone.utc)}

@integration_router.get('/companies/{company_id}')
def company_details(company_id: str, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, 'Empresa não encontrada.')
    return {column.name: getattr(company, column.name) for column in company.__table__.columns}

@integration_router.post('/auth/switch-company-context')
def switch(payload: SwitchContextInput, db: Session = Depends(get_db)):
    claims = context()
    company = db.query(Company).filter(Company.id == payload.target_company_id).first()
    if not company or (claims.get('role') not in {'super_admin', 'supervisor'} and company.id not in claims.get('company_ids', [])):
        raise HTTPException(403, 'Empresa não autorizada.')
    token = create_access_token({key: value for key, value in claims.items() if not key.startswith('_')} | {'company_id': company.id})
    return {'access_token': token, 'token_type': 'bearer', 'active_company_id': company.id, 'company_name': company.corporate_name}

def company_access():
    if not context().get('mfa_verified'):
        raise HTTPException(403, 'Configure e verifique o MFA antes de acessar empresas.')
