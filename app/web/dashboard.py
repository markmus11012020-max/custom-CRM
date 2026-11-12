"""Дашборд, переключение проектов и поиск."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.models import Client, Deal, Task
from app.services.access import accessible_project_ids, get_active_project, set_active_project
from app.services.accounting import monthly_series
from app.services.activity import recent_activity
from app.services.dashboard import (
    funnel,
    open_tasks,
    project_stats,
    recent_clients,
    recent_deals,
)
from app.services.stock import low_stock_products
from app.web.utils import flash, render

router = APIRouter(tags=["web-dashboard"])


@router.get("/")
def dashboard(request: Request, db: DbSession, user: CurrentUser):
    project = get_active_project(request, db, user)
    stats = project_stats(db, project.id)
    return render(
        request,
        "dashboard.html",
        db,
        user,
        active_project=project,
        stats=stats,
        funnel=funnel(db, project.id),
        tasks=open_tasks(db, project.id),
        deals=recent_deals(db, project.id),
        clients=recent_clients(db, project.id),
        activity=recent_activity(db, project.id),
        low_stock=low_stock_products(db, project.id, limit=5),
        monthly=monthly_series(db, project.id),
    )


@router.post("/project/switch")
def switch_project(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    project_id: int = Form(...),
    next: str = Form("/"),
):
    try:
        set_active_project(request, db, user, project_id)
        flash(request, "Активный проект переключён")
    except Exception as exc:  # noqa: BLE001
        flash(request, str(exc), "error")
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    return RedirectResponse(next, status_code=303)


@router.get("/search")
def search_page(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    all_projects: bool = False,
):
    project = get_active_project(request, db, user)
    term = q.strip().casefold()
    clients: list[Client] = []
    deals: list[Deal] = []
    tasks: list[Task] = []
    if term:
        like = f"%{term}%"
        project_ids = accessible_project_ids(db, user) if all_projects else [project.id]
        clients = list(
            db.scalars(
                select(Client)
                .where(Client.project_id.in_(project_ids), or_(Client.search_text.like(like), Client.name.ilike(like)))
                .order_by(Client.name)
                .limit(50)
            )
        )
        deals = list(
            db.scalars(
                select(Deal)
                .where(Deal.project_id.in_(project_ids), Deal.search_text.like(like))
                .order_by(Deal.created_at.desc())
                .limit(50)
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
                        Task.search_text.like(like),
                        Client.name.ilike(like),
                        Deal.title.ilike(like),
                    ),
                )
                .order_by(Task.due_at.is_(None), Task.due_at)
                .limit(50)
            )
        )
    return render(
        request,
        "search.html",
        db,
        user,
        active_project=project,
        q=q,
        all_projects=all_projects,
        clients=clients,
        deals=deals,
        tasks=tasks,
    )
