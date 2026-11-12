"""API аутентификации и токенов."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import ApiToken
from app.schemas import ApiTokenCreate, LoginRequest, TokenRead, UserRead
from app.services.access import accessible_projects
from app.services.auth import (
    authenticate,
    create_api_token,
    login_session,
    logout_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, request: Request, db: DbSession):
    user = authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    login_session(request, user)
    db.commit()
    return user


@router.post("/logout")
def logout(request: Request):
    logout_session(request)
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: DbSession, user: CurrentUser):
    projects = [
        {"id": p.id, "name": p.name, "code": p.code, "currency": p.currency}
        for p in accessible_projects(db, user)
    ]
    return {"user": UserRead.model_validate(user), "projects": projects}


@router.get("/tokens", response_model=list[TokenRead])
def list_tokens(db: DbSession, user: CurrentUser):
    tokens = db.scalars(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
    )
    return [
        TokenRead(
            id=token.id,
            name=token.name,
            expires_at=token.expires_at,
            created_at=token.created_at,
        )
        for token in tokens
    ]


@router.post("/tokens", response_model=TokenRead, status_code=201)
def create_token(payload: ApiTokenCreate, db: DbSession, user: CurrentUser):
    raw, token = create_api_token(db, user, payload.name, payload.days)
    db.commit()
    return TokenRead(
        id=token.id,
        name=token.name,
        token=raw,
        expires_at=token.expires_at,
        created_at=token.created_at,
    )


@router.delete("/tokens/{token_id}")
def delete_token(token_id: int, db: DbSession, user: CurrentUser):
    token = db.get(ApiToken, token_id)
    if token is None or (token.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Токен не найден")
    db.delete(token)
    db.commit()
    return {"ok": True}
