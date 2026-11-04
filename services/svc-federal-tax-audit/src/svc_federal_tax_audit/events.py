import json
from supreme_common.http_client import service_request
from supreme_common.events import start_consumer, stop_consumer

async def nfse_processed(event):
    from .app import workspace, reload_snapshot
    response = await service_request('nfse-engine', 'GET', event.payload['snapshot_uri'])
    path = workspace() / 'notas'
    path.mkdir(exist_ok=True)
    target = path / 'Consolidado_NFSe.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(response.json()), encoding='utf-8')
    temporary.replace(target)
    import asyncio
    await asyncio.to_thread(reload_snapshot)

async def start(app):
    start_consumer(app, 'federal-tax-audit', {'NFSeBatchProcessed': nfse_processed})

async def stop(app):
    await stop_consumer(app)
