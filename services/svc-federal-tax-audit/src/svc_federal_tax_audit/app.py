"""Company-partitioned federal audit API; no source documents are loaded at import."""
from pathlib import Path
from datetime import date
import json
import os
import uuid
from fastapi import Depends, FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from supreme_common.auth_context import AuthMiddleware, context, enforce_request_context, tenant_path
from supreme_common.events import publish
from supreme_common.state import tenant_database
from supreme_common.uploads import RequestLimitMiddleware, read_upload
from .engine import FederalTaxAuditEngine
from .tools.agent_tools import FederalTaxAuditTools

def workspace():
    return tenant_path(os.getenv('TAX_AUDIT_WORKSPACES_DIR', './data/storage/tax_audit'))

class SimulationRequest(BaseModel):
    presuncao_pct: float = Field(32, ge=1, le=100, allow_inf_nan=False)
    multa_oficio_pct: float = Field(75, ge=0, le=150, allow_inf_nan=False)
    taxa_selic_pct: float = Field(9.5, ge=0, le=100, allow_inf_nan=False)
    base_calculo_custom: float | None = Field(None, ge=0, allow_inf_nan=False)

def reload_snapshot():
    engine = FederalTaxAuditEngine(str(workspace()))
    engine.load_all()
    result = engine.run_full_audit()
    # The original prototype contains one customer's static headings. Derive them
    # from the uploaded dataset instead, including when no documents exist.
    issuer = next((n.get('emitente') or {} for n in engine.nfse_data if n.get('emitente')), {})
    result['empresa'] = {'razao_social': issuer.get('razao_social', context()['company_id']),
        'cnpj': issuer.get('cnpj', ''), 'regime_tributario': 'Conferir no cadastro da empresa',
        'atividades': 'Conforme documentos fornecidos', 'periodo_auditado': 'Conforme competências importadas'}
    # Findings from the old prototype mention fixed invoice numbers/customer data.
    # Publish only evidence from this tenant's actual reconciliation.
    findings = []
    absent = result.get('notas_ausentes_no_livro', {})
    if absent.get('quantidade'):
        findings.append({'id': 'DOCUMENT_RECONCILIATION', 'severidade': 'WARNING',
            'titulo': 'Notas pendentes de conciliação com o livro fornecido',
            'quantidade': absent['quantidade'], 'impacto_financeiro': absent.get('valor_total', 0),
            'descricao': 'Ausência no conjunto fornecido exige conferência documental; não prova omissão fiscal.'})
    if not engine.nfse_data:
        findings.append({'id': 'MISSING_PRIMARY_DATA', 'severidade': 'WARNING', 'titulo': 'Sem notas fiscais primárias', 'impacto_financeiro': 0})
    for error in engine.extraction_errors:
        findings.append({'id': 'EXTRACTION_ERROR', 'severidade': 'WARNING', 'titulo': error, 'impacto_financeiro': 0})
    result['achados_auditoria'] = findings
    version = str(uuid.uuid4())
    snapshot = {'version': version, 'result': result, 'notes': engine.nfse_data,
                'documents': engine.document_catalog, 'darfs': engine.darfs_data}
    with tenant_database('tax_audit') as db:
        db.execute('CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT)')
        db.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?)', (json.dumps(snapshot, default=str),))
    publish('FederalTaxAuditCompleted', {'snapshot_version': version, 'total_findings': len(findings)})
    return snapshot

def snapshot():
    with tenant_database('tax_audit') as db:
        db.execute('CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT)')
        row = db.execute('SELECT body FROM snapshot WHERE id=1').fetchone()
    return json.loads(row[0]) if row else reload_snapshot()

