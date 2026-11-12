"""Вход, выход и профиль пользователя."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import ApiToken
from app.services.auth import (
    authenticate,
    create_api_token,
    login_session,
    logout_session,
    update_user,
)
from app.web.utils import ensure_csrf, flash, render, templates

router = APIRouter(tags=["web-auth"])


@router.get("/login")
def login_page(request: Request, db: DbSession, next: str = "/"):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "csrf_token": ensure_csrf(request),
            "error": "",
            "next": next,
            "app_name": request.app.state.settings.app_name,
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    db: DbSession,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = authenticate(db, email, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "csrf_token": ensure_csrf(request),
                "error": "Неверный email или пароль",
                "next": next,
                "app_name": request.app.state.settings.app_name,
            },
            status_code=400,
        )
    login_session(request, user)
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    return RedirectResponse(next, status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_session(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/profile")
def profile(request: Request, db: DbSession, user: CurrentUser):
    tokens = list(
        db.scalars(
            select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
        )
    )
    return render(request, "profile.html", db, user, tokens=tokens)


@router.post("/profile")
def update_profile(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    full_name: str = Form(""),
    email: str = Form(...),
    telegram_chat_id: str = Form(""),
    notify_email: str | None = Form(None),
    notify_telegram: str | None = Form(None),
    password: str = Form(""),
):
    try:
        update_user(
            db,
            user,
            {
                "full_name": full_name,
                "email": email,
                "telegram_chat_id": telegram_chat_id,
                "notify_email": notify_email == "on",
                "notify_telegram": notify_telegram == "on",
                "password": password or None,
            },
        )
        db.commit()
        flash(request, "Профиль обновлён")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(request, f"Не удалось обновить профиль: {exc}", "error")
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/tokens")
def create_token(request: Request, db: DbSession, user: CurrentUser, name: str = Form("API token")):
    raw, token = create_api_token(db, user, name, 365)
    db.commit()
    flash(request, f"Токен создан. Сохраните его: {raw}", "warning")
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/tokens/{token_id}/delete")
def delete_token(token_id: int, request: Request, db: DbSession, user: CurrentUser):
    token = db.get(ApiToken, token_id)
    if token and (token.user_id == user.id or user.role == "admin"):
        db.delete(token)
        db.commit()
        flash(request, "Токен отозван")
    return RedirectResponse("/profile", status_code=303)
