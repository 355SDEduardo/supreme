"""Unified national/ABRASF/municipal engine with persistent cancellation projection."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import uuid
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from supreme_common.auth_context import AuthMiddleware, context, enforce_request_context
from supreme_common.sqlite_outbox import enqueue, drain
from supreme_common.security_xml import xml_inputs
from supreme_common.state import tenant_database
from supreme_common.uploads import RequestLimitMiddleware, read_upload
from .models import NFSNacionalModel, Participante, TributacaoFederal
from .parser import NFSeNacionalParser
from .retencoes import build_retention_report, get_retention_amounts
from .exporter import NFSeExporter
from .multilayout.nfse_pipeline import process_nfse_batch
from .multilayout.nfse_reporting import generate_nfse_excel_report, build_nfse_json_payload
from .sample_generator import SAMPLE_FILES
from .workspace import Workspaces, current_workspace, workspace_context

def database():
    if workspace := current_workspace.get():
        return workspace.database()
    return tenant_database('nfse')

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS artifacts (sha TEXT PRIMARY KEY, filename TEXT, content BLOB)')
    db.execute('CREATE TABLE IF NOT EXISTS notes (key TEXT PRIMARY KEY, sha TEXT, note TEXT, canonical TEXT, status TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS snapshots (version TEXT PRIMARY KEY, body TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, body TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS tombstones (key TEXT PRIMARY KEY)')

def adapt(doc, original):
    try:
        note = NFSeNacionalParser.parse(original, filename=doc.filename)
    except (ValueError, TypeError, KeyError, ArithmeticError):
        when = doc.identity.dps_issued_at or doc.identity.nfse_issued_at or datetime.now(timezone.utc)
        note = NFSNacionalModel(chave_nfse=doc.identity.access_key or doc.identity.xml_id or doc.artifact_sha256,
            numero_nfse=int(doc.identity.nfse_number) if doc.identity.nfse_number.isdecimal() else 0,
            data_hora_processamento=when, data_emissao_dps=when,
            data_competencia=doc.identity.competence_date or when.date(),
            emitente=Participante(cnpj=doc.provider.tax_id, razao_social=doc.provider.name),
            tomador=Participante(cnpj=doc.customer.tax_id, razao_social=doc.customer.name) if doc.customer else Participante(),
            tributos_federais=TributacaoFederal(), descricao_servico='; '.join(s.description for s in doc.services),
            arquivo_origem=doc.filename)
        if doc.services:
            service = doc.services[0]
            note.codigo_tributacao_nacional = service.national_tax_code
            note.tributacao_nacional_desc = service.lc116_subitem or service.municipal_tax_code
            note.codigo_nbs = service.nbs_code or None
            note.codigo_municipio_incidencia = service.incidence_city_ibge
            note.local_incidencia = service.incidence_city_ibge
            note.local_prestacao = service.execution_city_ibge
        note.optante_simples_nacional = 2 if doc.provider.is_simple_national else 1
    amounts, federal = doc.amounts, doc.federal_withholding
    note.valor_servico = amounts.gross_service
    note.valor_liquido = amounts.net_amount_calculated
    note.valor_issqn = amounts.iss_amount
    note.base_calculo = amounts.iss_base
    note.valor_total_retencoes = amounts.total_withheld
    retention_type = doc.iss_withholding_type.value
    note.tipo_retencao_issqn = int(retention_type) if retention_type in {'1','2','3'} else 1
    note.tributos_federais.valor_ret_cp_inss = federal.inss_cp
    note.tributos_federais.valor_ret_irrf = federal.irrf
    note.tributos_federais.valor_ret_csll = federal.csll
    note.tributos_federais.valor_pis = federal.pis
    note.tributos_federais.valor_cofins = federal.cofins
    note.tributos_federais.tp_retencao_pis_cofins = 1 if federal.pis or federal.cofins else 0
    if federal.social_contributions_total is not None:
        total = federal.social_contributions_total
        pis = (total * Decimal('0.65') / Decimal('4.65')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        cofins = (total * Decimal('3') / Decimal('4.65')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        note.tributos_federais.valor_pis = pis
        note.tributos_federais.valor_cofins = cofins
        note.tributos_federais.valor_ret_csll = total - pis - cofins
        note.tributos_federais.tp_retencao_pis_cofins = 1
    note.status = 100 if doc.status.value == 'AUTHORIZED' else 101
    severities = {finding.severity.value for finding in doc.findings}
    if severities & {'CRITICAL','HIGH'}:
        note.auditoria.status_conciliacao = 'INCONSISTENTE'
    elif 'WARNING' in severities:
        note.auditoria.status_conciliacao = 'ALERTA'
    note.auditoria.equacao_liquido_valida = amounts.net_difference == 0
    note.auditoria.diferenca_liquido = amounts.net_difference
    note.auditoria.detalhes_auditoria = list(dict.fromkeys(note.auditoria.detalhes_auditoria + [f.description for f in doc.findings]))
    return note

def notes(active=True):
    with database() as db:
        schema(db)
        rows = db.execute('SELECT note FROM notes' + (" WHERE status='AUTHORIZED'" if active else '')).fetchall()
    return [NFSNacionalModel.model_validate_json(row[0]) for row in rows]

def ingest(inputs, mode, *, replace=False):
    with database() as db:
        schema(db)
        if replace:
            db.execute('DELETE FROM artifacts')
            db.execute('DELETE FROM tombstones')
        for filename, content in inputs:
            if mode == 'nacional_strict':
                NFSeNacionalParser.parse(content, filename=filename)
            digest = sha256(content).hexdigest()
            db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?)', (digest, filename, content))
        artifacts = db.execute('SELECT filename,content FROM artifacts ORDER BY rowid').fetchall()
        if sum(len(raw) for _, raw in artifacts) > 100 * 1024 * 1024 or len(artifacts) > 5000:
            raise ValueError('Acervo excede 5.000 XMLs ou 100 MB por empresa; arquive a competência antes de continuar.')
        state = process_nfse_batch(artifacts)
        if replace and inputs and (state.issues or not any(doc.kind.value == 'NFSE' for doc in state.documents)):
            raise ValueError('Lote não importado: há XMLs sem NFS-e reconhecida ou com erros de leitura. '
                             'Confira os arquivos; o lote anterior foi preservado.')
        raw_by_sha = {sha256(raw).hexdigest(): raw for _, raw in artifacts}
        db.execute('DELETE FROM notes')
        for doc in state.documents:
            if doc.kind.value != 'NFSE':
                continue
            note = adapt(doc, raw_by_sha[doc.artifact_sha256])
            if db.execute('SELECT 1 FROM tombstones WHERE key=?',(note.chave_nfse,)).fetchone():
                continue
            db.execute('INSERT INTO notes VALUES(?,?,?,?,?)', (note.chave_nfse, doc.artifact_sha256,
                note.model_dump_json(), json.dumps(doc.to_dict()), doc.status.value))
        version = str(uuid.uuid4())
        data = {'metadata': {'version': version, 'total_notas': len(state.documents)}, 'notas': [
            {**json.loads(row[0]), 'retencoes': {k: float(v) for k,v in get_retention_amounts(NFSNacionalModel.model_validate_json(row[0])).items()}}
            for row in db.execute("SELECT note FROM notes WHERE status='AUTHORIZED'")]}
        data['metadata']['total_notas'] = len(data['notas'])
        if current_workspace.get():
            db.execute('DELETE FROM snapshots')
        db.execute('INSERT INTO snapshots VALUES(?,?)', (version, json.dumps(data)))
        db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('audit', json.dumps(build_nfse_json_payload(state))))
        db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('latest', json.dumps(version)))
        if not current_workspace.get():
            enqueue(db, 'NFSeBatchProcessed', {'snapshot_version': version,
                'snapshot_uri': '/api/export/json?version=' + version,
                'total_notes': len(data['notas'])}, event_id=version)
    if not current_workspace.get():
        drain('nfse')
    return {'success': True, 'processed_count': len(state.documents), 'error_count': len(state.issues),
            'message': f'{len(state.documents)} documento(s) processado(s).',
            'errors': state.issues, 'processed_keys': [doc.identity.access_key for doc in state.documents],
            'snapshot_version': version, 'audit': build_nfse_json_payload(state)}

def create_app():
    import asyncio
    import contextlib
    from contextlib import asynccontextmanager
    from supreme_common.sqlite_outbox import run
    @asynccontextmanager
    async def lifespan(app):
        from supreme_common.auth_context import secret_key
        secret_key()
        async def expire_workspaces():
            while True:
                await asyncio.sleep(30)
                app.state.workspaces.expire()
        task = asyncio.create_task(run('nfse'))
        cleanup = asyncio.create_task(expire_workspaces())
        yield
        task.cancel()
        cleanup.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup
        app.state.workspaces.close()
    app = FastAPI(title='svc-nfse-engine', lifespan=lifespan,
                  dependencies=[Depends(enforce_request_context), Depends(workspace_context)])
    app.state.workspaces = Workspaces()
    app.add_middleware(RequestLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    @app.get('/health', dependencies=[])
    @app.get('/api/health', dependencies=[])
    def health():
        return {'status': 'ok', 'service': 'svc-nfse-engine'}

    @app.post('/api/workspaces')
    def create_workspace():
        return {'workspace': app.state.workspaces.create(), 'expires_in': 7200}

    @app.delete('/api/workspaces/{key}')
    def close_workspace(key: str):
        app.state.workspaces.delete(key)
        return {'success': True}

    @app.post('/api/upload')
    async def upload(files: list[UploadFile] = File(...), mode: str = Query('multi_layout_audit', pattern='^(nacional_strict|multi_layout_audit)$')):
        if not 1 <= len(files) <= 200:
            raise HTTPException(400, 'Envie de 1 a 200 arquivos.')
        inputs, size = [], 0
        try:
            for file in files:
                content = await read_upload(file, 55 * 1024 * 1024)
                extracted = xml_inputs(file.filename or '', content)
                inputs.extend(extracted)
                size += sum(len(raw) for _, raw in extracted)
                if len(inputs) > 5000 or size > 100 * 1024 * 1024:
                    raise ValueError('Lote excede os limites operacionais.')
            if not inputs:
                raise ValueError('Nenhum XML encontrado no lote.')
            from supreme_common.http_client import service_request
            for filename, raw in ([] if current_workspace.get() else inputs):
                try:
                    competence = NFSeNacionalParser.parse(raw, filename=filename).data_competencia.strftime('%Y-%m')
                except (ValueError, TypeError, KeyError):
                    competence = datetime.now(timezone.utc).strftime('%Y-%m')
                await service_request('documents', 'POST', '/documents/upload',
                    data={'company_id': context()['company_id'], 'competence': competence, 'department': 'fiscal'},
                    files={'file': (filename, raw, 'application/xml')})
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(ingest, inputs, mode, replace=bool(current_workspace.get()))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/load-samples')
    def samples():
        return ingest([(name, raw.strip().encode()) for name, raw in SAMPLE_FILES.items()],
                      'multi_layout_audit', replace=bool(current_workspace.get()))

    @app.get('/api/notes')
    def list_notes(search: str = '', status_conciliacao: str | None = None, retencao: str | None = None, municipio: str | None = None, limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0)):
        items = [n.model_dump(mode='json') for n in notes(active=False)]
        if search:
            items = [n for n in items if search.casefold() in json.dumps(n, ensure_ascii=False).casefold()]
        if status_conciliacao:
            items = [n for n in items if n['auditoria']['status_conciliacao'] == status_conciliacao]
        if retencao in {'com_retencao','sem_retencao'}:
            items = [n for n in items if (n['valor_total_retencoes'] > 0) == (retencao == 'com_retencao')]
        if municipio:
            items = [n for n in items if municipio.casefold() in (n['local_prestacao'] + n['local_incidencia']).casefold()]
        return items[offset:offset+limit]

    @app.get('/api/notes/{key}')
    def detail(key: str):
        with database() as db:
            schema(db)
            row = db.execute('SELECT note,canonical FROM notes WHERE key=?', (key,)).fetchone()
        if not row:
            raise HTTPException(404, 'Nota não encontrada.')
        return {**json.loads(row[0]), 'canonical': json.loads(row[1])}

    @app.get('/api/notes/{key}/xml')
    def download_xml(key: str):
        with database() as db:
            schema(db)
            row = db.execute('SELECT content FROM artifacts JOIN notes ON notes.sha=artifacts.sha WHERE notes.key=?', (key,)).fetchone()
        if not row:
            raise HTTPException(404, 'XML não encontrado.')
        return Response(row[0], media_type='application/xml')

    @app.delete('/api/notes/{key}')
    def remove_note(key: str):
        with database() as db:
            schema(db)
            row = db.execute('SELECT sha FROM notes WHERE key=?', (key,)).fetchone()
            if not row:
                raise HTTPException(404, 'Nota não encontrada.')
            db.execute('INSERT OR IGNORE INTO tombstones VALUES(?)', (key,))
        return ingest([], 'multi_layout_audit')

    @app.post('/api/notes/{key}/restore')
    def restore_note(key: str):
        with database() as db:
            schema(db)
            db.execute('DELETE FROM tombstones WHERE key=?',(key,))
        return ingest([], 'multi_layout_audit')

    @app.delete('/api/notes')
    def clear():
        return ingest([], 'multi_layout_audit', replace=True)

    @app.get('/api/retencoes')
    def retentions(competencia: str | None = None):
        return build_retention_report(notes(), competencia)

    @app.get('/api/dashboard/stats')
    def stats():
        # Reuse the existing KPI contract against a read-only note view.
        from .storage import JSONStorage
        class View:
            get_all_notes = staticmethod(notes)
        return JSONStorage.get_kpis_and_analytics(View())

    @app.get('/api/audit/findings')
    def findings():
        with database() as db:
            schema(db)
            row = db.execute("SELECT body FROM metadata WHERE key='audit'").fetchone()
        return json.loads(row[0]) if row else {'documents': [], 'issues': []}

    @app.get('/api/export/json')
    def export_json(version: str | None = None):
        with database() as db:
            schema(db)
            if not version:
                row = db.execute("SELECT body FROM metadata WHERE key='latest'").fetchone()
                version = json.loads(row[0]) if row else ''
            row = db.execute('SELECT body FROM snapshots WHERE version=?', (version,)).fetchone()
        if not row:
            if version:
                raise HTTPException(404,'Snapshot não encontrado neste contexto.')
            return {'metadata': {'total_notas': 0}, 'notas': []}
        return JSONResponse(json.loads(row[0]), headers={'Content-Disposition': 'attachment; filename=Consolidado_NFSe.json'})

    @app.get('/api/export/excel')
    def export_excel(mode: str = 'gerencial'):
        if mode == 'auditoria':
            with database() as db:
                schema(db)
                state = process_nfse_batch(db.execute('SELECT filename,content FROM artifacts').fetchall())
            content = generate_nfse_excel_report(state).getvalue()
        else:
            content = NFSeExporter.generate_excel(notes())
        return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=nfse.xlsx'})

    @app.get('/api/export/csv')
    def export_csv():
        return Response(NFSeExporter.generate_csv(notes()), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=nfse.csv'})

    return app

app = create_app()
