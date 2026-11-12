"""API сделок, заказов и позиций."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, Paging, paginate, require_edit, resolve_project
from app.models import Client, Deal, OrderItem, Product
from app.schemas import (
    DealCreate,
    DealDetailRead,
    DealRead,
    DealUpdate,
    OrderItemCreate,
    OrderItemRead,
    Page,
)
from app.services.access import get_project_for_user
from app.services.activity import log_activity
from app.services.stock import create_stock_movement

router = APIRouter(prefix="/api/deals", tags=["deals"])


def _get_deal(db: DbSession, deal_id: int, user) -> Deal:  # type: ignore[no-untyped-def]
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    get_project_for_user(db, deal.project_id, user)
    return deal


def _recalc(deal: Deal) -> None:
    deal.amount = sum((item.total for item in deal.items), Decimal("0"))


@router.get("", response_model=Page[DealRead])
def list_deals(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
    q: str = "",
    stage: str | None = None,
    kind: str | None = None,
    client_id: int | None = None,
):
    project = resolve_project(request, db, user, project_id)
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
    if client_id:
        query = query.where(Deal.client_id == client_id)
    query = query.order_by(Deal.created_at.desc())
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("", response_model=DealRead, status_code=201)
def create_deal(payload: DealCreate, request: Request, db: DbSession, user: CurrentUser):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    if payload.client_id is not None:
        client = db.get(Client, payload.client_id)
        if client is None or client.project_id != project.id:
            raise HTTPException(status_code=400, detail="Клиент не найден в проекте")
    deal = Deal(
        project_id=project.id,
        client_id=payload.client_id,
        kind=payload.kind,
        title=payload.title,
        amount=payload.amount,
        currency=payload.currency,
        stage=payload.stage,
        description=payload.description,
        owner_id=payload.owner_id or user.id,
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
        details=f"{deal.title} — {deal.amount}",
    )
    db.commit()
    return deal


@router.get("/{deal_id}", response_model=DealDetailRead)
def get_deal(deal_id: int, db: DbSession, user: CurrentUser):
    deal = db.scalar(
        select(Deal).options(selectinload(Deal.items)).where(Deal.id == deal_id)
    )
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    get_project_for_user(db, deal.project_id, user)
    return deal


@router.put("/{deal_id}", response_model=DealRead)
def update_deal(deal_id: int, payload: DealUpdate, db: DbSession, user: CurrentUser):
    deal = _get_deal(db, deal_id, user)
    require_edit(db, deal.project, user)
    if payload.client_id is not None:
        client = db.get(Client, payload.client_id)
        if client is None or client.project_id != deal.project_id:
            raise HTTPException(status_code=400, detail="Клиент не найден в проекте")
    old_stage = deal.stage
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(deal, field, value)
    if old_stage != deal.stage:
        log_activity(
            db,
            action="deal_stage_changed",
            entity_type="deal",
            entity_id=deal.id,
            project_id=deal.project_id,
            user_id=user.id,
            details=f"{old_stage} -> {deal.stage}",
        )
    else:
        log_activity(
            db,
            action="deal_updated",
            entity_type="deal",
            entity_id=deal.id,
            project_id=deal.project_id,
            user_id=user.id,
        )
    db.commit()
    return deal


@router.delete("/{deal_id}")
def archive_deal(deal_id: int, db: DbSession, user: CurrentUser):
    deal = _get_deal(db, deal_id, user)
    require_edit(db, deal.project, user)
    deal.stage = "lost"
    log_activity(
        db,
        action="deal_archived",
        entity_type="deal",
        entity_id=deal.id,
        project_id=deal.project_id,
        user_id=user.id,
    )
    db.commit()
    return {"ok": True}


@router.post("/{deal_id}/items", response_model=OrderItemRead, status_code=201)
def add_item(deal_id: int, payload: OrderItemCreate, db: DbSession, user: CurrentUser):
    deal = db.scalar(select(Deal).options(selectinload(Deal.items)).where(Deal.id == deal_id))
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    get_project_for_user(db, deal.project_id, user)
    require_edit(db, deal.project, user)
    name = payload.name
    unit_price = payload.unit_price
    if payload.product_id is not None:
        product = db.get(Product, payload.product_id)
        if product is None or product.project_id != deal.project_id:
            raise HTTPException(status_code=400, detail="Товар не найден в проекте")
        name = name or product.name
        if unit_price == 0:
            unit_price = product.price
    total = (payload.quantity * unit_price).quantize(Decimal("0.01"))
    item = OrderItem(
        deal_id=deal.id,
        product_id=payload.product_id,
        name=name,
        quantity=payload.quantity,
        unit_price=unit_price,
        total=total,
    )
    db.add(item)
    db.flush()
    deal.items.append(item)
    _recalc(deal)
    db.commit()
    return item


@router.delete("/{deal_id}/items/{item_id}")
def delete_item(deal_id: int, item_id: int, db: DbSession, user: CurrentUser):
    item = db.get(OrderItem, item_id)
    if item is None or item.deal_id != deal_id:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    deal = db.scalar(select(Deal).options(selectinload(Deal.items)).where(Deal.id == deal_id))
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    get_project_for_user(db, deal.project_id, user)
    require_edit(db, deal.project, user)
    deal.items.remove(item)
    db.delete(item)
    db.flush()
    _recalc(deal)
    db.commit()
    return {"ok": True}


@router.post("/{deal_id}/fulfill", response_model=DealRead)
def fulfill_deal(deal_id: int, db: DbSession, user: CurrentUser):
    deal = db.scalar(select(Deal).options(selectinload(Deal.items)).where(Deal.id == deal_id))
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    get_project_for_user(db, deal.project_id, user)
    require_edit(db, deal.project, user)
    if deal.kind != "order":
        raise HTTPException(status_code=400, detail="Выполнить можно только заказ")
    if deal.stage == "fulfilled" or deal.fulfilled_at is not None:
        raise HTTPException(status_code=409, detail="Заказ уже выполнен")
    if not deal.items:
        raise HTTPException(status_code=400, detail="В заказе нет позиций")
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
        project_id=deal.project_id,
        user_id=user.id,
        details=f"Списано позиций: {len(deal.items)}",
    )
    db.commit()
    return deal
