import json
from supreme_common.http_client import service_request
from supreme_common.events import start_consumer, stop_consumer

async def nfse_processed(event):
    from .app import save_input, reload_snapshot
    response = await service_request('nfse-engine', 'GET', event.payload['snapshot_uri'])
    import asyncio
    await asyncio.to_thread(save_input, 'notas/Consolidado_NFSe.json', json.dumps(response.json()).encode('utf-8'))
    await asyncio.to_thread(reload_snapshot)

async def start(app):
    start_consumer(app, 'federal-tax-audit', {'NFSeBatchProcessed': nfse_processed})

async def stop(app):
    await stop_consumer(app)
