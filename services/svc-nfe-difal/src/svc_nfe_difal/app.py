"""FastAPI transport over the preserved NF-e/ZIP comparison domain."""
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
import json
import os
import time
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from supreme_common.auth_context import AuthMiddleware, context, enforce_request_context, tenant_path
from supreme_common.events import publish
from supreme_common.state import tenant_database
from supreme_common.uploads import RequestLimitMiddleware, read_upload
from .core.models import NfeData, NfeProduct, ParseIssue
from .core.nfe_parser import NfeParser
from .core.zip_extractor import extract_xmls_from_zip
from .core.zip_comparison import compare_nfe_zips
from .core.ncm_comparison import compare_nfes, load_fiscal_catalog
from .core.fiscal_registration import FiscalRegistration, FiscalRegistrationService
from .core.document_comparison import compare_products_to_pdf, text_report
from .core import reporting as reports

def catalog_path():
    root = Path(os.getenv('NFE_FISCAL_CATALOG_PATH', './data/storage/nfe/fiscal_data.json'))
    return tenant_path(root.parent) / root.name

def state_key():
    claims = context()
    return claims['sub'] + ':' + claims.get('session_id', claims['jti'])

def state_read():
    with tenant_database('nfe') as db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, expires REAL, body TEXT)')
        db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        row = db.execute('SELECT body FROM sessions WHERE sid=?', (state_key(),)).fetchone()
    return json.loads(row[0]) if row else {}

def state_write(data):
    with tenant_database('nfe') as db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, expires REAL, body TEXT)')
        db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        if db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] >= 100 and not db.execute('SELECT 1 FROM sessions WHERE sid=?', (state_key(),)).fetchone():
            raise HTTPException(503, 'Limite de sess?es ativas atingido; tente ap?s a expira??o.')
        db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?)',
            (state_key(), time.time() + int(os.getenv('STATE_TTL_SECONDS', '7200')), json.dumps(data)))

def current_notes():
    result = []
    for raw in state_read().get('nfes', []):
        note = dict(raw)
        note['produtos'] = [NfeProduct(**p) for p in raw['produtos']]
        result.append(NfeData(**note))
    if not result:
        raise HTTPException(404, 'Processe notas nesta sessão antes de continuar.')
    return result

def download(content, filename, media='application/json'):
    return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename={filename}'})

class Destination(BaseModel):
    note_index: int = Field(ge=0)
    product_index: int = Field(ge=0)
    destination: str = Field(pattern='^(Comercialização|Uso e Consumo|Imobilizado)$')
    apply_same_ncm: bool = False

