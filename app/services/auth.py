"""Аутентификация, пользователи и API-токены."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiToken, User
from app.security import (
    generate_api_token,
    hash_api_token,
    hash_password,
    verify_password,
)


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str = "",
    role: str = "manager",
    is_active: bool = True,
    telegram_chat_id: str = "",
    notify_email: bool = True,
    notify_telegram: bool = False,
) -> User:
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=is_active,
        telegram_chat_id=telegram_chat_id,
        notify_email=notify_email,
        notify_telegram=notify_telegram,
    )
    db.add(user)
    db.flush()
    return user


def update_user(db: Session, user: User, data: dict) -> User:
    if "email" in data and data["email"] is not None:
        email = str(data["email"]).strip().lower()
        existing = db.scalar(select(User).where(User.email == email, User.id != user.id))
        if existing:
            raise HTTPException(status_code=409, detail="Email уже используется")
        user.email = email
    for field in (
        "full_name",
        "role",
        "is_active",
        "telegram_chat_id",
        "notify_email",
        "notify_telegram",
    ):
        if field in data and data[field] is not None:
            setattr(user, field, data[field])
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
    return user


def create_api_token(db: Session, user: User, name: str, days: int | None = 365) -> tuple[str, ApiToken]:
    raw = generate_api_token()
    token = ApiToken(
        user_id=user.id,
        name=name or "API token",
        token_hash=hash_api_token(raw),
        expires_at=(datetime.now(UTC) + timedelta(days=days)) if days else None,
    )
    db.add(token)
    db.flush()
    return raw, token


def resolve_api_token(db: Session, raw_token: str) -> User | None:
    if not raw_token:
        return None
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_api_token(raw_token)))
    if token is None:
        return None
    if token.expires_at is not None:
        expires = token.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            return None
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        return None
    token.last_used_at = datetime.now(UTC)
    return user


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user_id = request.session.get("user_id")
    if user_id:
        user = db.get(User, int(user_id))
        if user is not None and user.is_active:
            request.state.user = user
            return user
        request.session.clear()

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        user = resolve_api_token(db, authorization[7:].strip())
        if user is not None:
            request.state.user = user
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется авторизация",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return user


def require_manager(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="Требуются права менеджера")
    return user


def login_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["role"] = user.role


def logout_session(request: Request) -> None:
    request.session.clear()
