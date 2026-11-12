"""API управленческого учёта."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Paging, paginate, require_edit, resolve_project
from app.models import Transaction
from app.schemas import Page, TransactionCreate, TransactionRead, TransactionUpdate
from app.services.accounting import create_transaction, summary
from app.services.activity import log_activity

router = APIRouter(prefix="/api", tags=["accounting"])


@router.get("/transactions", response_model=Page[TransactionRead])
def list_transactions(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
    type_filter: str | None = None,
    category: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    project = resolve_project(request, db, user, project_id)
    query = select(Transaction).where(Transaction.project_id == project.id)
    if type_filter:
        query = query.where(Transaction.type == type_filter)
    if category:
        query = query.where(Transaction.category == category)
    if date_from:
        query = query.where(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.where(Transaction.transaction_date <= date_to)
    query = query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("/transactions", response_model=TransactionRead, status_code=201)
def add_transaction(payload: TransactionCreate, request: Request, db: DbSession, user: CurrentUser):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    tx = create_transaction(
        db,
        project=project,
        type=payload.type,
        category=payload.category,
        amount=payload.amount,
        transaction_date=payload.transaction_date,
        description=payload.description,
        user=user,
        deal_id=payload.deal_id,
    )
    log_activity(
        db,
        action=f"transaction_{payload.type}",
        entity_type="transaction",
        entity_id=tx.id,
        project_id=project.id,
        user_id=user.id,
        details=f"{tx.amount} {tx.currency}",
    )
    db.commit()
    return tx


@router.put("/transactions/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int, payload: TransactionUpdate, db: DbSession, user: CurrentUser
):
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Транзакция не найдена")
    require_edit(db, tx.project, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tx, field, value)
    db.commit()
    return tx


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: DbSession, user: CurrentUser):
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Транзакция не найдена")
    require_edit(db, tx.project, user)
    db.delete(tx)
    db.commit()
    return {"ok": True}


@router.get("/accounting/summary")
def accounting_summary(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    project_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    project = resolve_project(request, db, user, project_id)
    data = summary(db, project.id, date_from, date_to)
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in data.items()}
