from supreme_common.events import start_consumer, stop_consumer
from .audit_logger import record_audit_log
from .models import AuditLog

async def start(app):
    async def audit(event):
        with app.state.sessions() as db:
            if db.query(AuditLog).filter(AuditLog.resource_id == event.event_id).first():
                return
            record_audit_log(db, actor_user_id=event.actor_user_id, company_id=event.company_id or None,
                action=event.payload.get('action',event.event_type), resource_type='http_request',resource_id=event.event_id,
                ip_address=event.payload.get('ip_address','internal'), payload_snapshot=event.payload)
    start_consumer(app, 'security-audit', {'AuditLogRecorded':audit})

async def stop(app):
    await stop_consumer(app)
