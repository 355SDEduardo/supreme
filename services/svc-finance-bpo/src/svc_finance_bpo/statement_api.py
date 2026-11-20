from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from starlette.concurrency import run_in_threadpool
from supreme_common.auth_context import context, require_role
from supreme_common.uploads import read_upload

from .database import get_db
from .statement_ai import PROMPT_VERSION, DescriptionAI, get_description_ai
from .statement_merge import merge_sources
from .statement_models import StatementImport, StatementMovement, StatementSource
from .statement_parsers import MAX_FILE_BYTES, digits, parse_statement
from .statement_types import ImportPayload, StatementError


def permission(request: Request) -> None:
    roles = ('super_admin', 'supervisor', 'analyst', 'bpo_operator', 'client_user', 'service')
    require_role(*roles, *(('viewer',) if request.method == 'GET' else ()))


router = APIRouter(prefix='/bills/statements', tags=['BPO — extratos complementares'],
                   dependencies=[Depends(permission)])


def scoped(db: Session, model: type):
    return db.query(model).filter(model.organization_id == context()['organization_id'],
                                  model.company_id == context()['company_id'])


def imported(db: Session, identifier: UUID) -> StatementImport:
    row = scoped(db, StatementImport).filter(StatementImport.id == str(identifier)).first()
    if row is None:
        raise HTTPException(404, 'Importação não encontrada nesta empresa.')
    return row


def commit(db: Session) -> None:
    try:
        db.commit()
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(409, 'A importação mudou durante a operação; atualize a prévia e tente novamente.') from None


def preview(row: StatementImport, *, offset: int = 0, limit: int = 100) -> dict:
    payload = ImportPayload.model_validate_json(row.payload)
    return {
        'id': row.id, 'status': row.status, 'account_key': row.account_key,
        'bank_code': payload.bank_code, 'agency': payload.agency, 'account': payload.account,
        'date_from': payload.date_from, 'date_to': payload.date_to,
        'total': len(payload.groups), 'offset': offset, 'limit': limit,
        'pending_descriptions': sum(g.selected_description_id is None for g in payload.groups),
        'issues': list(dict.fromkeys(issue for g in payload.groups for issue in g.issues)),
        'sources': [{**s.model_dump(exclude={'rows'}), 'transactions': len(s.rows)} for s in payload.sources],
        'results': [g.model_dump(mode='json') for g in payload.groups[offset:offset + limit]],
    }