def create_app():
    from contextlib import asynccontextmanager
    from .events import start, stop
    @asynccontextmanager
    async def lifespan(app):
        from supreme_common.auth_context import secret_key
        secret_key()
        await start(app)
        yield
        await stop(app)
    app = FastAPI(title='svc-federal-tax-audit', lifespan=lifespan, dependencies=[Depends(enforce_request_context)])
    app.add_middleware(RequestLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    @app.get('/health')
    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'service': 'svc-federal-tax-audit'}

    @app.post('/api/reload')
    def reload():
        return {'status': 'success', 'snapshot_version': reload_snapshot()['version']}

    @app.post('/api/nfse/import')
    def import_nfse(data: dict):
        if not isinstance(data.get('notas'), list):
            raise HTTPException(422, 'Informe um JSON consolidado com a lista notas.')
        target = workspace() / 'notas'
        target.mkdir(exist_ok=True)
        temporary = target / (str(uuid.uuid4()) + '.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temporary.replace(target / 'Consolidado_NFSe.json')
        return {'snapshot_version': reload_snapshot()['version']}

    @app.post('/api/documents/upload')
    async def upload(file: UploadFile = File(...)):
        name = Path(file.filename or '').name
        import re
        if not re.fullmatch(r'(?:PIS \d{2}-\d{4}|COFINS \d{2}-\d{4}|IRPJ|CSLL|Serviços|comprovantes)\.pdf', name):
            raise HTTPException(400, 'Nome de demonstrativo não reconhecido; consulte o README.')
        content = await read_upload(file, 30*1024*1024)
        if not content.startswith(b'%PDF-'):
            raise HTTPException(400, 'PDF inválido.')
        (workspace() / name).write_bytes(content)
        return {'snapshot_version': reload_snapshot()['version']}

    class LedgerPeriod(BaseModel):
        ledger_start: date
        ledger_end: date

    @app.put('/api/ledger/period')
    def ledger_period(payload: LedgerPeriod):
        from datetime import date
        start, end = payload.ledger_start, payload.ledger_end
        if start > end:
            raise HTTPException(422,'Período do livro inválido.')
        (workspace()/'audit_config.json').write_text(payload.model_dump_json(),encoding='utf-8')
        return {'snapshot_version':reload_snapshot()['version']}

    @app.get('/api/audit')
    def audit():
        return snapshot()['result']

    @app.get('/api/documents')
    def documents():
        data = snapshot()
        return {'snapshot_version': data['version'], 'documentos': data['documents'], 'total': len(data['documents'])}

    @app.get('/api/nfse')
    def nfse(competencia: str | None = None, search: str = '', busca: str = '', apenas_omitidas: bool = False, com_retencao: bool = False):
        data = snapshot()
        items = data['notes']
        total_base = len(items)
        if competencia:
            items = [n for n in items if n.get('competencia_normalizada') == competencia or str(n.get('data_competencia','')).startswith(competencia)]
        if search or busca:
            items = [n for n in items if (search or busca).casefold() in json.dumps(n, ensure_ascii=False).casefold()]
        if apenas_omitidas:
            items = [n for n in items if n.get('situacao_livro', '').startswith('NAO_LOCALIZADA')]
        if com_retencao:
            items = [n for n in items if any(float(n.get('retencoes',{}).get(k,0)) > 0 for k in ('inss','irrf','iss','csll','pis','cofins'))]
        result=[]
        for item in items:
            company=item.get('tomador') or {}
            result.append({**item,'tomador':company.get('razao_social',''), 'cnpj_tomador':company.get('cnpj',''),
                'data_competencia':item.get('data_competencia_iso'), 'competencia_mes':item.get('competencia_canonica'),
                'data_emissao':item.get('data_emissao_iso'),'municipio_prestacao':item.get('local_prestacao')})
        return {'snapshot_version':data['version'],'notas':result,'total':len(result),'total_filtrado':len(result),'total_base':total_base}

    @app.get('/api/crosscheck/monthly')
    def monthly():
        result = snapshot()['result']
        return result.get('cruzamento_mensal_pis_cofins', [])

    @app.get('/api/crosscheck/quarterly')
    def quarterly():
        result = snapshot()['result']
        return result.get('cruzamento_trimestral_irpj_csll', [])

    @app.get('/api/darfs')
    def darfs():
        data=snapshot()
        return {'snapshot_version':data['version'],'total_itens':len(data['darfs']),
            'total_arrecadado':data['result'].get('total_arrecadado_darfs',0),
            'resumo_por_tributo':data['result'].get('resumo_darfs_pagos',{}),'comprovantes':data['darfs']}

    @app.post('/api/simulate')
    def simulate(payload: SimulationRequest):
        return FederalTaxAuditTools(str(workspace())).simulate_tax_scenario(**payload.model_dump())

    @app.get('/api/report/markdown')
    def markdown():
        data = snapshot()
        result = data['result']
        lines = ['# Relatório preliminar de conciliação fiscal',
            f"Empresa: {result['empresa']['razao_social']}", f"Snapshot: {data['version']}",
            'A análise depende dos documentos fornecidos e exige revisão do contador responsável.',
            '## Resumo', '```json', json.dumps(result['resumo_faturamento'], ensure_ascii=False, indent=2), '```',
            '## Apontamentos']
        lines.extend('- ' + item['titulo'] for item in result['achados_auditoria'])
        return {'markdown': '\n\n'.join(lines)}

    return app

app = create_app()
