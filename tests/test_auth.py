from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import ADMIN_EMAIL, ADMIN_PASSWORD, get_csrf, headers, login


def test_login_and_logout(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    token = get_csrf(client, "/login")
    response = client.post(
        "/login",
        data={
            "_csrf": token,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "next": "/",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert client.get("/").status_code == 200

    token = get_csrf(client, "/")
    response = client.post("/logout", data={"_csrf": token}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unauthenticated_redirect(client: TestClient):
    response = client.get("/clients", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_invalid_api_login(client: TestClient):
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_viewer_permissions(app, client: TestClient):
    token = login(client)
    project_id = client.get("/api/projects").json()[0]["id"]

    response = client.post(
        "/api/users",
        json={
            "email": "viewer@test.local",
            "password": "ViewerPass123!",
            "full_name": "Viewer User",
            "role": "viewer",
        },
        headers=headers(token),
    )
    assert response.status_code == 201, response.text
    viewer_id = response.json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/members",
        json={"user_id": viewer_id, "role": "viewer"},
        headers=headers(token),
    )
    assert response.status_code == 201, response.text

    with TestClient(app) as viewer:
        viewer_token = login(viewer, "viewer@test.local", "ViewerPass123!")
        assert viewer_token
        assert viewer.get("/clients").status_code == 200
        assert viewer.get("/clients/new").status_code == 403
        assert viewer.get("/admin/users").status_code == 403
        response = viewer.post(
            "/api/clients",
            json={"name": "Запрещённый клиент"},
            headers=headers(viewer_token),
        )
        assert response.status_code == 403


def test_api_bearer_token(app, admin):
    client, token = admin
    response = client.post(
        "/api/auth/tokens",
        json={"name": "pytest", "days": 10},
        headers=headers(token),
    )
    assert response.status_code == 201, response.text
    raw = response.json()["token"]
    assert raw.startswith("crm_")

    with TestClient(app) as api_client:
        response = api_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {raw}"}
        )
        assert response.status_code == 200
        assert response.json()["user"]["email"] == ADMIN_EMAIL
        response = api_client.get(
            "/api/clients", headers={"Authorization": f"Bearer {raw}"}
        )
        assert response.status_code == 200


def test_csrf_required(admin):
    client, _ = admin
    response = client.post("/api/clients", json={"name": "Без CSRF"})
    assert response.status_code == 403
    response = client.post(
        "/api/clients",
        json={"name": "Неверный CSRF"},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert response.status_code == 403