@router.post('/imports', status_code=201)
async def upload(
    files: list[UploadFile] = File(...), bank_code: str = Form(...), agency: str = Form(...),
    account: str = Form(...), date_from: date = Form(...), date_to: date = Form(...),
    confirm_unidentified_sources: bool = Form(False), db: Session = Depends(get_db),
) -> dict:
    if not 1 <= len(files) <= 12:
        raise HTTPException(422, 'Envie entre 1 e 12 arquivos da mesma conta.')
    bank_code, agency, account = digits(bank_code).zfill(3), digits(agency), digits(account)
    if bank_code not in {'033', '756'} or not agency or not account or max(len(agency), len(account)) > 30:
        raise HTTPException(422, 'Informe banco 033 (Santander) ou 756 (Sicoob), agência e conta válidos.')
    if not 0 <= (date_to - date_from).days <= 365:
        raise HTTPException(422, 'Informe um período de até 366 dias em ordem cronológica.')
    sources, raw_sources, seen = [], [], set()
    for file in files:
        raw = await read_upload(file, MAX_FILE_BYTES)
        try:
            source = await run_in_threadpool(parse_statement, file.filename or '', raw, date_from, date_to)
        except StatementError as exc:
            raise HTTPException(422, str(exc)) from None
        if source.sha256 in seen:
            continue
        seen.add(source.sha256)
        for key, expected in (('bank_code', bank_code), ('agency', agency), ('account', account)):
            actual = getattr(source, key)
            if actual and actual != expected:
                raise HTTPException(422, f'{source.filename}: {key} do documento difere da conta selecionada.')
        if (not source.agency or not source.account or not source.bank_code) and not confirm_unidentified_sources:
            raise HTTPException(422, 'Confirme a conta dos arquivos que não trazem identificação bancária completa.')
        sources.append(source)
        raw_sources.append(raw)
        if sum(len(s.rows) for s in sources) > 10000:
            raise HTTPException(422, 'O lote excede 10.000 linhas; divida por período.')
    try:
        groups = await run_in_threadpool(merge_sources, sources)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if len(groups) > 5000:
        raise HTTPException(422, 'O lote excede 5.000 movimentos; divida por período.')
    account_key = f'{bank_code}:{agency}:{account}'
    fingerprint = hashlib.sha256(json.dumps([account_key, str(date_from), str(date_to),
                                            sorted(seen), 'parser-v1']).encode()).hexdigest()
    existing = scoped(db, StatementImport).filter(StatementImport.fingerprint == fingerprint).first()
    if existing:
        return preview(existing)
    tenant = {'organization_id': context()['organization_id'], 'company_id': context()['company_id']}
    row = StatementImport(id=str(uuid4()), account_key=account_key, fingerprint=fingerprint,
                          created_by=context()['sub'], created_at=datetime.now(timezone.utc).isoformat(),
                          status='preview', payload=ImportPayload(
                              bank_code=bank_code, agency=agency, account=account,
                              date_from=date_from, date_to=date_to, sources=sources, groups=groups,
                          ).model_dump_json(), **tenant)
    db.add(row)
    db.flush()
    for source, raw in zip(sources, raw_sources):
        db.add(StatementSource(id=str(uuid4()), import_id=row.id, source_id=source.id,
                               filename=source.filename, content=raw, **tenant))
    commit(db)
    return preview(row)


