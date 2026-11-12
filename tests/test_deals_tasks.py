from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.helpers import headers


def _client(client, token):
    response = client.post(
        "/api/clients", json={"name": "Клиент сделки"}, headers=headers(token)
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_deal_without_client_and_attach(admin):
    client, token = admin
    response = client.post(
        "/api/deals",
        json={"title": "Сделка без клиента", "kind": "deal", "amount": 50000},
        headers=headers(token),
    )
    assert response.status_code == 201
    deal_id = response.json()["id"]
    assert response.json()["client_id"] is None

    client_id = _client(client, token)
    response = client.put(
        f"/api/deals/{deal_id}",
        json={"client_id": client_id, "stage": "negotiation"},
        headers=headers(token),
    )
    assert response.status_code == 200
    assert response.json()["client_id"] == client_id
    assert response.json()["stage"] == "negotiation"


def test_order_items_and_fulfillment(admin):
    client, token = admin
    response = client.post(
        "/api/products",
        json={"name": "Товар", "sku": "SKU-1", "price": 1000, "cost": 500, "min_stock": 1},
        headers=headers(token),
    )
    assert response.status_code == 201, response.text
    product_id = response.json()["id"]
    response = client.post(
        "/api/stock/movements",
        json={
            "product_id": product_id,
            "movement_type": "in",
            "quantity": 10,
            "unit_cost": 500,
        },
        headers=headers(token),
    )
    assert response.status_code == 201

    client_id = _client(client, token)
    response = client.post(
        "/api/deals",
        json={
            "title": "Заказ",
            "kind": "order",
            "client_id": client_id,
            "amount": 0,
            "stage": "won",
        },
        headers=headers(token),
    )
    deal_id = response.json()["id"]
    response = client.post(
        f"/api/deals/{deal_id}/items",
        json={"product_id": product_id, "name": "Товар", "quantity": 2, "unit_price": 1000},
        headers=headers(token),
    )
    assert response.status_code == 201
    response = client.get(f"/api/deals/{deal_id}")
    assert response.json()["amount"] == "2000.00"
    assert len(response.json()["items"]) == 1

    response = client.post(f"/api/deals/{deal_id}/fulfill", headers=headers(token))
    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "fulfilled"
    response = client.get(f"/api/products/{product_id}")
    assert response.json()["stock_qty"] == "8.000"

    response = client.post(f"/api/deals/{deal_id}/fulfill", headers=headers(token))
    assert response.status_code == 409


def test_task_complete_and_overdue(admin):
    client, token = admin
    client_id = _client(client, token)
    past = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    response = client.post(
        "/api/tasks",
        json={
            "title": "Просроченная задача",
            "client_id": client_id,
            "due_at": past,
            "priority": "high",
        },
        headers=headers(token),
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    response = client.get("/api/tasks?bucket=overdue")
    assert response.status_code == 200
    assert any(item["id"] == task_id for item in response.json()["items"])

    response = client.post(f"/api/tasks/{task_id}/complete", headers=headers(token))
    assert response.status_code == 200
    assert response.json()["is_completed"] is True
    response = client.post(f"/api/tasks/{task_id}/reopen", headers=headers(token))
    assert response.status_code == 200
    assert response.json()["is_completed"] is False

    response = client.get("/api/tasks?q=просроченная")
    assert response.status_code == 200
    assert response.json()["total"] == 1
