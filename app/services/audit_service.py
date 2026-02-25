import uuid, json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog

def log_audit(db: Session, actor_user_id: str, action: str, entity_type: str, entity_id: str, details: dict | None = None):
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=json.dumps(details or {}, ensure_ascii=False),
    ))
