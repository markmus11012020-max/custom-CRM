"""Фоновые задачи: уведомления, дедлайны, отчёты по расписанию."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import Settings, get_logger
from app.database import Database
from app.models import ReportSchedule, Task, User
from app.services.notifications import notify_project_managers, notify_user, process_pending
from app.services.reports import next_cron_run, run_schedule

LOGGER = get_logger("scheduler")


class SchedulerService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            LOGGER.info("Планировщик отключён (SCHEDULER_ENABLED=false)")
            return
        timezone = ZoneInfo(self.settings.timezone)
        scheduler = BackgroundScheduler(timezone=timezone, daemon=True)
        scheduler.add_job(
            self.process_notifications,
            "interval",
            seconds=30,
            id="notifications",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            self.check_due_tasks,
            "interval",
            minutes=5,
            id="due_tasks",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            self.run_report_schedules,
            "interval",
            seconds=60,
            id="scheduled_reports",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        self.scheduler = scheduler
        self.initialize_schedules()
        LOGGER.info("Планировщик запущен (timezone=%s)", self.settings.timezone)

    def shutdown(self) -> None:
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
            LOGGER.info("Планировщик остановлен")

    # ------------------------------------------------------------------
    def process_notifications(self) -> None:
        try:
            with self.database.session_scope() as db:
                result = process_pending(db, self.settings)
                if result.get("sent") or result.get("failed"):
                    LOGGER.info("Outbox: %s", result)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Ошибка обработки уведомлений: %s", exc)

    def check_due_tasks(self) -> None:
        try:
            now = datetime.now(UTC)
            horizon = now + timedelta(hours=24)
            with self.database.session_scope() as db:
                tasks = list(
                    db.scalars(
                        select(Task)
                        .where(
                            Task.is_completed.is_(False),
                            Task.due_at.is_not(None),
                            Task.due_at <= horizon,
                        )
                        .order_by(Task.due_at)
                    )
                )
                for task in tasks:
                    due = task.due_at
                    if due is None:
                        continue
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=UTC)
                    overdue = due < now
                    key = f"task-due:{task.id}:{now.date().isoformat()}"
                    subject = (
                        f"Просроченная задача: {task.title}"
                        if overdue
                        else f"Задача скоро: {task.title}"
                    )
                    body = (
                        f"Проект: {task.project.name}\n"
                        f"Срок: {due.strftime('%d.%m.%Y %H:%M')}\n"
                        f"Приоритет: {task.priority}\n"
                        f"{task.description or ''}"
                    )
                    if task.assigned_to_id:
                        user = db.get(User, task.assigned_to_id)
                        if user:
                            notify_user(
                                db,
                                user,
                                subject=subject,
                                body=body,
                                project_id=task.project_id,
                                dedupe_key=key,
                            )
                    else:
                        notify_project_managers(
                            db,
                            task.project,
                            subject=subject,
                            body=body,
                            dedupe_key=key,
                        )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Ошибка проверки дедлайнов: %s", exc)

    def run_report_schedules(self) -> None:
        try:
            now = datetime.now(UTC)
            with self.database.session_scope() as db:
                schedules = list(
                    db.scalars(
                        select(ReportSchedule).where(
                            ReportSchedule.is_active.is_(True),
                            ReportSchedule.next_run_at.is_not(None),
                            ReportSchedule.next_run_at <= now,
                        )
                    )
                )
                for schedule in schedules:
                    try:
                        report = run_schedule(db, schedule, self.settings)
                        LOGGER.info(
                            "Отчёт по расписанию %s создан: %s",
                            schedule.id,
                            report.id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.exception("Ошибка отчёта по расписанию %s: %s", schedule.id, exc)
                        schedule.last_error = str(exc)[:2000]
                        schedule.last_run_at = now
                        schedule.next_run_at = next_cron_run(schedule.cron_expression, now)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Ошибка обработки расписаний: %s", exc)

    def initialize_schedules(self) -> None:
        try:
            with self.database.session_scope() as db:
                schedules = list(
                    db.scalars(
                        select(ReportSchedule).where(
                            ReportSchedule.is_active.is_(True),
                            ReportSchedule.next_run_at.is_(None),
                        )
                    )
                )
                for schedule in schedules:
                    try:
                        schedule.next_run_at = next_cron_run(schedule.cron_expression)
                    except Exception as exc:  # noqa: BLE001
                        schedule.last_error = str(exc)[:2000]
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Ошибка инициализации расписаний: %s", exc)
