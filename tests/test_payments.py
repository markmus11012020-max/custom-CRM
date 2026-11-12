from __future__ import annotations

import hashlib

from tests.helpers import headers


def _payment(client, token, method="robokassa", amount=1000):
    response = client.post(
        "/api/payments",
        json={"amount": amount, "method": method, "description": "Тестовый счёт"},
        headers=headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_robokassa_link_and_mark_paid(admin, settings):
    client, token = admin
    payment = _payment(client, token)
    assert payment["inv_id"]
    assert "MerchantLogin=test_merchant" in payment["robokassa_link"]
    assert "IsTest=1" in payment["robokassa_link"]
    expected = hashlib.md5(
        f"test_merchant:1000.00:{payment['inv_id']}:test_password_1".encode()
    ).hexdigest()
    assert expected in payment["robokassa_link"]

    response = client.post(
        f"/api/payments/{payment['id']}/mark-paid", headers=headers(token)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "paid"

    response = client.get("/api/accounting/summary")
    assert response.status_code == 200
    assert response.json()["income"] == "1000.00"

    response = client.post(
        f"/api/payments/{payment['id']}/refund", headers=headers(token)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "refunded"
    response = client.get("/api/accounting/summary")
    assert response.json()["expense"] == "1000.00"


def test_robokassa_result_callback(admin, settings):
    client, token = admin
    payment = _payment(client, token, amount=1500)
    signature = hashlib.md5(
        f"1500.00:{payment['inv_id']}:test_password_2".encode()
    ).hexdigest()
    response = client.post(
        "/payments/robokassa/result",
        data={
            "OutSum": "1500.00",
            "InvId": payment["inv_id"],
            "SignatureValue": signature,
        },
    )
    assert response.status_code == 200
    assert response.text == f"OK{payment['inv_id']}"

    response = client.get(f"/api/payments/{payment['id']}")
    assert response.json()["status"] == "paid"


def test_invalid_robokassa_signature(admin):
    client, token = admin
    payment = _payment(client, token)
    response = client.post(
        "/payments/robokassa/result",
        data={
            "OutSum": "1000.00",
            "InvId": payment["inv_id"],
            "SignatureValue": "invalid",
        },
    )
    assert response.status_code == 400
    response = client.get(f"/api/payments/{payment['id']}")
    assert response.json()["status"] == "pending"
