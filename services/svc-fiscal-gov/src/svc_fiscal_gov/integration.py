from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Column, String, Text
from sqlalchemy.orm import Session
from supreme_common.http_client import service_request
from supreme_common.security_xml import parse_safe_xml
from .database import Base, get_db
from .models import FiscalTransmission
from .schemas import FiscalTransmissionCreate, FiscalTransmissionResponse, DctfwebConsolidationInput

class RetentionProjection(Base):
    __tablename__ = 'retention_projections'
    id = Column(String(250), primary_key=True)
    totals = Column(Text, nullable=False)
    source_version = Column(String(100), nullable=False)

integration_router = APIRouter(prefix='/fiscal')

@integration_router.post('/transmissions/enqueue', response_model=FiscalTransmissionResponse)
def enqueue(payload: FiscalTransmissionCreate, db: Session = Depends(get_db)):
    if payload.system_target not in {'esocial','efd_reinf','dctfweb','nfse_nacional','integra_contador'}:
        raise HTTPException(422, 'Sistema fiscal inválido.')
    if payload.environment not in {'production','test_restricted'}:
        raise HTTPException(422, 'Ambiente fiscal inválido.')
    try:
        parse_safe_xml(payload.xml_payload.encode())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = db.query(FiscalTransmission).filter(FiscalTransmission.idempotency_key == payload.idempotency_key).first()
    if row:
        if row.xml_sent_payload != payload.xml_payload:
            raise HTTPException(409, 'Chave idempotente já usada com outro conteúdo.')
        return row
    row = FiscalTransmission(company_id=payload.company_id, system_target=payload.system_target,
        event_type=payload.event_type, competence=payload.competence, environment=payload.environment,
        idempotency_key=payload.idempotency_key, xml_sent_payload=payload.xml_payload, status='queued', attempts=0)
    db.add(row)
    db.commit()
    return row

@integration_router.post('/transmissions/{transmission_id}/retry')
def retry(transmission_id: str, db: Session = Depends(get_db)):
    row = db.query(FiscalTransmission).filter(FiscalTransmission.id == transmission_id).first()
    if not row:
        raise HTTPException(404, 'Transmissão não encontrada.')
    # Local validation cannot fabricate a government receipt or approval.
    raise HTTPException(501, 'Configure o adaptador oficial de transmissão antes de reenviar ao fisco.')

@integration_router.get('/companies/{company_id}/cnd-status')
def cnd(company_id: str):
    raise HTTPException(501, 'Consulta SERPRO exige credenciais e procuração do ambiente oficial.')

@integration_router.post('/dctfweb/consolidate')
async def consolidate(payload: DctfwebConsolidationInput):
    from supreme_common.competence import normalize_competencia
    # Only the HTTP contract is shared, never the NFSe database or ORM tables.
    response = await service_request('nfse-engine', 'GET', '/api/export/json')
    competence = normalize_competencia(payload.competence)
    totals = {key: Decimal('0') for key in ('inss','irrf','pis','cofins','csll')}
    for note in response.json()['notas']:
        if str(note['data_competencia']).startswith(competence):
            for key in totals:
                totals[key] += Decimal(str(note.get('retencoes', {}).get(key, 0)))
    pcc = totals['pis'] + totals['cofins'] + totals['csll']
    return {'company_id': payload.company_id, 'competence': competence, 'darf_number': None,
        'total_inss_previdenciario': str(totals['inss']), 'total_irrf_retencao': str(totals['irrf']),
        'total_pcc_retencao': str(pcc), 'total_darf_amount': str(totals['inss'] + totals['irrf'] + pcc),
        'status': 'previa_sem_transmissao', 'source_snapshot': response.json().get('metadata', {}).get('version')}
