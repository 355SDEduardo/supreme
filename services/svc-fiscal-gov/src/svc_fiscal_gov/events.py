import json
from collections import defaultdict
from decimal import Decimal
from supreme_common.events import start_consumer, stop_consumer
from supreme_common.http_client import service_request
from .integration import RetentionProjection

async def start(app):
    async def nfse(event):
        response = await service_request('nfse-engine', 'GET', event.payload['snapshot_uri'])
        totals = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
        for note in response.json()['notas']:
            competence = note['data_competencia'][:7]
            for key, value in note.get('retencoes', {}).items():
                totals[competence][key] += Decimal(str(value))
        with app.state.sessions() as db:
            for old in db.query(RetentionProjection).all():
                db.delete(old)
            for competence, values in totals.items():
                db.add(RetentionProjection(id=event.organization_id+':'+event.company_id+':'+competence, totals=json.dumps(values, default=str), source_version=event.payload['snapshot_version']))
            db.commit()
    start_consumer(app, 'fiscal-gov', {'NFSeBatchProcessed': nfse})

async def stop(app):
    await stop_consumer(app)
