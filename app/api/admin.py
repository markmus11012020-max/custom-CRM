"""Административное API: пользователи, активность, уведомления."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Paging, paginate
from app.models import ActivityLog, Notification, User
from app.schemas import NotificationRead, Page, UserCreate, UserRead, UserUpdate
from app.services.auth import create_user, require_admin, update_user

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/users", response_model=Page[UserRead])
def list_users(
    db: DbSession,
    paging: Paging,
    user: User = Depends(require_admin),
    q: str = "",
):
    query = select(User)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where((User.email.ilike(term)) | (User.full_name.ilike(term)))
    query = query.order_by(User.full_name, User.email)
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("/users", response_model=UserRead, status_code=201)
def add_user(payload: UserCreate, db: DbSession, user: User = Depends(require_admin)):
    created = create_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        telegram_chat_id=payload.telegram_chat_id,
        notify_email=payload.notify_email,
        notify_telegram=payload.notify_telegram,
    )
    db.commit()
    return created


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: DbSession, user: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return target


@router.put("/users/{user_id}", response_model=UserRead)
def edit_user(
    user_id: int, payload: UserUpdate, db: DbSession, user: User = Depends(require_admin)
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    update_user(db, target, payload.model_dump(exclude_unset=True))
    db.commit()
    return target


@router.delete("/users/{user_id}")
def deactivate_user(user_id: int, db: DbSession, user: User = Depends(require_admin)):
    if user.id == user_id:
        raise HTTPException(status_code=409, detail="Нельзя деактивировать самого себя")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    target.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/activity", response_model=Page[dict])
def activity(
    db: DbSession,
    paging: Paging,
    user: User = Depends(require_admin),
    project_id: int | None = None,
):
    query = select(ActivityLog)
    if project_id:
        query = query.where(ActivityLog.project_id == project_id)
    query = query.order_by(ActivityLog.created_at.desc())
    items, total = paginate(db, query, paging)
    return Page(
        items=[
            {
                "id": item.id,
                "project_id": item.project_id,
                "user_id": item.user_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "action": item.action,
                "details": item.details,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        total=total,
        page=paging.page,
        per_page=paging.per_page,
    )


@router.get("/notifications", response_model=Page[NotificationRead])
def notifications(
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    status_filter: str | None = Query(default=None, alias="status"),
):
    query = select(Notification)
    if user.role != "admin":
        query = query.where(Notification.user_id == user.id)
    if status_filter:
        query = query.where(Notification.status == status_filter)
    query = query.order_by(Notification.created_at.desc())
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)
