"""Глобальный поиск по CRM."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession, resolve_project
from app.models import Client, Deal, Task
from app.services.access import accessible_project_ids

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    q: str = Query(default="", max_length=255),
    project_id: int | None = None,
    all_projects: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
):
    query = q.strip().casefold()
    if not query:
        return {"query": "", "clients": [], "deals": [], "tasks": []}
    term = f"%{query}%"
    if all_projects:
        project_ids = accessible_project_ids(db, user)
    else:
        project = resolve_project(request, db, user, project_id)
        project_ids = [project.id]

    clients = list(
        db.scalars(
            select(Client)
            .where(
                Client.project_id.in_(project_ids),
                or_(Client.search_text.like(term), Client.name.ilike(term)),
            )
            .order_by(Client.name)
            .limit(limit)
        )
    )
    deals = list(
        db.scalars(
            select(Deal)
            .where(Deal.project_id.in_(project_ids), Deal.search_text.like(term))
            .order_by(Deal.created_at.desc())
            .limit(limit)
        )
    )
    tasks = list(
        db.scalars(
            select(Task)
            .outerjoin(Client, Task.client_id == Client.id)
            .outerjoin(Deal, Task.deal_id == Deal.id)
            .where(
                Task.project_id.in_(project_ids),
                or_(
                    Task.search_text.like(term),
                    Client.name.ilike(term),
                    Deal.title.ilike(term),
                ),
            )
            .order_by(Task.due_at.is_(None), Task.due_at)
            .limit(limit)
        )
    )
    return {
        "query": q,
        "clients": [
            {"id": item.id, "name": item.name, "company": item.company, "status": item.status}
            for item in clients
        ],
        "deals": [
            {"id": item.id, "title": item.title, "stage": item.stage, "amount": str(item.amount)}
            for item in deals
        ],
        "tasks": [
            {
                "id": item.id,
                "title": item.title,
                "is_completed": item.is_completed,
                "due_at": item.due_at.isoformat() if item.due_at else None,
            }
            for item in tasks
        ],
    }
