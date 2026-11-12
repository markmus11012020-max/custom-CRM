"""Агрегаты для дашборда."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Client, Deal, Payment, Task
from app.services.accounting import summary
from app.services.stock import low_stock_products, stock_value


def _decimal(value) -> Decimal:  # type: ignore[no-untyped-def]
    return Decimal(str(value or 0))


def project_stats(db: Session, project_id: int) -> dict:
    now = datetime.now(UTC)
    today_start = datetime.combine(now.date(), time.min)
    today_end = today_start + timedelta(days=1)

    clients_total = int(
        db.scalar(select(func.count(Client.id)).where(Client.project_id == project_id)) or 0
    )
    clients_active = int(
        db.scalar(
            select(func.count(Client.id)).where(
                Client.project_id == project_id,
                Client.status == "active",
                Client.is_archived.is_(False),
            )
        )
        or 0
    )
    clients_new = int(
        db.scalar(
            select(func.count(Client.id)).where(
                Client.project_id == project_id,
                Client.status == "new",
                Client.is_archived.is_(False),
            )
        )
        or 0
    )

    deals_open = int(
        db.scalar(
            select(func.count(Deal.id)).where(
                Deal.project_id == project_id,
                Deal.stage.notin_(["won", "lost", "fulfilled"]),
            )
        )
        or 0
    )
    pipeline_value = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Deal.amount), 0)).where(
                Deal.project_id == project_id,
                Deal.stage.notin_(["lost", "fulfilled"]),
            )
        )
    )
    won_value = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Deal.amount), 0)).where(
                Deal.project_id == project_id, Deal.stage.in_(["won", "fulfilled"])
            )
        )
    )

    tasks_open = int(
        db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == project_id, Task.is_completed.is_(False)
            )
        )
        or 0
    )
    tasks_overdue = int(
        db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_completed.is_(False),
                Task.due_at.is_not(None),
                Task.due_at < now,
            )
        )
        or 0
    )
    tasks_today = int(
        db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_completed.is_(False),
                Task.due_at >= today_start,
                Task.due_at < today_end,
            )
        )
        or 0
    )

    payments_pending = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.project_id == project_id, Payment.status == "pending"
            )
        )
    )
    payments_paid = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.project_id == project_id, Payment.status == "paid"
            )
        )
    )

    finance = summary(db, project_id)
    low_stock = low_stock_products(db, project_id, limit=100)

    return {
        "clients_total": clients_total,
        "clients_active": clients_active,
        "clients_new": clients_new,
        "deals_open": deals_open,
        "pipeline_value": pipeline_value,
        "won_value": won_value,
        "tasks_open": tasks_open,
        "tasks_overdue": tasks_overdue,
        "tasks_today": tasks_today,
        "payments_pending": payments_pending,
        "payments_paid": payments_paid,
        "income": finance["income"],
        "expense": finance["expense"],
        "profit": finance["profit"],
        "stock_value": stock_value(db, project_id),
        "low_stock_count": len(low_stock),
    }


def funnel(db: Session, project_id: int) -> list[dict]:
    rows = db.execute(
        select(
            Deal.stage,
            func.count(Deal.id),
            func.coalesce(func.sum(Deal.amount), 0),
        )
        .where(Deal.project_id == project_id)
        .group_by(Deal.stage)
    ).all()
    data = {stage: {"count": 0, "amount": Decimal("0")} for stage in (
        "new", "negotiation", "proposal", "won", "lost", "fulfilled"
    )}
    for stage, count, amount in rows:
        data[stage] = {"count": int(count), "amount": _decimal(amount)}
    labels = {
        "new": "Новые",
        "negotiation": "Переговоры",
        "proposal": "Предложение",
        "won": "Выиграны",
        "lost": "Проиграны",
        "fulfilled": "Выполнены",
    }
    return [
        {"stage": stage, "label": labels[stage], **values}
        for stage, values in data.items()
    ]


def open_tasks(db: Session, project_id: int, limit: int = 10) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id, Task.is_completed.is_(False))
            .order_by(Task.due_at.is_(None), Task.due_at, Task.priority.desc())
            .limit(limit)
        )
    )


def recent_deals(db: Session, project_id: int, limit: int = 6) -> list[Deal]:
    return list(
        db.scalars(
            select(Deal)
            .where(Deal.project_id == project_id)
            .order_by(Deal.created_at.desc())
            .limit(limit)
        )
    )


def recent_clients(db: Session, project_id: int, limit: int = 6) -> list[Client]:
    return list(
        db.scalars(
            select(Client)
            .where(Client.project_id == project_id)
            .order_by(Client.created_at.desc())
            .limit(limit)
        )
    )
