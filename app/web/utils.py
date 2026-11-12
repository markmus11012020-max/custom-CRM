"""Шаблоны, фильтры и flash-сообщения."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from app.config import get_settings
from app.models import Project, User
from app.services.access import accessible_projects
from app.services.reports import STAGE_LABELS, STATUS_LABELS, money

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

PRIORITY_LABELS = {
    "low": "Низкий",
    "normal": "Обычный",
    "high": "Высокий",
    "urgent": "Срочный",
}
ROLE_LABELS = {"admin": "Администратор", "manager": "Менеджер", "viewer": "Наблюдатель"}
KIND_LABELS = {"deal": "Сделка", "order": "Заказ"}
MOVEMENT_LABELS = {"in": "Приход", "out": "Расход", "adjust": "Корректировка"}
CHANNEL_LABELS = {"email": "Email", "telegram": "Telegram"}
REPORT_TYPE_LABELS = {
    "summary": "Сводка CRM",
    "sales": "Продажи",
    "finance": "Финансы",
    "warehouse": "Склад",
    "tasks": "Задачи",
}


def fmt_date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    return value.strftime("%d.%m.%Y")


def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def fmt_money(value: Any) -> str:
    return money(value)


def status_label(value: str | None) -> str:
    return STATUS_LABELS.get(value or "", value or "—")


def stage_label(value: str | None) -> str:
    return STAGE_LABELS.get(value or "", value or "—")


def priority_label(value: str | None) -> str:
    return PRIORITY_LABELS.get(value or "", value or "—")


def role_label(value: str | None) -> str:
    return ROLE_LABELS.get(value or "", value or "—")


def kind_label(value: str | None) -> str:
    return KIND_LABELS.get(value or "", value or "—")


def movement_label(value: str | None) -> str:
    return MOVEMENT_LABELS.get(value or "", value or "—")


def channel_label(value: str | None) -> str:
    return CHANNEL_LABELS.get(value or "", value or "—")


def report_type_label(value: str | None) -> str:
    return REPORT_TYPE_LABELS.get(value or "", value or "—")


def initials(value: str | None) -> str:
    parts = [part for part in (value or "").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def is_overdue(value: datetime | None) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value < datetime.now(UTC)


def percent(part: Any, total: Any) -> str:
    try:
        part_value = float(part or 0)
        total_value = float(total or 0)
        if total_value <= 0:
            return "0%"
        return f"{part_value / total_value * 100:.0f}%"
    except (TypeError, ValueError):
        return "0%"


templates.env.filters.update(
    {
        "money": fmt_money,
        "date": fmt_date,
        "datetime": fmt_dt,
        "status_label": status_label,
        "stage_label": stage_label,
        "priority_label": priority_label,
        "role_label": role_label,
        "kind_label": kind_label,
        "movement_label": movement_label,
        "channel_label": channel_label,
        "report_type_label": report_type_label,
        "initials": initials,
        "percent": percent,
        "is_overdue": is_overdue,
    }
)
templates.env.globals.update(
    {
        "app_name": get_settings().app_name,
        "now": datetime.now,
        "report_types": REPORT_TYPE_LABELS,
        "priority_options": PRIORITY_LABELS,
        "role_options": ROLE_LABELS,
        "status_options": STATUS_LABELS,
        "stage_options": STAGE_LABELS,
        "kind_options": KIND_LABELS,
    }
)


def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        from app.security import generate_csrf_token

        token = generate_csrf_token()
        request.session["csrf_token"] = token
    return token


def flash(request: Request, message: str, category: str = "success") -> None:
    flashes = request.session.setdefault("_flashes", [])
    flashes.append({"message": message, "category": category})
    request.session["_flashes"] = flashes


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flashes", [])


def base_context(
    request: Request,
    db: Session,
    user: User,
    active_project: Project | None = None,
) -> dict[str, Any]:
    projects = accessible_projects(db, user)
    if active_project is None and projects:
        active_id = request.session.get("active_project_id")
        active_project = next((p for p in projects if p.id == active_id), projects[0])
    return {
        "request": request,
        "user": user,
        "projects": projects,
        "active_project": active_project,
        "csrf_token": ensure_csrf(request),
        "flashes": pop_flashes(request),
    }


def render(
    request: Request,
    template: str,
    db: Session,
    user: User,
    *,
    active_project: Project | None = None,
    status_code: int = 200,
    **context: Any,
):
    data = base_context(request, db, user, active_project)
    data.update(context)
    return templates.TemplateResponse(
        request,
        template,
        data,
        status_code=status_code,
    )
