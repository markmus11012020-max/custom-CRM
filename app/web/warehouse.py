"""Веб-раздел склада."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models import Product, StockMovement
from app.services.access import get_active_project, get_project_for_user, require_project_edit
from app.services.activity import log_activity
from app.services.stock import create_stock_movement, low_stock_products, stock_value
from app.web.utils import flash, render

router = APIRouter(prefix="/warehouse", tags=["web-warehouse"])
PER_PAGE = 30


def _decimal(value: str, default: str = "0") -> Decimal:
    try:
        return Decimal(value.replace(",", ".") if value else default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


@router.get("")
def warehouse(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    low_only: bool = False,
    page: int = 1,
):
    project = get_active_project(request, db, user)
    query = select(Product).where(Product.project_id == project.id, Product.is_active.is_(True))
    if q.strip():
        query = query.where(Product.name.ilike(f"%{q.strip()}%") | Product.sku.ilike(f"%{q.strip()}%"))
    if low_only:
        query = query.where(Product.stock_qty <= Product.min_stock)
    total = len(list(db.scalars(query)))
    products = list(
        db.scalars(
            query.order_by(Product.name).offset((page - 1) * PER_PAGE).limit(PER_PAGE)
        )
    )
    movements = list(
        db.scalars(
            select(StockMovement)
            .options(selectinload(StockMovement.product))
            .where(StockMovement.project_id == project.id)
            .order_by(StockMovement.created_at.desc())
            .limit(20)
        )
    )
    return render(
        request,
        "warehouse/list.html",
        db,
        user,
        active_project=project,
        products=products,
        movements=movements,
        low_stock=low_stock_products(db, project.id),
        stock_value=stock_value(db, project.id),
        total=total,
        page=page,
        per_page=PER_PAGE,
        q=q,
        low_only=low_only,
    )


@router.get("/products/new")
def new_product(request: Request, db: DbSession, user: CurrentUser):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    return render(
        request,
        "warehouse/product_form.html",
        db,
        user,
        active_project=project,
        product=None,
        form_action="/warehouse/products/new",
        title="Новый товар",
    )


@router.post("/products/new")
def create_product(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    sku: str = Form(""),
    name: str = Form(""),
    unit: str = Form("шт"),
    price: str = Form("0"),
    cost: str = Form("0"),
    min_stock: str = Form("0"),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    if not name.strip():
        flash(request, "Название товара обязательно", "error")
        return RedirectResponse("/warehouse/products/new", status_code=303)
    product = Product(
        project_id=project.id,
        sku=sku.strip(),
        name=name.strip(),
        unit=unit.strip() or "шт",
        price=_decimal(price),
        cost=_decimal(cost),
        min_stock=_decimal(min_stock),
    )
    db.add(product)
    log_activity(
        db,
        action="product_created",
        entity_type="product",
        entity_id=product.id,
        project_id=project.id,
        user_id=user.id,
        details=product.name,
    )
    db.commit()
    flash(request, "Товар создан")
    return RedirectResponse("/warehouse", status_code=303)


@router.get("/products/{product_id}/edit")
def edit_product(product_id: int, request: Request, db: DbSession, user: CurrentUser):
    product = db.get(Product, product_id)
    if product is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Товар не найден")
    project = get_project_for_user(db, product.project_id, user)
    require_project_edit(db, project.id, user)
    return render(
        request,
        "warehouse/product_form.html",
        db,
        user,
        active_project=project,
        product=product,
        form_action=f"/warehouse/products/{product.id}/edit",
        title="Редактирование товара",
    )


@router.post("/products/{product_id}/edit")
def update_product(
    product_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    sku: str = Form(""),
    name: str = Form(""),
    unit: str = Form("шт"),
    price: str = Form("0"),
    cost: str = Form("0"),
    min_stock: str = Form("0"),
):
    product = db.get(Product, product_id)
    if product is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Товар не найден")
    project = get_project_for_user(db, product.project_id, user)
    require_project_edit(db, project.id, user)
    if not name.strip():
        flash(request, "Название товара обязательно", "error")
        return RedirectResponse(f"/warehouse/products/{product.id}/edit", status_code=303)
    product.sku = sku.strip()
    product.name = name.strip()
    product.unit = unit.strip() or "шт"
    product.price = _decimal(price)
    product.cost = _decimal(cost)
    product.min_stock = _decimal(min_stock)
    db.commit()
    flash(request, "Товар обновлён")
    return RedirectResponse("/warehouse", status_code=303)


@router.post("/products/{product_id}/deactivate")
def deactivate_product(product_id: int, request: Request, db: DbSession, user: CurrentUser):
    product = db.get(Product, product_id)
    if product is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Товар не найден")
    project = get_project_for_user(db, product.project_id, user)
    require_project_edit(db, project.id, user)
    product.is_active = False
    db.commit()
    flash(request, "Товар деактивирован")
    return RedirectResponse("/warehouse", status_code=303)


@router.post("/movements")
def add_movement(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    product_id: str = Form(""),
    movement_type: str = Form("in"),
    quantity: str = Form("0"),
    unit_cost: str = Form("0"),
    reference: str = Form(""),
    comment: str = Form(""),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    product = db.get(Product, int(product_id)) if product_id.isdigit() else None
    if product is None or product.project_id != project.id:
        flash(request, "Выберите товар", "error")
        return RedirectResponse("/warehouse", status_code=303)
    try:
        movement = create_stock_movement(
            db,
            product=product,
            movement_type=movement_type,
            quantity=_decimal(quantity),
            unit_cost=_decimal(unit_cost),
            reference=reference,
            comment=comment,
            user=user,
        )
        log_activity(
            db,
            action=f"stock_{movement_type}",
            entity_type="product",
            entity_id=product.id,
            project_id=project.id,
            user_id=user.id,
            details=f"{product.name}: {movement.quantity}",
        )
        db.commit()
        flash(request, "Складская операция проведена")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Ошибка склада: {exc}", "error")
    return RedirectResponse("/warehouse", status_code=303)


@router.get("/movements")
def movements(request: Request, db: DbSession, user: CurrentUser, page: int = 1):
    project = get_active_project(request, db, user)
    query = select(StockMovement).where(StockMovement.project_id == project.id)
    total = len(list(db.scalars(query)))
    items = list(
        db.scalars(
            query.options(selectinload(StockMovement.product))
            .order_by(StockMovement.created_at.desc())
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
        )
    )
    return render(
        request,
        "warehouse/movements.html",
        db,
        user,
        active_project=project,
        movements=items,
        total=total,
        page=page,
        per_page=PER_PAGE,
    )