@router.get('/imports')
def imports(db: Session = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> list[dict]:
    return [{'id': r.id, 'account_key': r.account_key, 'status': r.status, 'created_at': r.created_at}
            for r in scoped(db, StatementImport).order_by(StatementImport.created_at.desc()).offset(offset).limit(limit)]


@router.get('/imports/{import_id}')
def get_import(import_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
               db: Session = Depends(get_db)) -> dict:
    return preview(imported(db, import_id), offset=offset, limit=limit)


@router.post('/imports/{import_id}/descriptions')
async def descriptions(import_id: UUID, db: Session = Depends(get_db), ai: DescriptionAI = Depends(get_description_ai)) -> dict:
    row = imported(db, import_id)
    if row.status == 'registered':
        return preview(row)
    payload = ImportPayload.model_validate_json(row.payload)
    if any(g.issues for g in payload.groups):
        raise HTTPException(409, 'Resolva as divergências de pareamento ou moeda antes da seleção por IA.')
    pending = [g for g in payload.groups if g.selected_description_id is None][:25]
    if not pending:
        return preview(row)
    selection, response_id = await ai.choose(pending)
    by_id = {s.group_id: s for s in selection.selections}
    for group in pending:
        result = by_id[group.id]
        # Defense in depth for alternative/injected adapters, not only the OpenAI transport.
        if result.candidate_id not in {c.id for c in group.candidates}:
            raise HTTPException(502, 'Seleção de descrição fora das fontes permitidas.')
        group.selected_description_id = result.candidate_id
        group.selection_reason = result.reason
        group.ai_model, group.ai_response_id = ai.model, response_id
    row.payload = payload.model_dump_json()
    commit(db)
    return preview(row)


@router.post('/imports/{import_id}/register')
def register(import_id: UUID, db: Session = Depends(get_db)) -> dict:
    row = imported(db, import_id)
    if row.status == 'registered':
        return {'id': row.id, 'status': row.status, 'registered': scoped(db, StatementMovement).filter(
            StatementMovement.import_id == row.id).count()}
    payload = ImportPayload.model_validate_json(row.payload)
    if any(g.issues or not g.selected_description_id for g in payload.groups):
        raise HTTPException(409, 'O registro exige pareamento válido e seleção de todas as descrições pela IA.')
    # The status update provides the optimistic lock before inserting any ledger movement.
    row.status = 'registered'
    try:
        db.flush()
        tenant = {'organization_id': context()['organization_id'], 'company_id': context()['company_id']}
        created = 0
        for group in payload.groups:
            strong_ids = sorted({c.reference for c in group.candidates if c.reference_kind == 'fitid' and c.reference})
            key = hashlib.sha256(('fitid:' + '|'.join(strong_ids) if strong_ids else 'group:' + group.id).encode()).hexdigest()
            existing = scoped(db, StatementMovement).filter(StatementMovement.account_key == row.account_key,
                                                           StatementMovement.dedupe_key == key).first()
            if existing:
                if (existing.date, Decimal(existing.amount), existing.type) != (group.date, group.amount, group.type):
                    raise HTTPException(409, 'Identificador bancário já registrado com data, valor ou tipo diferentes.')
                continue
            overlap = scoped(db, StatementMovement).filter(
                StatementMovement.account_key == row.account_key, StatementMovement.date == group.date,
                StatementMovement.amount == str(group.amount.quantize(Decimal('.01'))),
                StatementMovement.type == group.type, StatementMovement.import_id != row.id,
            ).all()
            if overlap and (not strong_ids or any(json.loads(r.provenance).get('fitids') == [] for r in overlap)):
                raise HTTPException(409, 'Há movimentos semelhantes em outro lote sem FITID comparável. Reimporte as fontes juntas para evitar duplicidade.')
            chosen = next(c for c in group.candidates if c.id == group.selected_description_id)
            provenance = {'fields': group.field_sources, 'description': chosen.id,
                          'candidates': [c.model_dump(mode='json') for c in group.candidates],
                          'fitids': strong_ids, 'ai_model': group.ai_model, 'ai_response_id': group.ai_response_id,
                          'prompt_version': PROMPT_VERSION, 'reason': group.selection_reason}
            db.add(StatementMovement(id=str(uuid4()), import_id=row.id, group_id=group.id,
                                      account_key=row.account_key, dedupe_key=key, date=group.date,
                                      amount=str(group.amount.quantize(Decimal('.01'))), type=group.type,
                                      description=chosen.description, provenance=json.dumps(provenance), **tenant))
            created += 1
        commit(db)
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(409, 'Registro concorrente detectado; atualize a importação.') from None
    return {'id': row.id, 'status': row.status, 'registered': created}


@router.get('/transactions')
def movements(db: Session = Depends(get_db), account_key: str | None = None, date_from: date | None = None,
              date_to: date | None = None, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)) -> dict:
    query = scoped(db, StatementMovement)
    if account_key:
        query = query.filter(StatementMovement.account_key == account_key)
    if date_from:
        query = query.filter(StatementMovement.date >= date_from)
    if date_to:
        query = query.filter(StatementMovement.date <= date_to)
    return {'total': query.count(), 'offset': offset, 'limit': limit, 'results': [{
        'id': r.id, 'date': r.date, 'description': r.description, 'amount': r.amount, 'type': r.type,
        'account_key': r.account_key, 'import_id': r.import_id, 'provenance': json.loads(r.provenance),
    } for r in query.order_by(StatementMovement.date.desc(), StatementMovement.id).offset(offset).limit(limit)]}


@router.get('/imports/{import_id}/sources/{source_id}')
def original(import_id: UUID, source_id: str, db: Session = Depends(get_db)) -> Response:
    imported(db, import_id)
    row = scoped(db, StatementSource).filter(StatementSource.import_id == str(import_id),
                                            StatementSource.source_id == source_id).first()
    if not row:
        raise HTTPException(404, 'Documento não encontrado.')
    extension = row.filename.rsplit('.', 1)[-1].lower()
    return Response(row.content, media_type='application/octet-stream',
                    headers={'Content-Disposition': f'attachment; filename="extrato-{source_id}.{extension}"'})
