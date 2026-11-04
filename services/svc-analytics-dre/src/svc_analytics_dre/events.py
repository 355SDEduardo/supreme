from datetime import date
from decimal import Decimal
from supreme_common.events import start_consumer, stop_consumer
from .projections import BillProjection, AccountProjection, ConsumedEvent

async def start(app):
    async def bill_changed(event):
        data = event.payload['resource']
        with app.state.sessions() as db:
            if db.query(ConsumedEvent).filter(ConsumedEvent.id == event.event_id).first():
                return
            row = db.query(BillProjection).filter(BillProjection.id == data['id']).first()
            if row is None:
                row = BillProjection(id=data['id'], company_id=event.company_id)
                db.add(row)
            row.type, row.status = data['type'], data['status']
            row.category, row.amount = data.get('category_id'), Decimal(data['final_amount'])
            for field in ('issue_date','due_date','payment_date'):
                setattr(row, field, date.fromisoformat(data[field]) if data.get(field) else None)
            db.add(ConsumedEvent(id=event.event_id))
            db.commit()
    async def statement(event):
        data = event.payload['resource']
        with app.state.sessions() as db:
            row = db.query(AccountProjection).filter(AccountProjection.id == data['bank_account_id']).first()
            when = date.fromisoformat(data['period_end'])
            if row and row.as_of > when:
                return
            if row is None:
                row = AccountProjection(id=data['bank_account_id'], company_id=event.company_id)
                db.add(row)
            row.balance, row.as_of = Decimal(data['closing_balance']), when
            db.commit()
    start_consumer(app, 'analytics-dre', {'BillChanged': bill_changed, 'BankStatementImported': statement})

async def stop(app):
    await stop_consumer(app)
