import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record_audit(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    club_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(AuditLog(
        actor_id=actor_id,
        club_id=club_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details or {},
    ))
