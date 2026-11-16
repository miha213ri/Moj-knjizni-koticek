"""Pomožne funkcije za revizijsko sledenje in beleženje pomembnih sistemskih dogodkov."""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from app.models import AuditLog

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    action: str,
    user_id: int | None = None,
    location_id: int | None = None,
    entity: str | None = None,
    entity_id: int | None = None,
    details: str | None = None,
) -> AuditLog | None:
    """Zapiše dogodek v revizijski dnevnik (Audit Log)."""
    try:
        entry = AuditLog(
            action=action.strip()[:100],
            user_id=user_id,
            location_id=location_id,
            entity=entity.strip()[:100] if entity else None,
            entity_id=entity_id,
            details=details,
        )
        db.add(entry)
        db.flush()
        return entry
    except Exception as exc:
        logger.warning("Neuspešno beleženje revizijskega dogodka %r: %s", action, exc)
        return None
