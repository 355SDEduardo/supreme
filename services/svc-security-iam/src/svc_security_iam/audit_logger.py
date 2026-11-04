"""Audit Logger service ensuring immutable append-only records and payload sanitization."""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from .models import AuditLog

# Keys that must be masked to prevent leaking sensitive information
SENSITIVE_KEYS = {"password", "token", "secret", "private_key", "key", "authorization", "pfx", "p12"}


def sanitize_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Recursively mask sensitive attributes in JSON payloads."""
    if not payload or not isinstance(payload, dict):
        return payload
    
    sanitized = {}
    for k, v in payload.items():
        if k.lower() in SENSITIVE_KEYS:
            sanitized[k] = "********"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_payload(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_payload(item) if isinstance(item, dict) else item for item in v]
        else:
            sanitized[k] = v
    return sanitized


def record_audit_log(
    db: Session,
    action: str,
    resource_type: str,
    ip_address: str,
    actor_user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    company_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    payload_snapshot: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Record an immutable audit log entry."""
    sanitized_snapshot = sanitize_payload(payload_snapshot)
    log_entry = AuditLog(
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        company_id=company_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload_snapshot=sanitized_snapshot,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry


def query_audit_logs(
    db: Session,
    organization_id: Optional[str] = None,
    company_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[AuditLog]:
    """Retrieve audit logs with filtering and pagination."""
    query = db.query(AuditLog)
    if organization_id:
        query = query.filter(AuditLog.organization_id == organization_id)
    if company_id:
        query = query.filter(AuditLog.company_id == company_id)
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if action:
        query = query.filter(AuditLog.action == action)
        
    return query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
