"""API отчётов, экспорта и расписаний."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Paging, paginate, require_edit, resolve_project
from app.models import Report, ReportSchedule
from app.schemas import (
    Page,
    ReportGenerateRequest,
    ReportRead,
    ReportScheduleCreate,
    ReportScheduleRead,
    ReportScheduleUpdate,
)
from app.services.reports import (
    create_schedule,
    export_csv,
    generate_report,
    next_cron_run,
    report_file_name,
    run_schedule,
)

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports", response_model=Page[ReportRead])
def list_reports(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
):
    project = resolve_project(request, db, user, project_id)
    query = (
        select(Report)
        .where(Report.project_id == project.id)
        .order_by(Report.created_at.desc())
    )
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("/reports/generate", response_model=ReportRead)
def generate(payload: ReportGenerateRequest, request: Request, db: DbSession, user: CurrentUser):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    report = generate_report(
        db,
        project,
        user,
        payload.report_type,
        payload.period_from,
        payload.period_to,
        settings=request.app.state.settings,
    )
    db.commit()
    return report


@router.get("/reports/{report_id}", response_model=ReportRead)
def get_report(report_id: int, db: DbSession, user: CurrentUser):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    from app.services.access import get_project_for_user

    get_project_for_user(db, report.project_id, user)
    return report


@router.get("/export/{entity}")
def export_entity(
    entity: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    project_id: int | None = None,
):
    project = resolve_project(request, db, user, project_id)
    content = export_csv(db, project, entity)
    filename = report_file_name(entity)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report-schedules", response_model=Page[ReportScheduleRead])
def list_schedules(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    paging: Paging,
    project_id: int | None = None,
):
    project = resolve_project(request, db, user, project_id)
    query = (
        select(ReportSchedule)
        .where(ReportSchedule.project_id == project.id)
        .order_by(ReportSchedule.created_at.desc())
    )
    items, total = paginate(db, query, paging)
    return Page(items=items, total=total, page=paging.page, per_page=paging.per_page)


@router.post("/report-schedules", response_model=ReportScheduleRead, status_code=201)
def add_schedule(
    payload: ReportScheduleCreate, request: Request, db: DbSession, user: CurrentUser
):
    project = resolve_project(request, db, user, payload.project_id)
    require_edit(db, project, user)
    schedule = create_schedule(
        db,
        project,
        user,
        report_type=payload.report_type,
        cron_expression=payload.cron_expression,
        recipients_email=payload.recipients_email,
        recipients_telegram=payload.recipients_telegram,
        channels=payload.channels,
        is_active=payload.is_active,
    )
    db.commit()
    return schedule


@router.put("/report-schedules/{schedule_id}", response_model=ReportScheduleRead)
def update_schedule(
    schedule_id: int, payload: ReportScheduleUpdate, db: DbSession, user: CurrentUser
):
    schedule = db.get(ReportSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    require_edit(db, schedule.project, user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(schedule, field, value)
    if "cron_expression" in data and data["cron_expression"]:
        schedule.next_run_at = next_cron_run(data["cron_expression"])
    db.commit()
    return schedule


@router.delete("/report-schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: DbSession, user: CurrentUser):
    schedule = db.get(ReportSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    require_edit(db, schedule.project, user)
    db.delete(schedule)
    db.commit()
    return {"ok": True}


@router.post("/report-schedules/{schedule_id}/run", response_model=ReportRead)
def run_schedule_now(schedule_id: int, request: Request, db: DbSession, user: CurrentUser):
    schedule = db.get(ReportSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    require_edit(db, schedule.project, user)
    report = run_schedule(db, schedule, request.app.state.settings)
    db.commit()
    return report
