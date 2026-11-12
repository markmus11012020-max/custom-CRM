"""Точка входа FastAPI Custom-CRM."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api import accounting, admin, auth, clients, deals, google, health, payments, projects
from app.api import reports as reports_api
from app.api import search as search_api
from app.api import tasks as tasks_api
from app.api import warehouse as warehouse_api
from app.config import Settings, get_settings, setup_logging
from app.database import Database
from app.services.scheduler import SchedulerService
from app.web import accounting as web_accounting
from app.web import admin as web_admin
from app.web import auth as web_auth
from app.web import clients as web_clients
from app.web import dashboard as web_dashboard
from app.web import deals as web_deals
from app.web import payments as web_payments
from app.web import reports as web_reports
from app.web import tasks as web_tasks
from app.web import warehouse as web_warehouse
from app.web.utils import templates

LOGGER = logging.getLogger("custom_crm.main")

PUBLIC_PREFIXES = (
    "/static",
    "/login",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/payments/robokassa/",
)


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == prefix or path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return await call_next(request)
        if path == "/api/auth/login":
            return await call_next(request)
        has_session = bool(request.session.get("user_id"))
        has_bearer = request.headers.get("Authorization", "").lower().startswith("bearer ")
        if path.startswith("/api/"):
            if has_session or has_bearer:
                return await call_next(request)
            return JSONResponse({"detail": "Требуется авторизация"}, status_code=401)
        if not has_session:
            target = quote(path)
            return RedirectResponse(f"/login?next={target}", status_code=303)
        return await call_next(request)


class CSRFMiddleware:
    """ASGI-middleware с буферизацией body, чтобы форма осталась доступна маршруту."""

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    EXEMPT_PREFIXES = ("/payments/robokassa/",)

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        if method in self.SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return
        if path == "/api/auth/login":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        if headers.get("authorization", "").lower().startswith("bearer "):
            await self.app(scope, receive, send)
            return
        session = scope.get("session", {})
        if path.startswith("/api/") and not session.get("user_id"):
            await self.app(scope, receive, send)
            return

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        expected = session.get("csrf_token", "")
        supplied = headers.get("x-csrf-token", "")
        if not supplied:
            content_type = headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                from urllib.parse import parse_qs

                values = parse_qs(body.decode("utf-8", errors="replace"))
                supplied = (values.get("_csrf") or [""])[0]

        if not expected or supplied != expected:
            response = (
                JSONResponse({"detail": "CSRF-токен недействителен"}, status_code=403)
                if path.startswith("/api/")
                else HTMLResponse("<h1>403</h1><p>CSRF-токен недействителен</p>", status_code=403)
            )
            await response(scope, receive, send)
            return

        async def replay_receive():
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)
    database = Database(settings)
    database.create_all()
    database.seed()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = SchedulerService(database, settings)
        app.state.scheduler = scheduler
        scheduler.start()
        yield
        scheduler.shutdown()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Универсальная мини-CRM: клиенты, проекты, сделки, задачи, платежи, склад, учёт и отчёты.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = database
    app.state.templates = templates
    app.state.scheduler = None

    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="custom_crm_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=False,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # API
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(clients.router)
    app.include_router(deals.router)
    app.include_router(tasks_api.router)
    app.include_router(payments.router)
    app.include_router(warehouse_api.router)
    app.include_router(accounting.router)
    app.include_router(reports_api.router)
    app.include_router(google.router)
    app.include_router(search_api.router)
    app.include_router(admin.router)

    # Web UI
    app.include_router(web_auth.router)
    app.include_router(web_dashboard.router)
    app.include_router(web_clients.router)
    app.include_router(web_deals.router)
    app.include_router(web_tasks.router)
    app.include_router(web_payments.router)
    app.include_router(web_warehouse.router)
    app.include_router(web_accounting.router)
    app.include_router(web_reports.router)
    app.include_router(web_admin.router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "request": request,
                "status_code": exc.status_code,
                "detail": exc.detail,
                "app_name": settings.app_name,
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Ошибка валидации", "errors": exc.errors()}, status_code=422)
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "request": request,
                "status_code": 422,
                "detail": "Проверьте заполнение полей формы.",
                "app_name": settings.app_name,
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        LOGGER.exception("Необработанная ошибка: %s", exc)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "request": request,
                "status_code": 500,
                "detail": "Внутренняя ошибка сервера. Подробности в logs/app.log.",
                "app_name": settings.app_name,
            },
            status_code=500,
        )

    return app


app = create_app()
