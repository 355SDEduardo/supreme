from decimal import Decimal
from supreme_common.events import start_consumer, stop_consumer
from .service import generate_classification_suggestion
from .models import AiClassificationSuggestion

async def start(app):
    async def reconciled(event):
        with app.state.sessions() as db:
            transaction_id = event.payload['transaction_id']
            if db.query(AiClassificationSuggestion).filter(AiClassificationSuggestion.transaction_id == transaction_id).first():
                return
            generate_classification_suggestion(db, company_id=event.company_id,
                description_or_memo=event.payload.get('memo') or 'Conciliação bancária',
                amount=Decimal(event.payload['amount']), transaction_id=transaction_id, document_id=None)
    start_consumer(app, 'accounting-ai', {'TransactionReconciled': reconciled})

async def stop(app):
    await stop_consumer(app)
