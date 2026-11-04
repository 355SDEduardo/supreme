from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, String, Date, Text
from sqlalchemy.orm import Session
from supreme_common.auth_context import context, require_role
from supreme_common.http_client import service_request
from .database import Base, get_db
from .models import DocumentDownloadReceipt

class PublishedGuide(Base):
    __tablename__ = 'published_guides'
    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), nullable=False)
    title = Column(String(250), nullable=False)
    competence = Column(String(7), nullable=False)
    due_date = Column(Date, nullable=False)
    barcode_line = Column(String(150), nullable=True)
    pix_key = Column(String(150), nullable=True)

class GuideInput(BaseModel):
    document_id: str
    title: str
    competence: str
    due_date: date
    barcode_line: str | None = None
    pix_key: str | None = None

integration_router = APIRouter(prefix='/portal')

@integration_router.post('/guides', status_code=201)
async def publish(payload: GuideInput, db: Session = Depends(get_db)):
    require_role('super_admin','supervisor','analyst')
    await service_request('documents','GET',f'/documents/{payload.document_id}/metadata')
    if db.query(PublishedGuide).filter(PublishedGuide.id == payload.document_id).first():
        raise HTTPException(409,'Guia já publicada.')
    data=payload.model_dump()
    data.pop('document_id')
    row=PublishedGuide(id=payload.document_id,company_id=context()['company_id'],**data)
    db.add(row)
    db.commit()
    return {'document_id':row.id,'status':'published'}

@integration_router.get('/guides/available')
def guides(db: Session = Depends(get_db)):
    receipts={r.document_id:r.downloaded_at for r in db.query(DocumentDownloadReceipt).all()}
    return [{'document_id':g.id,'company_id':g.company_id,'title':g.title,'competence':g.competence,
        'due_date':g.due_date,'barcode_line':g.barcode_line,'pix_key':g.pix_key,
        'download_url':f'/api/v1/documents/{g.id}/content','viewed_by_client':g.id in receipts,
        'viewed_at':receipts.get(g.id)} for g in db.query(PublishedGuide).all()]
