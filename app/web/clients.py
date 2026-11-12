"""Веб-раздел клиентов."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.google import GoogleIntegrationError
from app.google.auth import load_user_credentials
from app.google.docs import GoogleDocsClient
from app.google.sheets import GoogleSheetsClient
from app.models import Client, GoogleFile, Task, User
from app.services.access import get_active_project, get_project_for_user, require_project_edit
from app.services.activity import activity_for_entity, log_activity
from app.web.utils import flash, render

router = APIRouter(prefix="/clients", tags=["web-clients"])
PER_PAGE = 20


@router.get("")
def list_clients(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    status_filter: str = "",
    archived: bool = False,
    page: int = 1,
):
    project = get_active_project(request, db, user)
    query = select(Client).where(Client.project_id == project.id)
    if q.strip():
        term = f"%{q.strip().casefold()}%"
        query = query.where(or_(Client.search_text.like(term), Client.name.ilike(term)))
    if status_filter:
        query = query.where(Client.status == status_filter)
    query = query.where(Client.is_archived.is_(archived))
    total = len(list(db.scalars(query)))
    clients = list(
        db.scalars(query.order_by(Client.name).offset((page - 1) * PER_PAGE).limit(PER_PAGE))
    )
    return render(
        request,
        "clients/list.html",
        db,
        user,
        active_project=project,
        clients=clients,
        total=total,
        page=page,
        per_page=PER_PAGE,
        q=q,
        status_filter=status_filter,
        archived=archived,
    )


@router.get("/new")
def new_client(request: Request, db: DbSession, user: CurrentUser):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "clients/form.html",
        db,
        user,
        active_project=project,
        client=None,
        users=users,
        form_action="/clients/new",
        title="Новый клиент",
    )


@router.post("/new")
def create_client(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    name: str = Form(""),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    status: str = Form("new"),
    source: str = Form(""),
    notes: str = Form(""),
    owner_id: str = Form(""),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    if not name.strip():
        flash(request, "Имя клиента обязательно", "error")
        return RedirectResponse("/clients/new", status_code=303)
    client = Client(
        project_id=project.id,
        name=name.strip(),
        company=company.strip(),
        email=email.strip(),
        phone=phone.strip(),
        status=status,
        source=source.strip(),
        notes=notes.strip(),
        owner_id=int(owner_id) if owner_id.isdigit() else user.id,
    )
    db.add(client)
    db.flush()
    log_activity(
        db,
        action="client_created",
        entity_type="client",
        entity_id=client.id,
        project_id=project.id,
        user_id=user.id,
        details=client.name,
    )
    db.commit()
    flash(request, f"Клиент «{client.name}» создан")
    return RedirectResponse(f"/clients/{client.id}", status_code=303)


@router.get("/{client_id}")
def client_detail(client_id: int, request: Request, db: DbSession, user: CurrentUser):
    client = db.scalar(
        select(Client)
        .options(selectinload(Client.deals), selectinload(Client.tasks), selectinload(Client.payments))
        .where(Client.id == client_id)
    )
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    project = get_project_for_user(db, client.project_id, user)
    files = list(
        db.scalars(
            select(GoogleFile)
            .where(GoogleFile.entity_type == "client", GoogleFile.entity_id == client.id)
            .order_by(GoogleFile.created_at.desc())
        )
    )
    activity = activity_for_entity(db, "client", client.id)
    return render(
        request,
        "clients/detail.html",
        db,
        user,
        active_project=project,
        client=client,
        files=files,
        activity=activity,
    )


@router.get("/{client_id}/edit")
def edit_client(client_id: int, request: Request, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    project = get_project_for_user(db, client.project_id, user)
    require_project_edit(db, project.id, user)
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "clients/form.html",
        db,
        user,
        active_project=project,
        client=client,
        users=users,
        form_action=f"/clients/{client.id}/edit",
        title="Редактирование клиента",
    )


@router.post("/{client_id}/edit")
def update_client(
    client_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    name: str = Form(""),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    status: str = Form("new"),
    source: str = Form(""),
    notes: str = Form(""),
    owner_id: str = Form(""),
):
    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    project = get_project_for_user(db, client.project_id, user)
    require_project_edit(db, project.id, user)
    if not name.strip():
        flash(request, "Имя клиента обязательно", "error")
        return RedirectResponse(f"/clients/{client.id}/edit", status_code=303)
    client.name = name.strip()
    client.company = company.strip()
    client.email = email.strip()
    client.phone = phone.strip()
    client.status = status
    client.source = source.strip()
    client.notes = notes.strip()
    client.owner_id = int(owner_id) if owner_id.isdigit() else None
    log_activity(
        db,
        action="client_updated",
        entity_type="client",
        entity_id=client.id,
        project_id=project.id,
        user_id=user.id,
    )
    db.commit()
    flash(request, "Клиент обновлён")
    return RedirectResponse(f"/clients/{client.id}", status_code=303)


@router.post("/{client_id}/archive")
def archive_client(client_id: int, request: Request, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    project = get_project_for_user(db, client.project_id, user)
    require_project_edit(db, project.id, user)
    client.is_archived = True
    client.status = "archived"
    db.commit()
    flash(request, "Клиент перемещён в архив")
    return RedirectResponse("/clients", status_code=303)


@router.post("/{client_id}/restore")
def restore_client(client_id: int, request: Request, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    project = get_project_for_user(db, client.project_id, user)
    require_project_edit(db, project.id, user)
    client.is_archived = False
    if client.status == "archived":
        client.status = "new"
    db.commit()
    flash(request, "Клиент восстановлен")
    return RedirectResponse(f"/clients/{client.id}", status_code=303)


@router.post("/{client_id}/tasks")
def add_client_task(
    client_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    title: str = Form(""),
    due_date: str = Form(""),
    priority: str = Form("normal"),
):
    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    project = get_project_for_user(db, client.project_id, user)
    require_project_edit(db, project.id, user)
    if not title.strip():
        flash(request, "Название задачи обязательно", "error")
        return RedirectResponse(f"/clients/{client.id}", status_code=303)
    due_at = None
    if due_date:
        try:
            due_at = datetime.fromisoformat(due_date).replace(tzinfo=UTC)
        except ValueError:
            due_at = None
    task = Task(
        project_id=project.id,
        client_id=client.id,
        title=title.strip(),
        priority=priority,
        due_at=due_at,
        assigned_to_id=user.id,
    )
    db.add(task)
    db.commit()
    flash(request, "Задача добавлена")
    return RedirectResponse(f"/clients/{client.id}", status_code=303)


@router.post("/{client_id}/google-doc")
def create_google_doc(client_id: int, request: Request, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    get_project_for_user(db, client.project_id, user)
    settings = get_settings()
    try:
        database = request.app.state.db
        folder_id = database.get_setting("google_drive_folder_id", "") or settings.google_drive_folder_id
        credentials = load_user_credentials(settings)
        document = GoogleDocsClient(credentials).create_text_document(
            f"Клиент: {client.name}",
            (
                f"Клиент: {client.name}\n"
                f"Компания: {client.company}\n"
                f"Email: {client.email}\n"
                f"Телефон: {client.phone}\n"
                f"Статус: {client.status}\n"
                f"Заметки: {client.notes}\n"
            ),
            folder_id or None,
        )
        db.add(
            GoogleFile(
                entity_type="client",
                entity_id=client.id,
                file_id=document["id"],
                name=document["name"],
                mime_type=document["mime_type"],
                web_url=document["url"],
            )
        )
        db.commit()
        flash(request, f"Google Документ создан: {document['url']}")
    except GoogleIntegrationError as exc:
        flash(request, f"Google: {exc}", "error")
    except Exception as exc:  # noqa: BLE001
        flash(request, f"Не удалось создать документ: {exc}", "error")
    return RedirectResponse(f"/clients/{client.id}", status_code=303)


@router.post("/{client_id}/google-sheet")
def create_google_sheet(client_id: int, request: Request, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Клиент не найден")
    get_project_for_user(db, client.project_id, user)
    settings = get_settings()
    try:
        database = request.app.state.db
        folder_id = database.get_setting("google_drive_folder_id", "") or settings.google_drive_folder_id
        from app.google.auth import load_user_credentials

        spreadsheet = GoogleSheetsClient(load_user_credentials(settings)).create_spreadsheet(
            f"Клиент: {client.name}", folder_id or None
        )
        db.add(
            GoogleFile(
                entity_type="client",
                entity_id=client.id,
                file_id=spreadsheet["id"],
                name=spreadsheet["name"],
                mime_type=spreadsheet["mime_type"],
                web_url=spreadsheet["url"],
            )
        )
        db.commit()
        flash(request, f"Google Таблица создана: {spreadsheet['url']}")
    except Exception as exc:  # noqa: BLE001
        flash(request, f"Google: {exc}", "error")
    return RedirectResponse(f"/clients/{client.id}", status_code=303)
