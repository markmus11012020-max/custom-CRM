"""Веб-раздел задач."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models import Client, Deal, Task, User
from app.services.access import get_active_project, get_project_for_user, require_project_edit
from app.services.activity import log_activity
from app.web.utils import flash, render

router = APIRouter(prefix="/tasks", tags=["web-tasks"])
PER_PAGE = 30


@router.get("")
def list_tasks(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    bucket: str = "",
    assigned_to: str = "",
    completed: bool = False,
    page: int = 1,
):
    project = get_active_project(request, db, user)
    query = (
        select(Task)
        .outerjoin(Client, Task.client_id == Client.id)
        .outerjoin(Deal, Task.deal_id == Deal.id)
        .where(Task.project_id == project.id, Task.is_completed.is_(completed))
    )
    if q.strip():
        term = f"%{q.strip().casefold()}%"
        query = query.where(
            or_(
                Task.search_text.like(term),
                Task.title.ilike(term),
                Client.name.ilike(term),
                Deal.title.ilike(term),
            )
        )
    if assigned_to.isdigit():
        query = query.where(Task.assigned_to_id == int(assigned_to))
    now = datetime.now(UTC)
    if bucket == "overdue":
        query = query.where(Task.due_at < now)
    elif bucket == "today":
        start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        query = query.where(Task.due_at >= start, Task.due_at < start + timedelta(days=1))
    elif bucket == "future":
        query = query.where(Task.due_at >= now + timedelta(days=1))
    elif bucket == "none":
        query = query.where(Task.due_at.is_(None))
    total = len(list(db.scalars(query)))
    tasks = list(
        db.scalars(
            query.options(selectinload(Task.client), selectinload(Task.deal), selectinload(Task.assigned_to))
            .order_by(Task.due_at.is_(None), Task.due_at, Task.priority.desc())
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
        )
    )
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "tasks/list.html",
        db,
        user,
        active_project=project,
        tasks=tasks,
        users=users,
        total=total,
        page=page,
        per_page=PER_PAGE,
        q=q,
        bucket=bucket,
        assigned_to=assigned_to,
        completed=completed,
    )


@router.get("/new")
def new_task(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    client_id: int | None = None,
    deal_id: int | None = None,
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    clients = list(
        db.scalars(
            select(Client)
            .where(Client.project_id == project.id, Client.is_archived.is_(False))
            .order_by(Client.name)
        )
    )
    deals = list(
        db.scalars(
            select(Deal).where(Deal.project_id == project.id).order_by(Deal.created_at.desc()).limit(200)
        )
    )
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "tasks/form.html",
        db,
        user,
        active_project=project,
        task=None,
        clients=clients,
        deals=deals,
        users=users,
        selected_client_id=client_id,
        selected_deal_id=deal_id,
        form_action="/tasks/new",
        title="Новая задача",
    )


@router.post("/new")
def create_task(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    title: str = Form(""),
    description: str = Form(""),
    client_id: str = Form(""),
    deal_id: str = Form(""),
    due_date: str = Form(""),
    priority: str = Form("normal"),
    assigned_to: str = Form(""),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    if not title.strip():
        flash(request, "Название задачи обязательно", "error")
        return RedirectResponse("/tasks/new", status_code=303)
    due_at = None
    if due_date:
        try:
            due_at = datetime.fromisoformat(due_date).replace(tzinfo=UTC)
        except ValueError:
            due_at = None
    task = Task(
        project_id=project.id,
        client_id=int(client_id) if client_id.isdigit() else None,
        deal_id=int(deal_id) if deal_id.isdigit() else None,
        title=title.strip(),
        description=description.strip(),
        due_at=due_at,
        priority=priority,
        assigned_to_id=int(assigned_to) if assigned_to.isdigit() else user.id,
    )
    db.add(task)
    db.flush()
    log_activity(
        db,
        action="task_created",
        entity_type="task",
        entity_id=task.id,
        project_id=project.id,
        user_id=user.id,
        details=task.title,
    )
    db.commit()
    flash(request, "Задача создана")
    return RedirectResponse("/tasks", status_code=303)


@router.get("/{task_id}/edit")
def edit_task(task_id: int, request: Request, db: DbSession, user: CurrentUser):
    task = db.get(Task, task_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Задача не найдена")
    project = get_project_for_user(db, task.project_id, user)
    require_project_edit(db, project.id, user)
    clients = list(
        db.scalars(
            select(Client)
            .where(Client.project_id == project.id, Client.is_archived.is_(False))
            .order_by(Client.name)
        )
    )
    deals = list(
        db.scalars(
            select(Deal).where(Deal.project_id == project.id).order_by(Deal.created_at.desc()).limit(200)
        )
    )
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "tasks/form.html",
        db,
        user,
        active_project=project,
        task=task,
        clients=clients,
        deals=deals,
        users=users,
        selected_client_id=task.client_id,
        selected_deal_id=task.deal_id,
        form_action=f"/tasks/{task.id}/edit",
        title="Редактирование задачи",
    )


@router.post("/{task_id}/edit")
def update_task(
    task_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    title: str = Form(""),
    description: str = Form(""),
    client_id: str = Form(""),
    deal_id: str = Form(""),
    due_date: str = Form(""),
    priority: str = Form("normal"),
    assigned_to: str = Form(""),
):
    task = db.get(Task, task_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Задача не найдена")
    project = get_project_for_user(db, task.project_id, user)
    require_project_edit(db, project.id, user)
    if not title.strip():
        flash(request, "Название задачи обязательно", "error")
        return RedirectResponse(f"/tasks/{task.id}/edit", status_code=303)
    task.title = title.strip()
    task.description = description.strip()
    task.client_id = int(client_id) if client_id.isdigit() else None
    task.deal_id = int(deal_id) if deal_id.isdigit() else None
    task.priority = priority
    task.assigned_to_id = int(assigned_to) if assigned_to.isdigit() else None
    if due_date:
        try:
            task.due_at = datetime.fromisoformat(due_date).replace(tzinfo=UTC)
        except ValueError:
            task.due_at = None
    else:
        task.due_at = None
    log_activity(
        db,
        action="task_updated",
        entity_type="task",
        entity_id=task.id,
        project_id=project.id,
        user_id=user.id,
    )
    db.commit()
    flash(request, "Задача обновлена")
    return RedirectResponse("/tasks", status_code=303)


@router.post("/{task_id}/toggle")
def toggle_task(task_id: int, request: Request, db: DbSession, user: CurrentUser):
    task = db.get(Task, task_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Задача не найдена")
    project = get_project_for_user(db, task.project_id, user)
    require_project_edit(db, project.id, user)
    task.is_completed = not task.is_completed
    task.completed_at = datetime.now(UTC) if task.is_completed else None
    log_activity(
        db,
        action="task_completed" if task.is_completed else "task_reopened",
        entity_type="task",
        entity_id=task.id,
        project_id=project.id,
        user_id=user.id,
        details=task.title,
    )
    db.commit()
    return RedirectResponse(request.headers.get("referer", "/tasks"), status_code=303)


@router.post("/{task_id}/delete")
def delete_task(task_id: int, request: Request, db: DbSession, user: CurrentUser):
    task = db.get(Task, task_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Задача не найдена")
    project = get_project_for_user(db, task.project_id, user)
    require_project_edit(db, project.id, user)
    db.delete(task)
    db.commit()
    flash(request, "Задача удалена")
    return RedirectResponse("/tasks", status_code=303)
