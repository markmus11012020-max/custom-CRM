from __future__ import annotations

import re

from fastapi.testclient import TestClient

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "TestPass123!"


def get_csrf(client: TestClient, path: str = "/") -> str:
    response = client.get(path)
    match = re.search(r'name="_csrf" value="([^"]+)"', response.text)
    assert match, f"CSRF token not found on {path}: {response.status_code}"
    return match.group(1)


def login(
    client: TestClient,
    email: str = ADMIN_EMAIL,
    password: str = ADMIN_PASSWORD,
) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return get_csrf(client)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}
