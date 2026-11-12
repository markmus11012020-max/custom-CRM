"""API задач."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession, Paging, paginate, require_edit, resolve_project
from app.models import Client, Deal, Task
from app.schemas import Page, TaskCreate, TaskRead, TaskUpdate
from app.services.access import get_project_for_user
from app.services.activity import log_activity

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_task(db: DbSession, task_id: int, user) -> Task:  # type: ignore[no-untyped-def]
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    get_project_for_user(db, task.project_id, user)
    return task


@router.get("", response_model=Page[TaskRead])
def list_tasks(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
    q: str = "",
    assigned_to: int | None = None,
    completed: bool | None = None,
    bucket: str | None = None,
):
    project = resolve_project(request, db, user, project_id)
    query = (
        select(Task)
        .outerjoin(Client, Task.client_id == Client.id)
        .outerjoin(Deal, Task.deal_id == Deal.id)
        .where(Task.project_id == project.id)
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
    if assigned_to:
        query = query.where(Task.assigned_to_id == assigned_to)
    if completed is not None:
        query = query.where(Task.is_completed.is_(completed))
    now = datetime.now(UTC)
    if bucket == "overdue":
        query = query.where(Task.is_completed.is_(False), Task.due_at < now)
    elif bucket == "today":
        start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        query = query.where(Task.due_at >= start, Task.due_at < start + timedelta(days=1))
    elif bucket == "future":
        query = query.where(Task.due_at >= now + timedelta(days=1))
    query = query.order_by(Task.is_completed, Task.due_at.is_(None), Task.due_at, Task.priority.desc())
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("", response_model=TaskRead, status_code=201)
def create_task(payload: TaskCreate, request: Request, db: DbSession, user: CurrentUser):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    if payload.client_id is not None:
        client = db.get(Client, payload.client_id)
        if client is None or client.project_id != project.id:
            raise HTTPException(status_code=400, detail="Клиент не найден в проекте")
    if payload.deal_id is not None:
        deal = db.get(Deal, payload.deal_id)
        if deal is None or deal.project_id != project.id:
            raise HTTPException(status_code=400, detail="Сделка не найдена в проекте")
    task = Task(
        project_id=project.id,
        client_id=payload.client_id,
        deal_id=payload.deal_id,
        title=payload.title,
        description=payload.description,
        due_at=payload.due_at,
        priority=payload.priority,
        assigned_to_id=payload.assigned_to_id or user.id,
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
    return task


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: DbSession, user: CurrentUser):
    return _get_task(db, task_id, user)


@router.put("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: DbSession, user: CurrentUser):
    task = _get_task(db, task_id, user)
    require_edit(db, task.project, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "is_completed":
            task.is_completed = bool(value)
            task.completed_at = datetime.now(UTC) if value else None
        else:
            setattr(task, field, value)
    log_activity(
        db,
        action="task_updated",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        user_id=user.id,
    )
    db.commit()
    return task


@router.delete("/{task_id}")
def delete_task(task_id: int, db: DbSession, user: CurrentUser):
    task = _get_task(db, task_id, user)
    require_edit(db, task.project, user)
    db.delete(task)
    db.commit()
    return {"ok": True}


@router.post("/{task_id}/complete", response_model=TaskRead)
def complete_task(task_id: int, db: DbSession, user: CurrentUser):
    task = _get_task(db, task_id, user)
    require_edit(db, task.project, user)
    task.is_completed = True
    task.completed_at = datetime.now(UTC)
    log_activity(
        db,
        action="task_completed",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        user_id=user.id,
        details=task.title,
    )
    db.commit()
    return task


@router.post("/{task_id}/reopen", response_model=TaskRead)
def reopen_task(task_id: int, db: DbSession, user: CurrentUser):
    task = _get_task(db, task_id, user)
    require_edit(db, task.project, user)
    task.is_completed = False
    task.completed_at = None
    db.commit()
    return task