def create_app():
    from contextlib import asynccontextmanager
    from supreme_common.auth_context import secret_key
    @asynccontextmanager
    async def lifespan(app):
        secret_key()
        yield
    app = FastAPI(title='svc-nfe-difal', lifespan=lifespan, dependencies=[Depends(enforce_request_context)])
    app.add_middleware(RequestLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.get('/health')
    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'service': 'svc-nfe-difal'}

    @app.post('/nfe/process')
    async def process(files: list[UploadFile] = File(...)):
        if not 1 <= len(files) <= 200:
            raise HTTPException(400, 'Envie de 1 a 200 arquivos XML/ZIP.')
        notes, issues, total = [], [], 0
        parser = NfeParser()
        for upload in files:
            name = Path(upload.filename or '').name
            if name.lower().endswith('.zip'):
                extracted = extract_xmls_from_zip(BytesIO(await read_upload(upload, 55*1024*1024)), zip_filename=name,
                    max_entries=500, max_xml_bytes=5*1024*1024, max_total_bytes=100*1024*1024-total)
                inputs = extracted.xml_files
                issues.extend(asdict(issue) for issue in extracted.issues)
            elif name.lower().endswith('.xml'):
                inputs = [(name, await read_upload(upload, 5*1024*1024))]
            else:
                raise HTTPException(400, 'Envie XML ou ZIP.')
            for filename, content in inputs:
                total += len(content)
                if total > 100*1024*1024:
                    raise HTTPException(413, 'Lote excede 100 MB descompactados.')
                try:
                    notes.append(parser.parse_bytes(content, filename))
                except ValueError as exc:
                    issues.append({'filename': filename, 'message': str(exc)})
        catalog = load_fiscal_catalog(catalog_path()) if catalog_path().exists() else {}
        comparison, summary = compare_nfes(notes, catalog)
        state = state_read()
        state.update(nfes=[asdict(n) for n in notes], issues=issues,
                     comparison=[i.to_dict() for i in comparison], comparison_summary=asdict(summary))
        state_write(state)
        publish('NFeBatchProcessed', {'total_notes': len(notes), 'total_products': sum(len(n.produtos) for n in notes)})
        return {**reports.report_payload(notes, [ParseIssue(**i) for i in issues]), 'comparison': state['comparison']}

    @app.get('/nfe/state')
    def get_state():
        return state_read()

    @app.delete('/nfe/state')
    def clear():
        state_write({})
        return {'status': 'cleared'}

    @app.post('/nfe/products/destination')
    def destination(payload: Destination):
        notes = current_notes()
        try:
            product = notes[payload.note_index].produtos[payload.product_index]
        except IndexError:
            raise HTTPException(404, 'Item não encontrado.')
        for i, note in enumerate(notes):
            for j, candidate in enumerate(note.produtos):
                if (i,j) == (payload.note_index, payload.product_index) or (payload.apply_same_ncm and product.ncm and candidate.ncm == product.ncm):
                    candidate.destinacao = payload.destination
        state = state_read()
        state['nfes'] = [asdict(n) for n in notes]
        state_write(state)
        return {'status': 'updated'}

    @app.post('/nfe/compare-ncm')
    def compare_ncm():
        items, summary = compare_nfes(current_notes(), load_fiscal_catalog(catalog_path()) if catalog_path().exists() else {})
        state = state_read()
        state.update(comparison=[item.to_dict() for item in items], comparison_summary=asdict(summary))
        state_write(state)
        return state['comparison']

    @app.post('/nfe/fiscal-catalog/import')
    async def import_catalog(file: UploadFile = File(...)):
        return {'count': FiscalRegistrationService().replace(catalog_path(), await read_upload(file, 10*1024*1024))}

    @app.post('/nfe/fiscal-catalog/items')
    async def add_catalog(request: Request):
        return {'count': FiscalRegistrationService().add(catalog_path(), FiscalRegistration(**(await request.json())))}

    @app.post('/nfe/compare-zips')
    async def zips(zip_cliente: UploadFile = File(...), zip_portal: UploadFile = File(...)):
        if not all((f.filename or '').lower().endswith('.zip') for f in (zip_cliente, zip_portal)):
            raise HTTPException(400, 'Envie dois arquivos ZIP.')
        result = compare_nfe_zips(BytesIO(await read_upload(zip_cliente, 55*1024*1024)),
            BytesIO(await read_upload(zip_portal, 55*1024*1024)), nome_cliente=Path(zip_cliente.filename).name, nome_portal=Path(zip_portal.filename).name)
        state = state_read()
        state['zip'] = reports.zip_comparison_payload(result)
        # Store primitive JSON; exports reconstruct dataclasses, never unpickle untrusted state.
        state_write(state)
        return state['zip']

    @app.post('/nfe/compare-documents')
    async def documents(txt_file: UploadFile = File(...), pdf_file: UploadFile = File(...)):
        result = compare_products_to_pdf(await read_upload(txt_file, 2*1024*1024), await read_upload(pdf_file,30*1024*1024),
            txt_filename=Path(txt_file.filename or 'produtos.txt').name, pdf_filename=Path(pdf_file.filename or 'relatorio.pdf').name)
        state = state_read()
        state['document'] = result
        state_write(state)
        return result

    @app.get('/nfe/export/report.json')
    def report_json():
        return download(reports.json_download(reports.report_payload(current_notes())), 'relatorio.json')

    @app.get('/nfe/export/report.xlsx')
    def report_excel():
        return download(reports.excel_download(current_notes()), 'relatorio.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.get('/nfe/export/ncm-comparison.json')
    def ncm_json():
        return state_read().get('comparison', [])

    @app.get('/nfe/export/csv/{dataset}')
    def csv_export(dataset: str):
        notes = current_notes()
        if dataset == 'notas':
            rows = reports.note_rows(notes)
        elif dataset == 'produtos':
            rows = reports.product_rows(notes)
        elif dataset in {'cfop','cst'}:
            rows = reports.aggregate_rows(notes, dataset)
        elif dataset == 'comparacao':
            rows = state_read().get('comparison', [])
        else:
            raise HTTPException(404, 'Dataset não encontrado.')
        columns = [(key, key) for key in rows[0]] if rows else [('numero','Número')]
        return download(reports.csv_download(rows, columns), dataset+'.csv', 'text/csv')

    @app.get('/nfe/export/zip-comparison.json')
    def zip_json():
        return state_read().get('zip', {})

    def zip_result():
        from .core.models import ZipComparisonResult, ReconciliationNote, ReconciliationDivergence, ReconciliationSummary
        data = dict(state_read().get('zip') or {})
        if not data:
            raise HTTPException(404, 'Compare os pacotes antes de exportar.')
        for field in ('apenas_cliente','apenas_portal','em_ambos','em_ambos_portal'):
            data[field] = [ReconciliationNote(**row) for row in data.get(field, [])]
        data['resumo'] = ReconciliationSummary(**data['resumo'])
        for field in ('issues_cliente','issues_portal'):
            data[field] = [ParseIssue(**row) for row in data.get(field, [])]
        data['divergencias'] = [ReconciliationDivergence(**{**row, 'nota_cliente': ReconciliationNote(**row['nota_cliente']),
            'nota_portal': ReconciliationNote(**row['nota_portal'])}) for row in data.get('divergencias', [])]
        return ZipComparisonResult(**data)

    @app.get('/nfe/export/zip-comparison.xlsx')
    def zip_excel():
        return download(reports.zip_comparison_excel(zip_result()), 'conciliacao.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.get('/nfe/export/zip-comparison/{group}.csv')
    def zip_csv(group: str):
        result = zip_result()
        if group == 'divergencias':
            content = reports.zip_comparison_divergences_csv(result.divergencias)
        elif group in {'apenas-cliente','apenas-portal','em-ambos'}:
            content = reports.zip_comparison_csv(getattr(result, group.replace('-','_')))
        else:
            raise HTTPException(404, 'Grupo inválido.')
        return download(content, group+'.csv', 'text/csv')

    @app.get('/nfe/export/document-comparison.{format}')
    def document_export(format: str):
        result = state_read().get('document')
        if not result or format not in {'json','txt'}:
            raise HTTPException(404, 'Comparação não encontrada.')
        return download(reports.json_download(result) if format == 'json' else text_report(result), 'comparacao.'+format,
                        'application/json' if format == 'json' else 'text/plain')

    return app

app = create_app()
