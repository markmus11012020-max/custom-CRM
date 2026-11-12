"""API платежей и Robokassa."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Paging, paginate, require_edit, resolve_project
from app.models import Payment
from app.schemas import Page, PaymentCreate, PaymentRead, PaymentUpdate
from app.services.access import get_project_for_user
from app.services.activity import log_activity
from app.services.payments import create_payment, mark_paid, refund_payment

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("", response_model=Page[PaymentRead])
def list_payments(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
    status_filter: str | None = None,
    client_id: int | None = None,
):
    project = resolve_project(request, db, user, project_id)
    query = select(Payment).where(Payment.project_id == project.id)
    if status_filter:
        query = query.where(Payment.status == status_filter)
    if client_id:
        query = query.where(Payment.client_id == client_id)
    query = query.order_by(Payment.created_at.desc())
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("", response_model=PaymentRead, status_code=201)
def add_payment(payload: PaymentCreate, request: Request, db: DbSession, user: CurrentUser):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    payment = create_payment(
        db,
        project=project,
        amount=payload.amount,
        currency=payload.currency,
        client_id=payload.client_id,
        deal_id=payload.deal_id,
        description=payload.description,
        method=payload.method,
        user=user,
        settings=request.app.state.settings,
    )
    log_activity(
        db,
        action="payment_created",
        entity_type="payment",
        entity_id=payment.id,
        project_id=project.id,
        user_id=user.id,
        details=f"{payment.amount} {payment.currency}",
    )
    db.commit()
    return payment


@router.get("/{payment_id}", response_model=PaymentRead)
def get_payment(payment_id: int, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    get_project_for_user(db, payment.project_id, user)
    return payment


@router.put("/{payment_id}", response_model=PaymentRead)
def update_payment(payment_id: int, payload: PaymentUpdate, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    require_edit(db, payment.project, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(payment, field, value)
    db.commit()
    return payment


@router.post("/{payment_id}/mark-paid", response_model=PaymentRead)
def mark_payment_paid(payment_id: int, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    require_edit(db, payment.project, user)
    mark_paid(db, payment, user)
    log_activity(
        db,
        action="payment_paid",
        entity_type="payment",
        entity_id=payment.id,
        project_id=payment.project_id,
        user_id=user.id,
        details=f"{payment.amount} {payment.currency}",
    )
    db.commit()
    return payment


@router.post("/{payment_id}/refund", response_model=PaymentRead)
def refund(payment_id: int, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    require_edit(db, payment.project, user)
    if payment.status != "paid":
        raise HTTPException(status_code=400, detail="Возврат возможен только для оплаченного счёта")
    refund_payment(db, payment, user)
    log_activity(
        db,
        action="payment_refunded",
        entity_type="payment",
        entity_id=payment.id,
        project_id=payment.project_id,
        user_id=user.id,
    )
    db.commit()
    return payment


@router.get("/{payment_id}/link")
def payment_link(payment_id: int, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    get_project_for_user(db, payment.project_id, user)
    return {
        "payment_id": payment.id,
        "status": payment.status,
        "link": payment.robokassa_link,
        "inv_id": payment.inv_id,
    }
