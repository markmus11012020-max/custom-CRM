"""Веб-раздел отчётов и расписаний."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.google.auth import oauth_status, service_account_status
from app.models import Report, ReportSchedule
from app.services.access import get_active_project, get_project_for_user, require_project_edit
from app.services.reports import (
    create_schedule,
    export_csv,
    generate_report,
    next_cron_run,
    report_file_name,
    run_schedule,
)
from app.web.utils import flash, render

router = APIRouter(prefix="/reports", tags=["web-reports"])
PER_PAGE = 20


def _date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@router.get("")
def reports(request: Request, db: DbSession, user: CurrentUser, page: int = 1):
    project = get_active_project(request, db, user)
    query = select(Report).where(Report.project_id == project.id)
    total = len(list(db.scalars(query)))
    items = list(
        db.scalars(
            query.order_by(Report.created_at.desc())
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
        )
    )
    schedules = list(
        db.scalars(
            select(ReportSchedule)
            .where(ReportSchedule.project_id == project.id)
            .order_by(ReportSchedule.created_at.desc())
        )
    )
    settings = request.app.state.settings
    return render(
        request,
        "reports/list.html",
        db,
        user,
        active_project=project,
        reports=items,
        schedules=schedules,
        total=total,
        page=page,
        per_page=PER_PAGE,
        settings=settings,
        oauth=oauth_status(settings),
        service_account=service_account_status(settings),
        folder_id=request.app.state.db.get_setting("google_drive_folder_id", ""),
        today=date.today(),
    )


@router.post("/generate")
def generate(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    report_type: str = Form("summary"),
    date_from: str = Form(""),
    date_to: str = Form(""),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    try:
        report = generate_report(
            db,
            project,
            user,
            report_type,
            _date(date_from),
            _date(date_to),
            settings=request.app.state.settings,
        )
        db.commit()
        if report.spreadsheet_url:
            flash(request, "Отчёт создан. Ссылка доступна в истории.")
        else:
            flash(request, f"Отчёт создан без Google-ссылки: {report.error}", "warning")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Не удалось создать отчёт: {exc}", "error")
    return RedirectResponse("/reports", status_code=303)


@router.get("/{report_id}")
def report_detail(report_id: int, request: Request, db: DbSession, user: CurrentUser):
    report = db.get(Report, report_id)
    if report is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Отчёт не найден")
    project = get_project_for_user(db, report.project_id, user)
    return render(
        request,
        "reports/detail.html",
        db,
        user,
        active_project=project,
        report=report,
    )


@router.post("/schedules")
def add_schedule(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    report_type: str = Form("summary"),
    cron_expression: str = Form("0 9 * * *"),
    recipients_email: str = Form(""),
    recipients_telegram: str = Form(""),
    channels: str = Form("email"),
):
    project = get_active_project(request, db, user)
    require_project_edit(db, project.id, user)
    try:
        create_schedule(
            db,
            project,
            user,
            report_type=report_type,
            cron_expression=cron_expression,
            recipients_email=recipients_email,
            recipients_telegram=recipients_telegram,
            channels=channels,
        )
        db.commit()
        flash(request, "Расписание создано")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Ошибка расписания: {exc}", "error")
    return RedirectResponse("/reports", status_code=303)


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, request: Request, db: DbSession, user: CurrentUser):
    schedule = db.get(ReportSchedule, schedule_id)
    if schedule is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Расписание не найдено")
    project = get_project_for_user(db, schedule.project_id, user)
    require_project_edit(db, project.id, user)
    schedule.is_active = not schedule.is_active
    if schedule.is_active:
        schedule.next_run_at = next_cron_run(schedule.cron_expression)
    db.commit()
    flash(request, "Расписание обновлено")
    return RedirectResponse("/reports", status_code=303)


@router.post("/schedules/{schedule_id}/run")
def run_schedule_now(schedule_id: int, request: Request, db: DbSession, user: CurrentUser):
    schedule = db.get(ReportSchedule, schedule_id)
    if schedule is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Расписание не найдено")
    project = get_project_for_user(db, schedule.project_id, user)
    require_project_edit(db, project.id, user)
    try:
        report = run_schedule(db, schedule, request.app.state.settings)
        db.commit()
        flash(request, "Отчёт по расписанию создан")
        return RedirectResponse(f"/reports/{report.id}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Ошибка запуска: {exc}", "error")
        return RedirectResponse("/reports", status_code=303)


@router.post("/schedules/{schedule_id}/delete")
def delete_schedule(schedule_id: int, request: Request, db: DbSession, user: CurrentUser):
    schedule = db.get(ReportSchedule, schedule_id)
    if schedule is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Расписание не найдено")
    project = get_project_for_user(db, schedule.project_id, user)
    require_project_edit(db, project.id, user)
    db.delete(schedule)
    db.commit()
    flash(request, "Расписание удалено")
    return RedirectResponse("/reports", status_code=303)


@router.get("/export/{entity}")
def export(entity: str, request: Request, db: DbSession, user: CurrentUser):
    project = get_active_project(request, db, user)
    content = export_csv(db, project, entity)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_file_name(entity)}"'},
    )
