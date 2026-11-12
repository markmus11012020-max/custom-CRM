"""Отчёты CRM: сбор данных, Google Sheets, AI-резюме, CSV и расписания."""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from croniter import croniter
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_logger, get_settings
from app.google import GoogleIntegrationError
from app.google.sheets import GoogleSheetsClient
from app.models import (
    Client,
    Deal,
    Payment,
    Product,
    Project,
    Report,
    ReportSchedule,
    Task,
    Transaction,
    User,
)
from app.services.accounting import summary as accounting_summary
from app.services.ai import AITunnelClient
from app.services.dashboard import funnel, project_stats
from app.services.notifications import enqueue, notify_user
from app.services.stock import low_stock_products

LOGGER = get_logger("reports")

REPORT_TYPES = {
    "summary": "Сводка CRM",
    "sales": "Продажи и воронка",
    "finance": "Финансы",
    "warehouse": "Склад",
    "tasks": "Задачи",
}

STAGE_LABELS = {
    "new": "Новые",
    "negotiation": "Переговоры",
    "proposal": "Предложение",
    "won": "Выиграны",
    "lost": "Проиграны",
    "fulfilled": "Выполнены",
}

STATUS_LABELS = {
    "new": "Новый",
    "active": "Активный",
    "inactive": "Неактивный",
    "archived": "Архив",
    "pending": "Ожидает",
    "paid": "Оплачен",
    "failed": "Ошибка",
    "refunded": "Возврат",
    "canceled": "Отменён",
}


def money(value: Decimal | float | int | None) -> str:
    try:
        amount = Decimal(str(value or 0))
        return f"{amount:,.2f} ₽".replace(",", " ").replace(".", ",")
    except Exception:  # noqa: BLE001
        return "0,00 ₽"


def period_label(date_from: date | None, date_to: date | None) -> str:
    if date_from and date_to:
        return f"{date_from.strftime('%d.%m.%Y')} — {date_to.strftime('%d.%m.%Y')}"
    if date_from:
        return f"с {date_from.strftime('%d.%m.%Y')}"
    if date_to:
        return f"по {date_to.strftime('%d.%m.%Y')}"
    return "за всё время"


def _date_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(date_from, time.min, tzinfo=UTC) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC) if date_to else None
    return start, end


