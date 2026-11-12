"""Управленческий учёт: доходы, расходы, прибыль."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Payment, Project, Transaction, User


def _as_decimal(value: Decimal | float | int | None) -> Decimal:
    return Decimal(str(value or 0))


def create_transaction(
    db: Session,
    *,
    project: Project,
    type: str,
    category: str,
    amount: Decimal,
    transaction_date: date,
    description: str = "",
    user: User | None = None,
    payment_id: int | None = None,
    deal_id: int | None = None,
) -> Transaction:
    if payment_id is not None:
        existing = db.scalar(
            select(Transaction).where(
                Transaction.payment_id == payment_id, Transaction.type == type
            )
        )
        if existing is not None:
            return existing
    tx = Transaction(
        project_id=project.id,
        type=type,
        category=category[:120],
        amount=_as_decimal(amount),
        currency=project.currency,
        transaction_date=transaction_date,
        description=description[:255],
        payment_id=payment_id,
        deal_id=deal_id,
        created_by_id=user.id if user else None,
    )
    db.add(tx)
    db.flush()
    return tx


def payment_income(db: Session, payment: Payment, user: User | None = None) -> Transaction:
    paid_date = payment.paid_at.date() if payment.paid_at else date.today()
    return create_transaction(
        db,
        project=payment.project,
        type="income",
        category="Оплата по счёту",
        amount=payment.amount,
        transaction_date=paid_date,
        description=payment.description or f"Платёж №{payment.id}",
        user=user,
        payment_id=payment.id,
        deal_id=payment.deal_id,
    )


def payment_refund(db: Session, payment: Payment, user: User | None = None) -> Transaction:
    return create_transaction(
        db,
        project=payment.project,
        type="expense",
        category="Возврат по счёту",
        amount=payment.amount,
        transaction_date=date.today(),
        description=f"Возврат по платежу №{payment.id}",
        user=user,
        payment_id=payment.id,
        deal_id=payment.deal_id,
    )


def summary(
    db: Session,
    project_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Decimal | int]:
    query_income = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.project_id == project_id, Transaction.type == "income"
    )
    query_expense = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.project_id == project_id, Transaction.type == "expense"
    )
    query_count = select(func.count(Transaction.id)).where(Transaction.project_id == project_id)
    if date_from:
        query_income = query_income.where(Transaction.transaction_date >= date_from)
        query_expense = query_expense.where(Transaction.transaction_date >= date_from)
        query_count = query_count.where(Transaction.transaction_date >= date_from)
    if date_to:
        query_income = query_income.where(Transaction.transaction_date <= date_to)
        query_expense = query_expense.where(Transaction.transaction_date <= date_to)
        query_count = query_count.where(Transaction.transaction_date <= date_to)

    income = _as_decimal(db.scalar(query_income))
    expense = _as_decimal(db.scalar(query_expense))
    count = int(db.scalar(query_count) or 0)
    return {
        "income": income,
        "expense": expense,
        "profit": income - expense,
        "count": count,
    }


def monthly_series(db: Session, project_id: int, months: int = 6) -> list[dict]:
    """Диалект-независимая агрегация по месяцам."""
    rows = db.execute(
        select(Transaction.transaction_date, Transaction.type, Transaction.amount).where(
            Transaction.project_id == project_id
        )
    ).all()
    data: dict[str, dict[str, Decimal]] = {}
    for tx_date, tx_type, amount in rows:
        if tx_date is None:
            continue
        month = tx_date.strftime("%Y-%m")
        data.setdefault(month, {"income": Decimal("0"), "expense": Decimal("0")})
        data[month][tx_type] = data[month].get(tx_type, Decimal("0")) + _as_decimal(amount)
    result = []
    for month in sorted(data)[-months:]:
        item = data[month]
        result.append(
            {
                "month": month,
                "income": item["income"],
                "expense": item["expense"],
                "profit": item["income"] - item["expense"],
            }
        )
    return result


def categories(db: Session, project_id: int) -> list[str]:
    rows = db.scalars(
        select(Transaction.category)
        .where(Transaction.project_id == project_id, Transaction.category != "")
        .distinct()
        .order_by(Transaction.category)
    )
    return list(rows)


def today_utc() -> datetime:
    return datetime.now(UTC)
