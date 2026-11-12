"""Складские операции и остатки."""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, StockMovement, User


def _as_decimal(value: Decimal | float | int | None) -> Decimal:
    return Decimal(str(value or 0))


def create_stock_movement(
    db: Session,
    *,
    product: Product,
    movement_type: str,
    quantity: Decimal,
    unit_cost: Decimal,
    reference: str = "",
    comment: str = "",
    user: User | None = None,
) -> StockMovement:
    if movement_type not in {"in", "out", "adjust"}:
        raise HTTPException(status_code=400, detail="Недопустимый тип складской операции")
    quantity = _as_decimal(quantity)
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Количество должно быть больше нуля")

    old_qty = _as_decimal(product.stock_qty)
    old_cost = _as_decimal(product.cost)
    unit_cost = _as_decimal(unit_cost) if unit_cost else old_cost

    if movement_type == "in":
        new_qty = old_qty + quantity
        if new_qty > 0 and unit_cost > 0:
            product.cost = ((old_qty * old_cost) + (quantity * unit_cost)) / new_qty
        product.stock_qty = new_qty
    elif movement_type == "out":
        if old_qty < quantity:
            raise HTTPException(
                status_code=409,
                detail=f"Недостаточно товара «{product.name}»: остаток {old_qty}, нужно {quantity}",
            )
        product.stock_qty = old_qty - quantity
    else:  # adjust
        product.stock_qty = quantity
        if unit_cost > 0:
            product.cost = unit_cost

    movement = StockMovement(
        project_id=product.project_id,
        product_id=product.id,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=unit_cost,
        reference=reference[:120],
        comment=comment[:255],
        created_by_id=user.id if user else None,
    )
    db.add(movement)
    db.flush()
    return movement


def stock_value(db: Session, project_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(Product.stock_qty * Product.cost), 0)).where(
            Product.project_id == project_id, Product.is_active.is_(True)
        )
    )
    return _as_decimal(value)


def low_stock_products(db: Session, project_id: int, limit: int = 100) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .where(
                Product.project_id == project_id,
                Product.is_active.is_(True),
                Product.stock_qty <= Product.min_stock,
            )
            .order_by((Product.stock_qty - Product.min_stock).asc(), Product.name)
            .limit(limit)
        )
    )


def product_options(db: Session, project_id: int) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .where(Product.project_id == project_id, Product.is_active.is_(True))
            .order_by(Product.name)
        )
    )
