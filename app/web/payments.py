"""Веб-раздел платежей и публичные маршруты Robokassa."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models import Client, Deal, Payment
from app.services.access import get_active_project, get_project_for_user, require_project_edit
from app.services.activity import log_activity
from app.services.payments import create_payment, mark_paid, process_robokassa_result, refund_payment
from app.web.utils import flash, render

router = APIRouter(prefix="/payments", tags=["web-payments"])
PER_PAGE = 20


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


# ---------------------------------------------------------------------------
# Robokassa public endpoints (без авторизации)
# ---------------------------------------------------------------------------
@router.api_route("/robokassa/result", methods=["GET", "POST"])
async def robokassa_result(request: Request):
    form = await request.form() if request.method == "POST" else request.query_params
    out_sum = str(form.get("OutSum", ""))
    inv_id = str(form.get("InvId", ""))
    signature = str(form.get("SignatureValue", ""))
    try:
        db_factory = request.app.state.db
        with db_factory.session_scope() as db:
            payment = process_robokassa_result(
                db,
                out_sum=out_sum,
                inv_id=inv_id,
                signature=signature,
                settings=request.app.state.settings,
            )
            log_activity(
                db,
                action="payment_paid",
                entity_type="payment",
                entity_id=payment.id,
                project_id=payment.project_id,
                details=f"Robokassa: {out_sum}",
            )
        return PlainTextResponse(f"OK{inv_id}")
    except Exception as exc:  # noqa: BLE001
        return PlainTextResponse(f"ERROR: {exc}", status_code=400)


@router.get("/robokassa/success")
def robokassa_success(request: Request, InvId: str = "", OutSum: str = ""):
    body = f"""
    <html><head><meta charset="utf-8"><title>Оплата</title>
    <style>body{{font-family:Arial;background:#F7F8FC;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
    .card{{background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:32px;max-width:520px;box-shadow:0 18px 50px -28px rgba(15,23,42,.22)}}
    h1{{color:#0D9488;margin-top:0}} a{{color:#4338CA}}</style></head>
    <body><div class="card"><h1>Оплата принята</h1>
    <p>Счёт №{InvId} на сумму {OutSum} ₽. Статус будет подтверждён уведомлением Robokassa.</p>
    <p><a href="/payments">Перейти к платежам</a></p></div></body></html>
    """
    return HTMLResponse(body)


@router.get("/robokassa/fail")
def robokassa_fail(request: Request, InvId: str = ""):
    body = f"""
    <html><head><meta charset="utf-8"><title>Оплата</title>
    <style>body{{font-family:Arial;background:#F7F8FC;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
    .card{{background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:32px;max-width:520px;box-shadow:0 18px 50px -28px rgba(15,23,42,.22)}}
    h1{{color:#DC2626;margin-top:0}} a{{color:#4338CA}}</style></head>
    <body><div class="card"><h1>Оплата не завершена</h1>
    <p>Счёт №{InvId} не был оплачен. Можно вернуться и попробовать снова.</p>
    <p><a href="/payments">Перейти к платежам</a></p></div></body></html>
    """
    return HTMLResponse(body)


# ---------------------------------------------------------------------------
# Личный кабинет платежей
# ---------------------------------------------------------------------------
@router.get("")
def list_payments(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    status_filter: str = "",
    page: int = 1,
):
    project = get_active_project(request, db, user)
    query = select(Payment).where(Payment.project_id == project.id)
    if status_filter:
        query = query.where(Payment.status == status_filter)
    total = len(list(db.scalars(query)))
    payments = list(
        db.scalars(
            query.options(selectinload(Payment.client), selectinload(Payment.deal))
            .order_by(Payment.created_at.desc())
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
        )
    )
    return render(
        request,
        "payments/list.html",
        db,
        user,
        active_project=project,
        payments=payments,
        total=total,
        page=page,
        per_page=PER_PAGE,
        status_filter=status_filter,
    )


@router.get("/new")
def new_payment(request: Request, db: DbSession, user: CurrentUser):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    clients = list(
        db.scalars(
            select(Client)
            .where(Client.project_id == project.id, Client.is_archived.is_(False))
            .order_by(Client.name)
        )
    )
    deals = list(
        db.scalars(
            select(Deal).where(Deal.project_id == project.id).order_by(Deal.created_at.desc()).limit(200)
        )
    )
    return render(
        request,
        "payments/form.html",
        db,
        user,
        active_project=project,
        clients=clients,
        deals=deals,
        payment=None,
        form_action="/payments/new",
        title="Новый счёт",
    )


@router.post("/new")
def create_payment_web(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    amount: str = Form("0"),
    client_id: str = Form(""),
    deal_id: str = Form(""),
    description: str = Form(""),
    method: str = Form("manual"),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    try:
        payment = create_payment(
            db,
            project=project,
            amount=_decimal(amount),
            client_id=int(client_id) if client_id.isdigit() else None,
            deal_id=int(deal_id) if deal_id.isdigit() else None,
            description=description,
            method=method,
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
        flash(request, "Счёт создан")
        return RedirectResponse(f"/payments/{payment.id}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Не удалось создать счёт: {exc}", "error")
        return RedirectResponse("/payments/new", status_code=303)


@router.get("/{payment_id}")
def payment_detail(payment_id: int, request: Request, db: DbSession, user: CurrentUser):
    payment = db.scalar(
        select(Payment)
        .options(selectinload(Payment.client), selectinload(Payment.deal))
        .where(Payment.id == payment_id)
    )
    if payment is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Платёж не найден")
    project = get_project_for_user(db, payment.project_id, user)
    return render(
        request,
        "payments/detail.html",
        db,
        user,
        active_project=project,
        payment=payment,
    )


@router.post("/{payment_id}/mark-paid")
def mark_paid_web(payment_id: int, request: Request, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Платёж не найден")
    project = get_project_for_user(db, payment.project_id, user)
    require_project_edit(db, project.id, user)
    mark_paid(db, payment, user)
    log_activity(
        db,
        action="payment_paid",
        entity_type="payment",
        entity_id=payment.id,
        project_id=project.id,
        user_id=user.id,
        details=f"{payment.amount} {payment.currency}",
    )
    db.commit()
    flash(request, "Платёж отмечен оплаченным")
    return RedirectResponse(f"/payments/{payment.id}", status_code=303)


@router.post("/{payment_id}/refund")
def refund_web(payment_id: int, request: Request, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Платёж не найден")
    project = get_project_for_user(db, payment.project_id, user)
    require_project_edit(db, project.id, user)
    if payment.status != "paid":
        flash(request, "Возврат возможен только для оплаченного счёта", "error")
        return RedirectResponse(f"/payments/{payment.id}", status_code=303)
    refund_payment(db, payment, user)
    db.commit()
    flash(request, "Платёж возвращён")
    return RedirectResponse(f"/payments/{payment.id}", status_code=303)


@router.post("/{payment_id}/delete")
def delete_payment(payment_id: int, request: Request, db: DbSession, user: CurrentUser):
    payment = db.get(Payment, payment_id)
    if payment is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Платёж не найден")
    project = get_project_for_user(db, payment.project_id, user)
    require_project_edit(db, project.id, user)
    db.delete(payment)
    db.commit()
    flash(request, "Платёж удалён")
    return RedirectResponse("/payments", status_code=303)


@router.get("/{payment_id}/invoice")
def invoice(payment_id: int, request: Request, db: DbSession, user: CurrentUser):
    payment = db.scalar(
        select(Payment)
        .options(selectinload(Payment.client), selectinload(Payment.deal))
        .where(Payment.id == payment_id)
    )
    if payment is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Платёж не найден")
    project = get_project_for_user(db, payment.project_id, user)
    return render(
        request,
        "payments/invoice.html",
        db,
        user,
        active_project=project,
        payment=payment,
    )
