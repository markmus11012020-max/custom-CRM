"""Общие зависимости API."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.services.access import (
    accessible_projects,
    get_project_for_user,
    require_project_edit,
)
from app.services.auth import get_current_user


def resolve_project(
    request: Request,
    db: Session,
    user: User,
    project_id: int | None = None,
) -> Project:
    if project_id is not None:
        return get_project_for_user(db, project_id, user)
    active_id = request.session.get("active_project_id")
    if active_id:
        try:
            return get_project_for_user(db, int(active_id), user)
        except Exception:  # noqa: BLE001
            pass
    projects = accessible_projects(db, user)
    if not projects:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="Нет доступных проектов")
    request.session["active_project_id"] = projects[0].id
    return projects[0]


def require_edit(db: Session, project: Project, user: User) -> None:
    require_project_edit(db, project.id, user)


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
    ) -> None:
        self.page = page
        self.per_page = per_page


def paginate(db: Session, query: Select, params: PageParams) -> tuple[list[Any], int]:
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int(db.scalar(count_query) or 0)
    items = list(
        db.scalars(query.offset((params.page - 1) * params.per_page).limit(params.per_page))
    )
    return items, total


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends()]
