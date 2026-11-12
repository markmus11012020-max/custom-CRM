"""Healthcheck и системная информация."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__

router = APIRouter(tags=["system"])


@router.get("/health")
def health(request: Request):
    database = request.app.state.db
    ok = database.healthcheck()
    scheduler = getattr(request.app.state, "scheduler", None)
    return {
        "status": "ok" if ok else "degraded",
        "database": "ok" if ok else "error",
        "version": __version__,
        "scheduler": bool(scheduler and scheduler.scheduler),
    }


@router.get("/api/system/info")
def system_info(request: Request):
    settings = request.app.state.settings
    return {
        "app": settings.app_name,
        "version": __version__,
        "env": settings.app_env,
        "database": "sqlite" if settings.is_sqlite else "postgresql",
        "scheduler_enabled": settings.scheduler_enabled,
        "google_service_account": settings.google_service_account_configured,
        "google_oauth": settings.google_oauth_authorized,
        "robokassa_test_mode": settings.robokassa_test_mode,
        "smtp": settings.smtp_configured,
        "telegram": settings.telegram_configured,
        "ai": settings.ai_configured,
    }
