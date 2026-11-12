"""Администрирование: пользователи, проекты, активность и настройки."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.google import GoogleIntegrationError
from app.google.auth import oauth_status, service_account_status
from app.google.bootstrap import ensure_folder, resolve_folder_id
from app.models import ActivityLog, Project, ProjectMember, User
from app.services.access import ensure_project_member
from app.services.auth import create_user, require_admin, update_user
from app.services.notifications import process_pending, queue_test_notification
from app.web.utils import flash, render

router = APIRouter(prefix="/admin", tags=["web-admin"])
PER_PAGE = 30


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------
@router.get("/users")
def users(request: Request, db: DbSession, user: CurrentUser, q: str = ""):
    require_admin(user)
    query = select(User)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where(or_(User.email.ilike(term), User.full_name.ilike(term)))
    items = list(db.scalars(query.order_by(User.full_name, User.email)))
    return render(request, "admin/users.html", db, user, users=items, q=q)


@router.get("/users/new")
def new_user(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    return render(
        request,
        "admin/user_form.html",
        db,
        user,
        target=None,
        form_action="/admin/users/new",
        title="Новый пользователь",
    )


@router.post("/users/new")
def create_user_web(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    email: str = Form(""),
    password: str = Form(""),
    full_name: str = Form(""),
    role: str = Form("manager"),
    telegram_chat_id: str = Form(""),
):
    require_admin(user)
    try:
        if len(password) < 8:
            raise ValueError("Пароль должен быть не короче 8 символов")
        create_user(
            db,
            email=email,
            password=password,
            full_name=full_name,
            role=role,
            telegram_chat_id=telegram_chat_id,
            notify_email=True,
            notify_telegram=bool(telegram_chat_id),
        )
        db.commit()
        flash(request, "Пользователь создан")
        return RedirectResponse("/admin/users", status_code=303)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Ошибка: {exc}", "error")
        return RedirectResponse("/admin/users/new", status_code=303)


@router.get("/users/{user_id}/edit")
def edit_user(request: Request, db: DbSession, user: CurrentUser, user_id: int):
    require_admin(user)
    target = db.get(User, user_id)
    if target is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return render(
        request,
        "admin/user_form.html",
        db,
        user,
        target=target,
        form_action=f"/admin/users/{target.id}/edit",
        title="Редактирование пользователя",
    )


@router.post("/users/{user_id}/edit")
def update_user_web(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    user_id: int,
    email: str = Form(""),
    password: str = Form(""),
    full_name: str = Form(""),
    role: str = Form("manager"),
    telegram_chat_id: str = Form(""),
    is_active: str = Form(""),
    notify_email: str = Form(""),
    notify_telegram: str = Form(""),
):
    require_admin(user)
    target = db.get(User, user_id)
    if target is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Пользователь не найден")
    try:
        update_user(
            db,
            target,
            {
                "email": email,
                "full_name": full_name,
                "role": role,
                "telegram_chat_id": telegram_chat_id,
                "is_active": is_active == "on",
                "notify_email": notify_email == "on",
                "notify_telegram": notify_telegram == "on",
                "password": password or None,
            },
        )
        db.commit()
        flash(request, "Пользователь обновлён")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Ошибка: {exc}", "error")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(request: Request, db: DbSession, user: CurrentUser, user_id: int):
    require_admin(user)
    if user.id == user_id:
        flash(request, "Нельзя деактивировать самого себя", "error")
        return RedirectResponse("/admin/users", status_code=303)
    target = db.get(User, user_id)
    if target:
        target.is_active = False
        db.commit()
        flash(request, "Пользователь деактивирован")
    return RedirectResponse("/admin/users", status_code=303)


# ---------------------------------------------------------------------------
# Проекты
# ---------------------------------------------------------------------------
@router.get("/projects")
def projects(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    items = list(db.scalars(select(Project).order_by(Project.name)))
    return render(request, "admin/projects.html", db, user, projects=items)


@router.get("/projects/new")
def new_project(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "admin/project_form.html",
        db,
        user,
        project=None,
        users=users,
        form_action="/admin/projects/new",
        title="Новый проект",
    )


@router.post("/projects/new")
def create_project_web(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    name: str = Form(""),
    code: str = Form(""),
    description: str = Form(""),
    currency: str = Form("RUB"),
    owner_id: str = Form(""),
):
    require_admin(user)
    code = code.strip().lower()
    if not name.strip() or not code:
        flash(request, "Название и код проекта обязательны", "error")
        return RedirectResponse("/admin/projects/new", status_code=303)
    if db.scalar(select(Project).where(Project.code == code)):
        flash(request, "Проект с таким кодом уже существует", "error")
        return RedirectResponse("/admin/projects/new", status_code=303)
    owner = db.get(User, int(owner_id)) if owner_id.isdigit() else user
    project = Project(
        name=name.strip(),
        code=code,
        description=description.strip(),
        currency=currency,
        owner_id=owner.id if owner else user.id,
    )
    db.add(project)
    db.flush()
    ensure_project_member(db, project, owner or user, "manager")
    if owner and owner.id != user.id:
        ensure_project_member(db, project, user, "manager")
    db.commit()
    flash(request, "Проект создан")
    return RedirectResponse("/admin/projects", status_code=303)


@router.get("/projects/{project_id}/edit")
def edit_project(request: Request, db: DbSession, user: CurrentUser, project_id: int):
    require_admin(user)
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.members).selectinload(ProjectMember.user))
        .where(Project.id == project_id)
    )
    if project is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Проект не найден")
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "admin/project_form.html",
        db,
        user,
        project=project,
        users=users,
        form_action=f"/admin/projects/{project.id}/edit",
        title="Редактирование проекта",
    )


@router.post("/projects/{project_id}/edit")
def update_project_web(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    project_id: int,
    name: str = Form(""),
    description: str = Form(""),
    currency: str = Form("RUB"),
    status: str = Form("active"),
):
    require_admin(user)
    project = db.get(Project, project_id)
    if project is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Проект не найден")
    project.name = name.strip() or project.name
    project.description = description.strip()
    project.currency = currency
    project.status = status
    project.is_archived = status == "archived"
    db.commit()
    flash(request, "Проект обновлён")
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/projects/{project_id}/members")
def add_member(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    project_id: int,
    user_id: int = Form(...),
    role: str = Form("manager"),
):
    require_admin(user)
    project = db.get(Project, project_id)
    target = db.get(User, user_id)
    if project is None or target is None:
        flash(request, "Проект или пользователь не найдены", "error")
        return RedirectResponse("/admin/projects", status_code=303)
    ensure_project_member(db, project, target, role)
    db.commit()
    flash(request, "Участник добавлен")
    return RedirectResponse(f"/admin/projects/{project.id}/edit", status_code=303)


@router.post("/projects/{project_id}/members/{member_id}/delete")
def remove_member(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    project_id: int,
    member_id: int,
):
    require_admin(user)
    project = db.get(Project, project_id)
    member = db.get(ProjectMember, member_id)
    if project is None or member is None or member.project_id != project.id:
        flash(request, "Участник не найден", "error")
        return RedirectResponse("/admin/projects", status_code=303)
    if project.owner_id == member.user_id:
        flash(request, "Нельзя удалить владельца проекта", "error")
        return RedirectResponse(f"/admin/projects/{project.id}/edit", status_code=303)
    db.delete(member)
    db.commit()
    flash(request, "Участник удалён")
    return RedirectResponse(f"/admin/projects/{project.id}/edit", status_code=303)


# ---------------------------------------------------------------------------
# Активность
# ---------------------------------------------------------------------------
@router.get("/activity")
def activity(request: Request, db: DbSession, user: CurrentUser, page: int = 1):
    require_admin(user)
    query = select(ActivityLog).options(selectinload(ActivityLog.user), selectinload(ActivityLog.project))
    total = len(list(db.scalars(query)))
    items = list(
        db.scalars(
            query.order_by(ActivityLog.created_at.desc())
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
        )
    )
    return render(
        request,
        "admin/activity.html",
        db,
        user,
        activity=items,
        total=total,
        page=page,
        per_page=PER_PAGE,
    )


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
@router.get("/settings")
def settings_page(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    settings = request.app.state.settings
    database = request.app.state.db
    return render(
        request,
        "admin/settings.html",
        db,
        user,
        settings=settings,
        oauth=oauth_status(settings),
        service_account=service_account_status(settings),
        folder_id=resolve_folder_id(settings, database),
    )


@router.post("/settings/backup")
def backup(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    path = request.app.state.db.backup()
    if path:
        flash(request, f"Резервная копия создана: {path.name}")
    else:
        flash(request, "Автоматическая копия доступна только для SQLite. Используйте pg_dump.", "warning")
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/test-email")
def test_email(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    if not user.email:
        flash(request, "У пользователя не указан email", "error")
        return RedirectResponse("/admin/settings", status_code=303)
    queue_test_notification(db, user, "email")
    result = process_pending(db, request.app.state.settings)
    db.commit()
    flash(request, f"Тест email: {result}", "success" if result["sent"] else "warning")
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/test-telegram")
def test_telegram(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    if not user.telegram_chat_id:
        flash(request, "У пользователя не указан Telegram chat_id", "error")
        return RedirectResponse("/admin/settings", status_code=303)
    queue_test_notification(db, user, "telegram")
    result = process_pending(db, request.app.state.settings)
    db.commit()
    flash(request, f"Тест Telegram: {result}", "success" if result["sent"] else "warning")
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/google/bootstrap")
def google_bootstrap(request: Request, db: DbSession, user: CurrentUser):
    require_admin(user)
    settings = request.app.state.settings
    try:
        folder = ensure_folder(settings, database=request.app.state.db)
        flash(request, f"Папка Google готова: {folder['web_url']}")
    except GoogleIntegrationError as exc:
        flash(request, f"Google: {exc}", "error")
    except Exception as exc:  # noqa: BLE001
        flash(request, f"Ошибка Google: {exc}", "error")
    return RedirectResponse("/admin/settings", status_code=303)
