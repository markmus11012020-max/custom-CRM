from __future__ import annotations

from tests.helpers import headers


def test_client_crud_and_search(admin):
    client, token = admin
    payload = {
        "name": "Иван Петров",
        "company": "ООО Ромашка",
        "email": "ivan@example.com",
        "phone": "+7 900 100-10-10",
        "status": "active",
        "notes": "Интересуется автоматизацией",
    }
    response = client.post("/api/clients", json=payload, headers=headers(token))
    assert response.status_code == 201, response.text
    client_id = response.json()["id"]

    response = client.get("/api/clients?q=ромашка")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == client_id

    response = client.get("/api/clients?q=ИВАН")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = client.put(
        f"/api/clients/{client_id}",
        json={"status": "inactive", "notes": "Обновлено"},
        headers=headers(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "inactive"

    response = client.delete(f"/api/clients/{client_id}", headers=headers(token))
    assert response.status_code == 200
    response = client.get(f"/api/clients/{client_id}")
    assert response.status_code == 200
    assert response.json()["is_archived"] is True

    response = client.post(f"/api/clients/{client_id}/restore", headers=headers(token))
    assert response.status_code == 200
    assert response.json()["is_archived"] is False


def test_client_pagination(admin):
    client, token = admin
    for index in range(5):
        response = client.post(
            "/api/clients",
            json={"name": f"Клиент {index}"},
            headers=headers(token),
        )
        assert response.status_code == 201
    response = client.get("/api/clients?page=1&per_page=2")
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["per_page"] == 2


def test_client_validation(admin):
    client, token = admin
    response = client.post("/api/clients", json={"name": ""}, headers=headers(token))
    assert response.status_code == 422
