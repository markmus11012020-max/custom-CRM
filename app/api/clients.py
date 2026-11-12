"""API клиентов."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import or_, select

from app.api.deps import (
    CurrentUser,
    DbSession,
    Paging,
    paginate,
    require_edit,
    resolve_project,
)
from app.models import Client
from app.schemas import ClientCreate, ClientRead, ClientUpdate, Page
from app.services.activity import log_activity

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=Page[ClientRead])
def list_clients(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
    q: str = "",
    status_filter: str | None = Query(default=None, alias="status"),
    archived: bool | None = None,
    owner_id: int | None = None,
):
    project = resolve_project(request, db, user, project_id)
    query = select(Client).where(Client.project_id == project.id)
    if q.strip():
        term = f"%{q.strip().casefold()}%"
        query = query.where(
            or_(
                Client.search_text.like(term),
                Client.name.ilike(term),
                Client.company.ilike(term),
                Client.email.ilike(term),
                Client.phone.ilike(term),
            )
        )
    if status_filter:
        query = query.where(Client.status == status_filter)
    if archived is not None:
        query = query.where(Client.is_archived.is_(archived))
    if owner_id:
        query = query.where(Client.owner_id == owner_id)
    query = query.order_by(Client.name)
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("", response_model=ClientRead, status_code=201)
def create_client(
    payload: ClientCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    client = Client(
        project_id=project.id,
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        status=payload.status,
        source=payload.source,
        notes=payload.notes,
        owner_id=payload.owner_id or user.id,
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
    return client


@router.get("/{client_id}", response_model=ClientRead)
def get_client(client_id: int, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    from app.services.access import get_project_for_user

    get_project_for_user(db, client.project_id, user)
    return client


@router.put("/{client_id}", response_model=ClientRead)
def update_client(client_id: int, payload: ClientUpdate, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    from app.services.access import get_project_for_user

    project = get_project_for_user(db, client.project_id, user)
    require_edit(db, project, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    log_activity(
        db,
        action="client_updated",
        entity_type="client",
        entity_id=client.id,
        project_id=client.project_id,
        user_id=user.id,
    )
    db.commit()
    return client


@router.delete("/{client_id}")
def archive_client(client_id: int, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    from app.services.access import get_project_for_user

    project = get_project_for_user(db, client.project_id, user)
    require_edit(db, project, user)
    client.is_archived = True
    client.status = "archived"
    log_activity(
        db,
        action="client_archived",
        entity_type="client",
        entity_id=client.id,
        project_id=client.project_id,
        user_id=user.id,
    )
    db.commit()
    return {"ok": True}


@router.post("/{client_id}/restore", response_model=ClientRead)
def restore_client(client_id: int, db: DbSession, user: CurrentUser):
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    from app.services.access import get_project_for_user

    project = get_project_for_user(db, client.project_id, user)
    require_edit(db, project, user)
    client.is_archived = False
    if client.status == "archived":
        client.status = "new"
    log_activity(
        db,
        action="client_restored",
        entity_type="client",
        entity_id=client.id,
        project_id=client.project_id,
        user_id=user.id,
    )
    db.commit()
    return client


@router.delete("/{client_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_permanent(client_id: int, db: DbSession, user: CurrentUser):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Только администратор может удалять клиентов")
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    db.delete(client)
    db.commit()
    return None
