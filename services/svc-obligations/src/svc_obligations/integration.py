from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from supreme_common.http_client import service_request
from supreme_common.auth_context import context, delegated_company
from .database import get_db
from .schemas import CompetenceBatchGenerateInput, CompetenceBatchGenerateResult, TaskAttachmentInput
from .service import generate_tasks_for_competence, attach_task_receipt

integration_router = APIRouter()

@integration_router.post('/tasks/generate-competence', response_model=CompetenceBatchGenerateResult)
async def generate(payload: CompetenceBatchGenerateInput, db: Session = Depends(get_db)):
    from contextlib import nullcontext
    response = await service_request('companies', 'GET', '/companies', params={'limit':5000})
    companies = {c['id']:c for c in response.json()}
    ids = payload.company_ids or [context()['company_id']]
    if len(ids) > 200 or any(company_id not in companies for company_id in ids):
        raise HTTPException(403,'Empresa fora da carteira autorizada ou lote acima de 200 empresas.')
    generated, errors = 0, []
    processed = 0
    for company_id in dict.fromkeys(ids):
        try:
            manager = delegated_company(company_id) if company_id != context().get('company_id') else nullcontext()
            with manager:
                result = generate_tasks_for_competence(db, payload.model_copy(update={'company_ids':[company_id]}),
                    {company_id:companies[company_id]['tax_regime']})
                generated += result.tasks_generated
                processed += result.companies_processed
                errors.extend(result.errors)
        except HTTPException as exc:
            db.rollback()
            errors.append({'company_id':company_id,'error':str(exc.detail)})
    return CompetenceBatchGenerateResult(competence=payload.competence,companies_processed=processed,tasks_generated=generated,errors=errors)

@integration_router.post('/tasks/{task_id}/attachments')
async def attachment(task_id: str, payload: TaskAttachmentInput, db: Session = Depends(get_db)):
    response = await service_request('documents', 'GET', f'/documents/{payload.file_id}/metadata')
    if response.json()['sha256'] != payload.file_hash:
        raise HTTPException(409, 'Hash não corresponde ao documento em custódia.')
    task = attach_task_receipt(db, task_id, payload.file_id, payload.file_hash, context()['sub'], 'internal')
    return {'status': 'attached', 'task_id': task.id, 'receipt_file_id': task.receipt_file_id}
