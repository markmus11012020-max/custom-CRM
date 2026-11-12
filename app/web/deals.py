"""Веб-раздел сделок и заказов."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.google import GoogleIntegrationError
from app.google.auth import load_user_credentials
from app.google.docs import GoogleDocsClient
from app.models import Client, Deal, GoogleFile, OrderItem, Product, User
from app.services.access import get_active_project, get_project_for_user, require_project_edit
from app.services.activity import activity_for_entity, log_activity
from app.services.payments import create_payment
from app.services.stock import create_stock_movement
from app.web.utils import flash, render

router = APIRouter(prefix="/deals", tags=["web-deals"])
PER_PAGE = 20


def _decimal(value: str, default: str = "0") -> Decimal:
    try:
        return Decimal(value.replace(",", ".") if value else default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


@router.get("")
def list_deals(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    stage: str = "",
    kind: str = "",
    page: int = 1,
):
    project = get_active_project(request, db, user)
    query = (
        select(Deal)
        .outerjoin(Client, Deal.client_id == Client.id)
        .where(Deal.project_id == project.id)
    )
    if q.strip():
        term = f"%{q.strip().casefold()}%"
        query = query.where(
            or_(
                Deal.search_text.like(term),
                Deal.title.ilike(term),
                Client.name.ilike(term),
                Client.company.ilike(term),
            )
        )
    if stage:
        query = query.where(Deal.stage == stage)
    if kind:
        query = query.where(Deal.kind == kind)
    total = len(list(db.scalars(query)))
    deals = list(
        db.scalars(query.order_by(Deal.created_at.desc()).offset((page - 1) * PER_PAGE).limit(PER_PAGE))
    )
    return render(
        request,
        "deals/list.html",
        db,
        user,
        active_project=project,
        deals=deals,
        total=total,
        page=page,
        per_page=PER_PAGE,
        q=q,
        stage=stage,
        kind=kind,
    )


@router.get("/new")
def new_deal(request: Request, db: DbSession, user: CurrentUser, client_id: int | None = None):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    clients = list(
        db.scalars(
            select(Client)
            .where(Client.project_id == project.id, Client.is_archived.is_(False))
            .order_by(Client.name)
        )
    )
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "deals/form.html",
        db,
        user,
        active_project=project,
        deal=None,
        clients=clients,
        users=users,
        selected_client_id=client_id,
        form_action="/deals/new",
        title="Новая сделка",
    )


@router.post("/new")
def create_deal(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    title: str = Form(""),
    client_id: str = Form(""),
    kind: str = Form("deal"),
    amount: str = Form("0"),
    stage: str = Form("new"),
    description: str = Form(""),
    owner_id: str = Form(""),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    if not title.strip():
        flash(request, "Название сделки обязательно", "error")
        return RedirectResponse("/deals/new", status_code=303)
    client_value = int(client_id) if client_id.isdigit() else None
    if client_value is not None:
        client = db.get(Client, client_value)
        if client is None or client.project_id != project.id:
            client_value = None
    deal = Deal(
        project_id=project.id,
        client_id=client_value,
        kind=kind,
        title=title.strip(),
        amount=_decimal(amount),
        stage=stage,
        description=description.strip(),
        owner_id=int(owner_id) if owner_id.isdigit() else user.id,
    )
    db.add(deal)
    db.flush()
    log_activity(
        db,
        action="deal_created",
        entity_type="deal",
        entity_id=deal.id,
        project_id=project.id,
        user_id=user.id,
        details=deal.title,
    )
    db.commit()
    flash(request, "Сделка создана")
    return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.get("/{deal_id}")
def deal_detail(deal_id: int, request: Request, db: DbSession, user: CurrentUser):
    deal = db.scalar(
        select(Deal)
        .options(
            selectinload(Deal.items),
            selectinload(Deal.payments),
            selectinload(Deal.tasks),
            selectinload(Deal.client),
        )
        .where(Deal.id == deal_id)
    )
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    products = list(
        db.scalars(
            select(Product)
            .where(Product.project_id == project.id, Product.is_active.is_(True))
            .order_by(Product.name)
        )
    )
    files = list(
        db.scalars(
            select(GoogleFile)
            .where(GoogleFile.entity_type == "deal", GoogleFile.entity_id == deal.id)
            .order_by(GoogleFile.created_at.desc())
        )
    )
    activity = activity_for_entity(db, "deal", deal.id)
    return render(
        request,
        "deals/detail.html",
        db,
        user,
        active_project=project,
        deal=deal,
        products=products,
        files=files,
        activity=activity,
    )


@router.get("/{deal_id}/edit")
def edit_deal(deal_id: int, request: Request, db: DbSession, user: CurrentUser):
    deal = db.get(Deal, deal_id)
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    clients = list(
        db.scalars(
            select(Client)
            .where(Client.project_id == project.id, Client.is_archived.is_(False))
            .order_by(Client.name)
        )
    )
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
    return render(
        request,
        "deals/form.html",
        db,
        user,
        active_project=project,
        deal=deal,
        clients=clients,
        users=users,
        selected_client_id=deal.client_id,
        form_action=f"/deals/{deal.id}/edit",
        title="Редактирование сделки",
    )


@router.post("/{deal_id}/edit")
def update_deal(
    deal_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    title: str = Form(""),
    client_id: str = Form(""),
    kind: str = Form("deal"),
    amount: str = Form("0"),
    stage: str = Form("new"),
    description: str = Form(""),
    owner_id: str = Form(""),
):
    deal = db.get(Deal, deal_id)
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    if not title.strip():
        flash(request, "Название сделки обязательно", "error")
        return RedirectResponse(f"/deals/{deal.id}/edit", status_code=303)
    old_stage = deal.stage
    deal.title = title.strip()
    deal.client_id = int(client_id) if client_id.isdigit() else None
    deal.kind = kind
    deal.amount = _decimal(amount)
    deal.stage = stage
    deal.description = description.strip()
    deal.owner_id = int(owner_id) if owner_id.isdigit() else None
    log_activity(
        db,
        action="deal_stage_changed" if old_stage != stage else "deal_updated",
        entity_type="deal",
        entity_id=deal.id,
        project_id=project.id,
        user_id=user.id,
        details=f"{old_stage} -> {stage}" if old_stage != stage else "",
    )
    db.commit()
    flash(request, "Сделка обновлена")
    return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.post("/{deal_id}/stage")
def change_stage(
    deal_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    stage: str = Form(...),
):
    deal = db.get(Deal, deal_id)
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    old_stage = deal.stage
    deal.stage = stage
    log_activity(
        db,
        action="deal_stage_changed",
        entity_type="deal",
        entity_id=deal.id,
        project_id=project.id,
        user_id=user.id,
        details=f"{old_stage} -> {stage}",
    )
    db.commit()
    flash(request, "Этап сделки обновлён")
    return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.post("/{deal_id}/items")
def add_item(
    deal_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    product_id: str = Form(""),
    name: str = Form(""),
    quantity: str = Form("1"),
    unit_price: str = Form("0"),
):
    deal = db.scalar(select(Deal).options(selectinload(Deal.items)).where(Deal.id == deal_id))
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    product = db.get(Product, int(product_id)) if product_id.isdigit() else None
    if product is not None and product.project_id != project.id:
        product = None
    item_name = name.strip() or (product.name if product else "")
    if not item_name:
        flash(request, "Укажите название позиции", "error")
        return RedirectResponse(f"/deals/{deal.id}", status_code=303)
    price = _decimal(unit_price)
    if price == 0 and product is not None:
        price = product.price
    qty = _decimal(quantity, "1")
    item = OrderItem(
        deal_id=deal.id,
        product_id=product.id if product else None,
        name=item_name,
        quantity=qty,
        unit_price=price,
        total=(qty * price).quantize(Decimal("0.01")),
    )
    db.add(item)
    db.flush()
    deal.items.append(item)
    deal.amount = sum((existing.total for existing in deal.items), Decimal("0"))
    db.commit()
    flash(request, "Позиция добавлена")
    return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.post("/{deal_id}/items/{item_id}/delete")
def delete_item(deal_id: int, item_id: int, request: Request, db: DbSession, user: CurrentUser):
    item = db.get(OrderItem, item_id)
    if item is None or item.deal_id != deal_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Позиция не найдена")
    deal = db.scalar(select(Deal).options(selectinload(Deal.items)).where(Deal.id == deal_id))
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    deal.items.remove(item)
    db.delete(item)
    db.flush()
    deal.amount = sum((existing.total for existing in deal.items), Decimal("0"))
    db.commit()
    flash(request, "Позиция удалена")
    return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.post("/{deal_id}/fulfill")
def fulfill(deal_id: int, request: Request, db: DbSession, user: CurrentUser):
    deal = db.scalar(select(Deal).options(selectinload(Deal.items)).where(Deal.id == deal_id))
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    if deal.kind != "order" or not deal.items:
        flash(request, "Выполнить можно только заказ с позициями", "error")
        return RedirectResponse(f"/deals/{deal.id}", status_code=303)
    if deal.stage == "fulfilled" or deal.fulfilled_at is not None:
        flash(request, "Заказ уже выполнен", "warning")
        return RedirectResponse(f"/deals/{deal.id}", status_code=303)
    try:
        for item in deal.items:
            if item.product_id is None:
                continue
            product = db.get(Product, item.product_id)
            if product is None:
                continue
            create_stock_movement(
                db,
                product=product,
                movement_type="out",
                quantity=item.quantity,
                unit_cost=Decimal("0"),
                reference=f"Заказ #{deal.id}",
                comment=item.name,
                user=user,
            )
        deal.stage = "fulfilled"
        deal.fulfilled_at = datetime.now(UTC)
        log_activity(
            db,
            action="order_fulfilled",
            entity_type="deal",
            entity_id=deal.id,
            project_id=project.id,
            user_id=user.id,
            details=f"Списано позиций: {len(deal.items)}",
        )
        db.commit()
        flash(request, "Заказ выполнен, товары списаны со склада")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Не удалось выполнить заказ: {exc}", "error")
    return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.post("/{deal_id}/payment")
def create_deal_payment(
    deal_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    amount: str = Form("0"),
    description: str = Form(""),
    method: str = Form("manual"),
):
    deal = db.get(Deal, deal_id)
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    try:
        payment = create_payment(
            db,
            project=project,
            amount=_decimal(amount),
            client_id=deal.client_id,
            deal_id=deal.id,
            description=description or deal.title,
            method=method,
            user=user,
            settings=request.app.state.settings,
        )
        db.commit()
        flash(request, "Счёт создан")
        return RedirectResponse(f"/payments/{payment.id}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Не удалось создать счёт: {exc}", "error")
        return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.post("/{deal_id}/google-doc")
def create_deal_doc(deal_id: int, request: Request, db: DbSession, user: CurrentUser):
    deal = db.get(Deal, deal_id)
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    get_project_for_user(db, deal.project_id, user)
    settings = get_settings()
    try:
        database = request.app.state.db
        folder_id = database.get_setting("google_drive_folder_id", "") or settings.google_drive_folder_id
        document = GoogleDocsClient(load_user_credentials(settings)).create_text_document(
            f"Сделка: {deal.title}",
            (
                f"Сделка: {deal.title}\n"
                f"Клиент: {deal.client.name if deal.client else '—'}\n"
                f"Сумма: {deal.amount} {deal.currency}\n"
                f"Этап: {deal.stage}\n"
                f"Описание: {deal.description}\n"
            ),
            folder_id or None,
        )
        db.add(
            GoogleFile(
                entity_type="deal",
                entity_id=deal.id,
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
    return RedirectResponse(f"/deals/{deal.id}", status_code=303)


@router.post("/{deal_id}/archive")
def archive_deal(deal_id: int, request: Request, db: DbSession, user: CurrentUser):
    deal = db.get(Deal, deal_id)
    if deal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Сделка не найдена")
    project = get_project_for_user(db, deal.project_id, user)
    require_project_edit(db, project.id, user)
    deal.stage = "lost"
    db.commit()
    flash(request, "Сделка закрыта как проигранная")
    return RedirectResponse("/deals", status_code=303)
