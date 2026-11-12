"""Email/Telegram-уведомления через outbox-таблицу."""

from __future__ import annotations

import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape as html_escape

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_logger, get_settings
from app.models import Notification, Project, ProjectMember, User

LOGGER = get_logger("notifications")


def enqueue(
    db: Session,
    *,
    channel: str,
    recipient: str,
    subject: str,
    body: str,
    user_id: int | None = None,
    project_id: int | None = None,
    dedupe_key: str | None = None,
) -> Notification:
    if dedupe_key:
        existing = db.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))
        if existing is not None:
            return existing
    notification = Notification(
        user_id=user_id,
        project_id=project_id,
        channel=channel,
        recipient=recipient[:255],
        subject=subject[:255],
        body=body,
        status="pending",
        dedupe_key=dedupe_key,
    )
    db.add(notification)
    db.flush()
    return notification


def notify_user(
    db: Session,
    user: User,
    *,
    subject: str,
    body: str,
    project_id: int | None = None,
    dedupe_key: str | None = None,
    channels: list[str] | None = None,
) -> list[Notification]:
    if not user.is_active:
        return []
    requested = channels or ["email", "telegram"]
    created: list[Notification] = []
    if "email" in requested and user.notify_email and user.email:
        key = f"{dedupe_key}:{user.id}:email" if dedupe_key else None
        created.append(
            enqueue(
                db,
                channel="email",
                recipient=user.email,
                subject=subject,
                body=body,
                user_id=user.id,
                project_id=project_id,
                dedupe_key=key,
            )
        )
    if "telegram" in requested and user.notify_telegram and user.telegram_chat_id:
        key = f"{dedupe_key}:{user.id}:telegram" if dedupe_key else None
        created.append(
            enqueue(
                db,
                channel="telegram",
                recipient=user.telegram_chat_id,
                subject=subject,
                body=body,
                user_id=user.id,
                project_id=project_id,
                dedupe_key=key,
            )
        )
    return created


def notify_project_managers(
    db: Session,
    project: Project,
    *,
    subject: str,
    body: str,
    dedupe_key: str | None = None,
) -> list[Notification]:
    user_ids: set[int] = set()
    if project.owner_id:
        user_ids.add(project.owner_id)
    for member in db.scalars(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.role == "manager"
        )
    ):
        user_ids.add(member.user_id)
    created: list[Notification] = []
    for user_id in user_ids:
        user = db.get(User, user_id)
        if user is not None:
            created.extend(
                notify_user(
                    db,
                    user,
                    subject=subject,
                    body=body,
                    project_id=project.id,
                    dedupe_key=dedupe_key,
                )
            )
    return created


def send_email(settings: Settings, recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_configured:
        raise RuntimeError("SMTP не настроен")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, context=ssl.create_default_context(), timeout=20
        ) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_tls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


def send_telegram(settings: Settings, chat_id: str, subject: str, body: str) -> None:
    if not settings.telegram_configured:
        raise RuntimeError("Telegram не настроен")
    text = f"<b>{html_escape(subject)}</b>\n\n{html_escape(body)}"
    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=20,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400 or not payload.get("ok", False):
        raise RuntimeError(f"Telegram API: {response.status_code} {payload}")


def process_pending(db: Session, settings: Settings | None = None, limit: int = 50) -> dict[str, int]:
    settings = settings or get_settings()
    pending = list(
        db.scalars(
            select(Notification)
            .where(Notification.status == "pending")
            .order_by(Notification.created_at)
            .limit(limit)
        )
    )
    result = {"sent": 0, "failed": 0, "skipped": 0, "processed": len(pending)}
    for notification in pending:
        notification.attempts += 1
        try:
            if notification.channel == "email":
                if not settings.smtp_configured:
                    raise RuntimeError("SMTP не настроен")
                send_email(settings, notification.recipient, notification.subject, notification.body)
            elif notification.channel == "telegram":
                if not settings.telegram_configured:
                    raise RuntimeError("Telegram не настроен")
                send_telegram(settings, notification.recipient, notification.subject, notification.body)
            else:
                raise RuntimeError(f"Неизвестный канал: {notification.channel}")
            notification.status = "sent"
            notification.sent_at = datetime.now(UTC)
            notification.error = ""
            result["sent"] += 1
        except Exception as exc:  # noqa: BLE001
            notification.error = str(exc)[:1000]
            if "не настроен" in str(exc).lower():
                notification.status = "skipped"
                result["skipped"] += 1
            elif notification.attempts >= 3:
                notification.status = "failed"
                result["failed"] += 1
            else:
                notification.status = "pending"
                result["failed"] += 1
            LOGGER.warning(
                "Уведомление %s (%s) не отправлено: %s",
                notification.id,
                notification.channel,
                notification.error,
            )
    db.flush()
    return result


def process_pending_job(database) -> dict[str, int]:  # type: ignore[no-untyped-def]
    with database.session_scope() as session:
        return process_pending(session)


def queue_test_notification(db: Session, user: User, channel: str) -> Notification:
    return enqueue(
        db,
        channel=channel,
        recipient=user.email if channel == "email" else user.telegram_chat_id,
        subject="Тестовое уведомление Custom-CRM",
        body="Если вы видите это сообщение, интеграция настроена корректно.",
        user_id=user.id,
    )
