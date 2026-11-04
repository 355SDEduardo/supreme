from sqlalchemy import Column, String
from supreme_common.events import start_consumer, stop_consumer
from .database import Base

class PortfolioResource(Base):
    __tablename__ = 'portfolio_resources'
    id = Column(String(200), primary_key=True)
    company_id = Column(String(100), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False)
    competence = Column(String(7), nullable=True)

async def start(app):
    async def changed(event):
        data = event.payload['resource']
        kinds={'TaskChanged':'task','ChecklistItemChanged':'document','BankTransactionChanged':'bank'}
        kind=kinds[event.event_type]
        identity=event.organization_id+':'+event.company_id+':'+kind+':'+data['id']
        with app.state.sessions() as db:
            row=db.query(PortfolioResource).filter(PortfolioResource.id==identity).first()
            if not row:
                row=PortfolioResource(id=identity,company_id=event.company_id,kind=kind)
                db.add(row)
            row.status=('fulfilled' if data['is_fulfilled'] else 'pending') if kind=='document' else data['status']
            row.competence=data.get('competence')
            db.commit()
    start_consumer(app,'companies',{'TaskChanged':changed,'ChecklistItemChanged':changed,'BankTransactionChanged':changed})

async def stop(app):
    await stop_consumer(app)
