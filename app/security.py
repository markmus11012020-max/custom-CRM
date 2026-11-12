"""Пароли, токены и CSRF."""

from __future__ import annotations

import hashlib
import secrets

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:  # noqa: BLE001 - повреждённый хеш не должен ронять вход
        return False


def generate_api_token() -> str:
    return "crm_" + secrets.token_urlsafe(36)


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_compare(left: str, right: str) -> bool:
    return secrets.compare_digest(left or "", right or "")
