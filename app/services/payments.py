"""Платежи и интеграция Robokassa."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Client, Deal, Payment, Project, User


def _money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def robokassa_payment_signature(login: str, out_sum: str, inv_id: str, password1: str) -> str:
    raw = f"{login}:{out_sum}:{inv_id}:{password1}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def robokassa_result_signature(out_sum: str, inv_id: str, password2: str) -> str:
    raw = f"{out_sum}:{inv_id}:{password2}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_robokassa_link(
    settings: Settings,
    amount: Decimal | float | int,
    inv_id: str,
    description: str = "Оплата услуг",
) -> str:
    out_sum = f"{_money(amount):.2f}"
    signature = robokassa_payment_signature(
        settings.robokassa_merchant_login,
        out_sum,
        str(inv_id),
        settings.robokassa_password1,
    )
    params = {
        "MerchantLogin": settings.robokassa_merchant_login,
        "OutSum": out_sum,
        "InvId": str(inv_id),
        "Description": description or "Оплата услуг",
        "SignatureValue": signature,
    }
    if settings.robokassa_test_mode:
        params["IsTest"] = "1"
    return "https://auth.robokassa.ru/Merchant/Index.aspx?" + urlencode(params)


def verify_robokassa_result(
    settings: Settings, out_sum: str, inv_id: str, signature: str
) -> bool:
    expected = robokassa_result_signature(out_sum, inv_id, settings.robokassa_password2)
    import hmac

    return hmac.compare_digest(expected.lower(), (signature or "").lower())


def create_payment(
    db: Session,
    *,
    project: Project,
    amount: Decimal,
    currency: str = "RUB",
    client_id: int | None = None,
    deal_id: int | None = None,
    description: str = "",
    method: str = "manual",
    user: User | None = None,
    settings: Settings | None = None,
) -> Payment:
    amount = _money(amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма платежа должна быть больше нуля")
    if client_id is not None:
        client = db.get(Client, client_id)
        if client is None or client.project_id != project.id:
            raise HTTPException(status_code=400, detail="Клиент не найден в проекте")
    if deal_id is not None:
        deal = db.get(Deal, deal_id)
        if deal is None or deal.project_id != project.id:
            raise HTTPException(status_code=400, detail="Сделка не найдена в проекте")

    payment = Payment(
        project_id=project.id,
        client_id=client_id,
        deal_id=deal_id,
        amount=amount,
        currency=currency or project.currency,
        status="pending",
        method=method,
        description=description[:255],
    )
    db.add(payment)
    db.flush()
    if method == "robokassa":
        payment.inv_id = str(payment.id)
        settings = settings or get_settings()
        payment.robokassa_link = build_robokassa_link(
            settings, payment.amount, payment.inv_id, payment.description or "Оплата услуг"
        )
    db.flush()
    return payment


def mark_paid(
    db: Session,
    payment: Payment,
    user: User | None = None,
    *,
    notify: bool = True,
) -> Payment:
    if payment.status == "paid":
        return payment
    payment.status = "paid"
    payment.paid_at = datetime.now(UTC)
    db.flush()

    from app.services.accounting import payment_income

    payment_income(db, payment, user)

    if notify:
        try:
            from app.services.notifications import notify_project_managers

            notify_project_managers(
                db,
                payment.project,
                subject=f"Оплата получена: {payment.amount:.2f} {payment.currency}",
                body=(
                    f"Платёж №{payment.id} по проекту «{payment.project.name}» оплачен. "
                    f"Сумма: {payment.amount:.2f} {payment.currency}."
                ),
                dedupe_key=f"payment-paid:{payment.id}",
            )
        except Exception:
            pass
    return payment


def refund_payment(db: Session, payment: Payment, user: User | None = None) -> Payment:
    if payment.status == "refunded":
        return payment
    payment.status = "refunded"
    db.flush()
    from app.services.accounting import payment_refund

    payment_refund(db, payment, user)
    return payment


def process_robokassa_result(
    db: Session,
    *,
    out_sum: str,
    inv_id: str,
    signature: str,
    settings: Settings | None = None,
) -> Payment:
    settings = settings or get_settings()
    if not verify_robokassa_result(settings, out_sum, inv_id, signature):
        raise HTTPException(status_code=403, detail="Неверная подпись Robokassa")
    payment = db.scalar(select(Payment).where(Payment.inv_id == str(inv_id)))
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    try:
        amount = _money(out_sum)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Некорректная сумма") from exc
    if amount != _money(payment.amount):
        raise HTTPException(status_code=409, detail="Сумма не совпадает с платежом")
    return mark_paid(db, payment, None)
