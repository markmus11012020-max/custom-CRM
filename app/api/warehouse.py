"""API склада и товаров."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession, Paging, paginate, require_edit, resolve_project
from app.models import Product, StockMovement
from app.schemas import (
    Page,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    StockMovementCreate,
    StockMovementRead,
)
from app.services.activity import log_activity
from app.services.stock import create_stock_movement, low_stock_products, stock_value

router = APIRouter(prefix="/api", tags=["warehouse"])


@router.get("/products", response_model=Page[ProductRead])
def list_products(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
    q: str = "",
    low_only: bool = False,
):
    project = resolve_project(request, db, user, project_id)
    query = select(Product).where(Product.project_id == project.id)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where(or_(Product.name.ilike(term), Product.sku.ilike(term)))
    if low_only:
        query = query.where(Product.stock_qty <= Product.min_stock)
    query = query.order_by(Product.name)
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("/products", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, request: Request, db: DbSession, user: CurrentUser):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    product = Product(
        project_id=project.id,
        sku=payload.sku,
        name=payload.name,
        unit=payload.unit,
        price=payload.price,
        cost=payload.cost,
        min_stock=payload.min_stock,
        is_active=payload.is_active,
    )
    db.add(product)
    db.flush()
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
    return product


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession, user: CurrentUser):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    from app.services.access import get_project_for_user

    get_project_for_user(db, product.project_id, user)
    return product


@router.put("/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, db: DbSession, user: CurrentUser):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    from app.services.access import get_project_for_user

    project = get_project_for_user(db, product.project_id, user)
    require_edit(db, project, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    return product


@router.delete("/products/{product_id}")
def deactivate_product(product_id: int, db: DbSession, user: CurrentUser):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    from app.services.access import get_project_for_user

    project = get_project_for_user(db, product.project_id, user)
    require_edit(db, project, user)
    product.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/stock/movements", response_model=Page[StockMovementRead])
def list_movements(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
    product_id: int | None = None,
):
    project = resolve_project(request, db, user, project_id)
    query = select(StockMovement).where(StockMovement.project_id == project.id)
    if product_id:
        query = query.where(StockMovement.product_id == product_id)
    query = query.order_by(StockMovement.created_at.desc())
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("/stock/movements", response_model=StockMovementRead, status_code=201)
def add_movement(payload: StockMovementCreate, request: Request, db: DbSession, user: CurrentUser):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    product = db.get(Product, payload.product_id)
    if product is None or product.project_id != project.id:
        raise HTTPException(status_code=400, detail="Товар не найден в проекте")
    movement = create_stock_movement(
        db,
        product=product,
        movement_type=payload.movement_type,
        quantity=payload.quantity,
        unit_cost=payload.unit_cost,
        reference=payload.reference,
        comment=payload.comment,
        user=user,
    )
    log_activity(
        db,
        action=f"stock_{movement.movement_type}",
        entity_type="product",
        entity_id=product.id,
        project_id=project.id,
        user_id=user.id,
        details=f"{product.name}: {movement.quantity}",
    )
    db.commit()
    return movement


@router.get("/stock/low", response_model=list[ProductRead])
def low_stock(request: Request, db: DbSession, user: CurrentUser, project_id: int | None = None):
    project = resolve_project(request, db, user, project_id)
    return low_stock_products(db, project.id)


@router.get("/stock/value")
def inventory_value(request: Request, db: DbSession, user: CurrentUser, project_id: int | None = None):
    project = resolve_project(request, db, user, project_id)
    return {"project_id": project.id, "value": str(stock_value(db, project.id))}
