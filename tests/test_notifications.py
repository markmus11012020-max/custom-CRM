from __future__ import annotations


def test_test_email_is_skipped_without_smtp(admin):
    client, token = admin
    response = client.post("/admin/settings/test-email", data={"_csrf": token}, follow_redirects=False)
    assert response.status_code == 303

    response = client.get("/api/notifications")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert items[0]["status"] == "skipped"
    assert items[0]["channel"] == "email"