def build_report_context(
    db: Session,
    project: Project,
    report_type: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    stats = project_stats(db, project.id)
    finance = accounting_summary(db, project.id, date_from, date_to)
    context: dict[str, Any] = {
        "project": project.name,
        "report_type": report_type,
        "report_title": REPORT_TYPES.get(report_type, "Отчёт"),
        "period": period_label(date_from, date_to),
        "kpis": [
            {"name": "Клиенты", "value": str(stats["clients_total"])},
            {"name": "Сделки в работе", "value": str(stats["deals_open"])},
            {"name": "Сумма воронки", "value": money(stats["pipeline_value"])},
            {"name": "Выручка", "value": money(finance["income"])},
            {"name": "Расходы", "value": money(finance["expense"])},
            {"name": "Прибыль", "value": money(finance["profit"])},
        ],
        "income": money(finance["income"]),
        "expense": money(finance["expense"]),
        "profit": money(finance["profit"]),
        "tables": [],
        "chart": None,
    }

    start, end = _date_bounds(date_from, date_to)
    deal_query = (
        select(Deal)
        .options(selectinload(Deal.client))
        .where(Deal.project_id == project.id)
        .order_by(Deal.created_at.desc())
    )
    if start:
        deal_query = deal_query.where(Deal.created_at >= start)
    if end:
        deal_query = deal_query.where(Deal.created_at < end)
    deals = list(db.scalars(deal_query.limit(100)))

    task_query = (
        select(Task)
        .options(selectinload(Task.client), selectinload(Task.deal))
        .where(Task.project_id == project.id)
        .order_by(Task.due_at.is_(None), Task.due_at)
    )
    if start:
        task_query = task_query.where(Task.due_at >= start)
    if end:
        task_query = task_query.where(Task.due_at < end)
    tasks = list(db.scalars(task_query.limit(100)))

    if report_type in {"summary", "sales"}:
        funnel_rows = [
            [item["label"], float(item["amount"]), item["count"]] for item in funnel(db, project.id)
        ]
        context["tables"].append(
            {
                "title": "Воронка продаж",
                "headers": ["Этап", "Сумма", "Количество"],
                "rows": funnel_rows,
                "money_columns": [1],
            }
        )
        context["chart"] = {
            "title": "Сумма по этапам воронки",
            "categories": [row[0] for row in funnel_rows],
            "values": [row[1] for row in funnel_rows],
        }
        context["tables"].append(
            {
                "title": "Последние сделки",
                "headers": ["Сделка", "Клиент", "Этап", "Сумма", "Тип"],
                "rows": [
                    [
                        deal.title,
                        deal.client.name if deal.client else "—",
                        STAGE_LABELS.get(deal.stage, deal.stage),
                        float(deal.amount),
                        "Заказ" if deal.kind == "order" else "Сделка",
                    ]
                    for deal in deals[:20]
                ],
                "money_columns": [3],
            }
        )

    if report_type in {"summary", "finance"}:
        transactions = list(
            db.scalars(
                select(Transaction)
                .where(Transaction.project_id == project.id)
                .order_by(Transaction.transaction_date.desc())
                .limit(50)
            )
        )
        context["tables"].append(
            {
                "title": "Финансовые операции",
                "headers": ["Дата", "Тип", "Категория", "Сумма", "Описание"],
                "rows": [
                    [
                        tx.transaction_date.strftime("%d.%m.%Y"),
                        "Доход" if tx.type == "income" else "Расход",
                        tx.category,
                        float(tx.amount),
                        tx.description,
                    ]
                    for tx in transactions
                ],
                "money_columns": [3],
            }
        )

    if report_type in {"summary", "warehouse"}:
        products = list(
            db.scalars(
                select(Product)
                .where(Product.project_id == project.id)
                .order_by(Product.name)
                .limit(100)
            )
        )
        context["tables"].append(
            {
                "title": "Складские остатки",
                "headers": ["Товар", "SKU", "Остаток", "Мин. остаток", "Себестоимость", "Цена"],
                "rows": [
                    [
                        product.name,
                        product.sku,
                        float(product.stock_qty),
                        float(product.min_stock),
                        float(product.cost),
                        float(product.price),
                    ]
                    for product in products
                ],
                "money_columns": [4, 5],
            }
        )
        context["tables"].append(
            {
                "title": "Товары ниже минимального остатка",
                "headers": ["Товар", "Остаток", "Минимум", "Единица"],
                "rows": [
                    [product.name, float(product.stock_qty), float(product.min_stock), product.unit]
                    for product in low_stock_products(db, project.id)
                ],
                "money_columns": [],
            }
        )

    if report_type in {"summary", "tasks"}:
        context["tables"].append(
            {
                "title": "Задачи",
                "headers": ["Задача", "Клиент", "Сделка", "Приоритет", "Срок", "Статус"],
                "rows": [
                    [
                        task.title,
                        task.client.name if task.client else "—",
                        task.deal.title if task.deal else "—",
                        task.priority,
                        task.due_at.strftime("%d.%m.%Y %H:%M") if task.due_at else "—",
                        "Выполнена" if task.is_completed else "Открыта",
                    ]
                    for task in tasks[:50]
                ],
                "money_columns": [],
            }
        )

    return context


def build_sheet_rows(context: dict[str, Any]) -> tuple[list[list[Any]], dict[str, int]]:
    columns = 6
    rows: list[list[Any]] = []

    def add(row: list[Any]) -> None:
        rows.append(list(row) + [""] * (columns - len(row)))

    add([context["report_title"], "", "", "", "", ""])
    add([f"Проект: {context['project']}", f"Период: {context['period']}", "", "", "", ""])
    add([""])
    add(["Ключевые показатели", "Значение", "", "", "", ""])
    for item in context["kpis"]:
        add([item["name"], item["value"]])

    chart_start = 0
    chart_end = 0
    for table in context["tables"]:
        add([""])
        add([table["title"], "", "", "", "", ""])
        add(list(table["headers"]))
        header_index = len(rows)
        for row in table["rows"]:
            formatted = []
            for index, value in enumerate(row):
                if index in table.get("money_columns", []) and isinstance(value, (int, float, Decimal)):
                    formatted.append(float(value))
                else:
                    formatted.append(value)
            add(formatted)
        if table["title"] == "Воронка продаж":
            chart_start = header_index
            chart_end = len(rows)

    add([""])
    add(["Аналитическое резюме", "", "", "", "", ""])
    summary = context.get("summary", "")
    for line in _wrap_lines(summary, 110):
        add([line])

    meta = {
        "header_row": 4,
        "last_row": len(rows),
        "columns": columns,
        "chart_start": chart_start,
        "chart_end": chart_end,
    }
    return rows, meta


def _wrap_lines(text: str, width: int) -> list[str]:
    if not text:
        return [""]
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _sheet_title(report_type: str, now: datetime) -> str:
    label = REPORT_TYPES.get(report_type, "Отчёт")
    title = f"CRM {now.strftime('%d.%m.%Y %H:%M')} {label}"
    return title[:100]


def generate_report(
    db: Session,
    project: Project,
    user: User | None,
    report_type: str = "summary",
    date_from: date | None = None,
    date_to: date | None = None,
    settings: Settings | None = None,
) -> Report:
    settings = settings or get_settings()
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестный тип отчёта")
    context = build_report_context(db, project, report_type, date_from, date_to)
    ai_result = AITunnelClient(settings).generate_summary(context)
    context["summary"] = ai_result.text

    report = Report(
        project_id=project.id,
        report_type=report_type,
        period_from=date_from,
        period_to=date_to,
        summary=ai_result.text,
        created_by_id=user.id if user else None,
        status="generated",
    )
    db.add(report)
    db.flush()

    spreadsheet_url = ""
    error = ""
    if settings.report_spreadsheet_id and settings.google_service_account_configured:
        try:
            sheets = GoogleSheetsClient(settings=settings)
            now = datetime.now()
            sheet_title = _sheet_title(report_type, now)
            if sheets.sheet_exists(settings.report_spreadsheet_id, sheet_title):
                sheet_title = sheet_title[:88] + now.strftime("%H%M%S")
            sheet_id = sheets.add_sheet(settings.report_spreadsheet_id, sheet_title)
            rows, meta = build_sheet_rows(context)
            sheets.write_values(settings.report_spreadsheet_id, sheet_title, rows)
            sheets.format_report(
                settings.report_spreadsheet_id,
                sheet_id,
                header_row=meta["header_row"],
                last_row=meta["last_row"],
                columns=meta["columns"],
                column_widths=[280, 140, 140, 150, 150, 160],
            )
            if meta["chart_start"] and meta["chart_end"] > meta["chart_start"]:
                try:
                    sheets.add_column_chart(
                        settings.report_spreadsheet_id,
                        sheet_id,
                        title="Сумма по этапам воронки",
                        start_row=meta["chart_start"] - 1,
                        end_row=meta["chart_end"],
                        category_column=0,
                        value_column=1,
                        anchor_row=1,
                        anchor_column=7,
                    )
                except GoogleIntegrationError as exc:
                    LOGGER.warning("Не удалось добавить диаграмму: %s", exc)
            spreadsheet_url = (
                f"https://docs.google.com/spreadsheets/d/{settings.report_spreadsheet_id}"
                f"/edit#gid={sheet_id}"
            )
            report.status = "generated"
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            report.status = "partial"
            LOGGER.error("Отчёт не записан в Google Sheets: %s", exc)

    report.spreadsheet_url = spreadsheet_url
    report.error = error
    db.flush()

    if user is not None:
        link = spreadsheet_url or "ссылка недоступна (Google не настроен)"
        notify_user(
            db,
            user,
            subject=f"Отчёт готов: {REPORT_TYPES.get(report_type, report_type)}",
            body=(
                f"Отчёт по проекту «{project.name}» за {period_label(date_from, date_to)} готов.\n"
                f"Ссылка: {link}\n\n{ai_result.text}"
            ),
            project_id=project.id,
            dedupe_key=f"report:{report.id}",
        )
    return report


def report_file_name(report_type: str) -> str:
    return f"report-{report_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"


def export_csv(
    db: Session,
    project: Project,
    entity: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> bytes:
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    start, end = _date_bounds(date_from, date_to)

    if entity == "clients":
        writer.writerow(["ID", "Имя", "Компания", "Email", "Телефон", "Статус", "Источник", "Дата"])
        for client in db.scalars(
            select(Client).where(Client.project_id == project.id).order_by(Client.name)
        ):
            writer.writerow(
                [
                    client.id,
                    client.name,
                    client.company,
                    client.email,
                    client.phone,
                    STATUS_LABELS.get(client.status, client.status),
                    client.source,
                    client.created_at.strftime("%d.%m.%Y"),
                ]
            )
    elif entity == "deals":
        writer.writerow(["ID", "Сделка", "Клиент", "Тип", "Этап", "Сумма", "Валюта", "Дата"])
        for deal in db.scalars(
            select(Deal)
            .options(selectinload(Deal.client))
            .where(Deal.project_id == project.id)
            .order_by(Deal.created_at.desc())
        ):
            writer.writerow(
                [
                    deal.id,
                    deal.title,
                    deal.client.name if deal.client else "",
                    "Заказ" if deal.kind == "order" else "Сделка",
                    STAGE_LABELS.get(deal.stage, deal.stage),
                    f"{deal.amount:.2f}",
                    deal.currency,
                    deal.created_at.strftime("%d.%m.%Y"),
                ]
            )
    elif entity == "tasks":
        writer.writerow(["ID", "Задача", "Клиент", "Сделка", "Приоритет", "Срок", "Выполнена"])
        for task in db.scalars(
            select(Task)
            .options(selectinload(Task.client), selectinload(Task.deal))
            .where(Task.project_id == project.id)
            .order_by(Task.due_at)
        ):
            writer.writerow(
                [
                    task.id,
                    task.title,
                    task.client.name if task.client else "",
                    task.deal.title if task.deal else "",
                    task.priority,
                    task.due_at.strftime("%d.%m.%Y %H:%M") if task.due_at else "",
                    "да" if task.is_completed else "нет",
                ]
            )
    elif entity == "payments":
        writer.writerow(["ID", "Сумма", "Валюта", "Статус", "Метод", "Описание", "Создан", "Оплачен"])
        for payment in db.scalars(
            select(Payment)
            .where(Payment.project_id == project.id)
            .order_by(Payment.created_at.desc())
        ):
            writer.writerow(
                [
                    payment.id,
                    f"{payment.amount:.2f}",
                    payment.currency,
                    STATUS_LABELS.get(payment.status, payment.status),
                    payment.method,
                    payment.description,
                    payment.created_at.strftime("%d.%m.%Y"),
                    payment.paid_at.strftime("%d.%m.%Y") if payment.paid_at else "",
                ]
            )
    elif entity == "transactions":
        writer.writerow(["ID", "Дата", "Тип", "Категория", "Сумма", "Валюта", "Описание"])
        query = select(Transaction).where(Transaction.project_id == project.id)
        if start:
            query = query.where(Transaction.transaction_date >= start.date())
        if end:
            query = query.where(Transaction.transaction_date < end.date())
        for tx in db.scalars(query.order_by(Transaction.transaction_date.desc())):
            writer.writerow(
                [
                    tx.id,
                    tx.transaction_date.strftime("%d.%m.%Y"),
                    "Доход" if tx.type == "income" else "Расход",
                    tx.category,
                    f"{tx.amount:.2f}",
                    tx.currency,
                    tx.description,
                ]
            )
    elif entity == "products":
        writer.writerow(["ID", "SKU", "Название", "Единица", "Цена", "Себестоимость", "Остаток", "Минимум"])
        for product in db.scalars(
            select(Product).where(Product.project_id == project.id).order_by(Product.name)
        ):
            writer.writerow(
                [
                    product.id,
                    product.sku,
                    product.name,
                    product.unit,
                    f"{product.price:.2f}",
                    f"{product.cost:.2f}",
                    f"{product.stock_qty:.3f}",
                    f"{product.min_stock:.3f}",
                ]
            )
    else:
        raise HTTPException(status_code=400, detail="Неизвестная сущность экспорта")
    return output.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Расписания
# ---------------------------------------------------------------------------
def next_cron_run(cron_expression: str, base: datetime | None = None) -> datetime:
    base = base or datetime.now(UTC)
    try:
        return croniter(cron_expression, base).get_next(datetime)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Некорректное cron-выражение: {exc}") from exc


def create_schedule(
    db: Session,
    project: Project,
    user: User | None,
    *,
    report_type: str,
    cron_expression: str,
    recipients_email: str = "",
    recipients_telegram: str = "",
    channels: str = "email",
    is_active: bool = True,
) -> ReportSchedule:
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестный тип отчёта")
    schedule = ReportSchedule(
        project_id=project.id,
        report_type=report_type,
        cron_expression=cron_expression.strip(),
        recipients_email=recipients_email.strip(),
        recipients_telegram=recipients_telegram.strip(),
        channels=channels,
        is_active=is_active,
        next_run_at=next_cron_run(cron_expression),
        created_by_id=user.id if user else None,
    )
    db.add(schedule)
    db.flush()
    return schedule


def run_schedule(db: Session, schedule: ReportSchedule, settings: Settings | None = None) -> Report:
    settings = settings or get_settings()
    project = db.get(Project, schedule.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Проект расписания не найден")
    creator = db.get(User, schedule.created_by_id) if schedule.created_by_id else None
    report = generate_report(
        db,
        project,
        creator,
        schedule.report_type,
        settings=settings,
    )
    link = report.spreadsheet_url or "ссылка недоступна"
    subject = f"Отчёт по расписанию: {REPORT_TYPES.get(schedule.report_type, schedule.report_type)}"
    body = f"Проект: {project.name}\nОтчёт: {link}\n\n{report.summary}"

    channels = {item.strip() for item in schedule.channels.split(",") if item.strip()}
    if "email" in channels:
        for email in _split(schedule.recipients_email):
            enqueue(
                db,
                channel="email",
                recipient=email,
                subject=subject,
                body=body,
                project_id=project.id,
                dedupe_key=f"schedule:{schedule.id}:{report.id}:email:{email}",
            )
    if "telegram" in channels:
        for chat_id in _split(schedule.recipients_telegram):
            enqueue(
                db,
                channel="telegram",
                recipient=chat_id,
                subject=subject,
                body=body,
                project_id=project.id,
                dedupe_key=f"schedule:{schedule.id}:{report.id}:telegram:{chat_id}",
            )

    schedule.last_run_at = datetime.now(UTC)
    schedule.next_run_at = next_cron_run(schedule.cron_expression, schedule.last_run_at)
    schedule.last_error = report.error
    db.flush()
    return report


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
