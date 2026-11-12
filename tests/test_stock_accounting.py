from __future__ import annotations

from tests.helpers import headers


def test_stock_movements_and_low_stock(admin):
    client, token = admin
    response = client.post(
        "/api/products",
        json={"name": "Товар", "sku": "STOCK-1", "price": 1000, "cost": 500, "min_stock": 3},
        headers=headers(token),
    )
    product_id = response.json()["id"]

    response = client.post(
        "/api/stock/movements",
        json={"product_id": product_id, "movement_type": "in", "quantity": 10, "unit_cost": 500},
        headers=headers(token),
    )
    assert response.status_code == 201
    response = client.post(
        "/api/stock/movements",
        json={"product_id": product_id, "movement_type": "out", "quantity": 6},
        headers=headers(token),
    )
    assert response.status_code == 201
    response = client.get(f"/api/products/{product_id}")
    assert response.json()["stock_qty"] == "4.000"

    response = client.get("/api/stock/low")
    assert response.status_code == 200
    assert response.json() == []

    response = client.post(
        "/api/stock/movements",
        json={"product_id": product_id, "movement_type": "out", "quantity": 100},
        headers=headers(token),
    )
    assert response.status_code == 409

    response = client.post(
        "/api/stock/movements",
        json={"product_id": product_id, "movement_type": "adjust", "quantity": 2},
        headers=headers(token),
    )
    assert response.status_code == 201
    response = client.get("/api/stock/low")
    assert any(item["id"] == product_id for item in response.json())

    response = client.get("/api/stock/value")
    assert response.status_code == 200
    assert response.json()["value"] == "1000.00"


def test_accounting_summary_and_export(admin):
    client, token = admin
    response = client.post(
        "/api/transactions",
        json={
            "type": "income",
            "category": "Продажи",
            "amount": 10000,
            "transaction_date": "2026-11-01",
            "description": "Оплата",
        },
        headers=headers(token),
    )
    assert response.status_code == 201
    response = client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "category": "Подрядчики",
            "amount": 4000,
            "transaction_date": "2026-11-02",
            "description": "Работа",
        },
        headers=headers(token),
    )
    assert response.status_code == 201
    response = client.get("/api/accounting/summary")
    data = response.json()
    assert data["income"] == "10000.00"
    assert data["expense"] == "4000.00"
    assert data["profit"] == "6000.00"

    response = client.get("/api/export/transactions")
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "Продажи".encode() in response.content
