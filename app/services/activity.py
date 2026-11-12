"""Журнал действий пользователей."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityLog, User


def log_activity(
    db: Session,
    *,
    action: str,
    entity_type: str = "",
    entity_id: int | None = None,
    project_id: int | None = None,
    user_id: int | None = None,
    details: str = "",
) -> ActivityLog:
    entry = ActivityLog(
        project_id=project_id,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        details=details[:4000],
    )
    db.add(entry)
    return entry


def recent_activity(db: Session, project_id: int, limit: int = 20) -> list[ActivityLog]:
    return list(
        db.scalars(
            select(ActivityLog)
            .where(ActivityLog.project_id == project_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
        )
    )


def activity_for_entity(
    db: Session, entity_type: str, entity_id: int, limit: int = 30
) -> list[ActivityLog]:
    return list(
        db.scalars(
            select(ActivityLog)
            .where(ActivityLog.entity_type == entity_type, ActivityLog.entity_id == entity_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
        )
    )


def user_display(user: User | None) -> str:
    if user is None:
        return "Система"
    return user.full_name or user.email
