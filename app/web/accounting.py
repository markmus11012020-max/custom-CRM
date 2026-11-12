"""Веб-раздел управленческого учёта."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Transaction
from app.services.access import get_active_project, get_project_for_user, require_project_edit
from app.services.accounting import categories, create_transaction, summary
from app.services.activity import log_activity
from app.web.utils import flash, render

router = APIRouter(prefix="/accounting", tags=["web-accounting"])
PER_PAGE = 30


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today()


@router.get("")
def accounting(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    type_filter: str = "",
    category: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
):
    project = get_active_project(request, db, user)
    query = select(Transaction).where(Transaction.project_id == project.id)
    if type_filter:
        query = query.where(Transaction.type == type_filter)
    if category:
        query = query.where(Transaction.category == category)
    if date_from:
        query = query.where(Transaction.transaction_date >= _date(date_from))
    if date_to:
        query = query.where(Transaction.transaction_date <= _date(date_to))
    total = len(list(db.scalars(query)))
    items = list(
        db.scalars(
            query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
        )
    )
    return render(
        request,
        "accounting/list.html",
        db,
        user,
        active_project=project,
        transactions=items,
        categories=categories(db, project.id),
        summary=summary(db, project.id),
        total=total,
        page=page,
        per_page=PER_PAGE,
        type_filter=type_filter,
        category=category,
        date_from=date_from,
        date_to=date_to,
        today=date.today(),
    )


@router.get("/new")
def new_transaction(request: Request, db: DbSession, user: CurrentUser):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    return render(
        request,
        "accounting/form.html",
        db,
        user,
        active_project=project,
        transaction=None,
        categories=categories(db, project.id),
        form_action="/accounting/new",
        title="Новая операция",
        today=date.today(),
    )


@router.post("/new")
def create_transaction_web(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    type: str = Form("income"),
    category: str = Form(""),
    amount: str = Form("0"),
    transaction_date: str = Form(""),
    description: str = Form(""),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    try:
        tx = create_transaction(
            db,
            project=project,
            type=type,
            category=category,
            amount=_decimal(amount),
            transaction_date=_date(transaction_date),
            description=description,
            user=user,
        )
        log_activity(
            db,
            action=f"transaction_{type}",
            entity_type="transaction",
            entity_id=tx.id,
            project_id=project.id,
            user_id=user.id,
            details=f"{tx.amount} {tx.currency}",
        )
        db.commit()
        flash(request, "Операция добавлена")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Ошибка: {exc}", "error")
    return RedirectResponse("/accounting", status_code=303)


@router.get("/{transaction_id}/edit")
def edit_transaction(transaction_id: int, request: Request, db: DbSession, user: CurrentUser):
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Операция не найдена")
    project = get_project_for_user(db, tx.project_id, user)
    require_project_edit(db, project.id, user)
    return render(
        request,
        "accounting/form.html",
        db,
        user,
        active_project=project,
        transaction=tx,
        categories=categories(db, project.id),
        form_action=f"/accounting/{tx.id}/edit",
        title="Редактирование операции",
        today=date.today(),
    )


@router.post("/{transaction_id}/edit")
def update_transaction_web(
    transaction_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    type: str = Form("income"),
    category: str = Form(""),
    amount: str = Form("0"),
    transaction_date: str = Form(""),
    description: str = Form(""),
):
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Операция не найдена")
    project = get_project_for_user(db, tx.project_id, user)
    require_project_edit(db, project.id, user)
    tx.type = type
    tx.category = category
    tx.amount = _decimal(amount)
    tx.transaction_date = _date(transaction_date)
    tx.description = description
    db.commit()
    flash(request, "Операция обновлена")
    return RedirectResponse("/accounting", status_code=303)


@router.post("/{transaction_id}/delete")
def delete_transaction_web(transaction_id: int, request: Request, db: DbSession, user: CurrentUser):
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Операция не найдена")
    project = get_project_for_user(db, tx.project_id, user)
    require_project_edit(db, project.id, user)
    db.delete(tx)
    db.commit()
    flash(request, "Операция удалена")
    return RedirectResponse("/accounting", status_code=303)
