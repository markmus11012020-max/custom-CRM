from __future__ import annotations

from datetime import UTC, datetime

from app.services.reports import next_cron_run
from tests.helpers import headers


def test_cron_next_run():
    base = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    nxt = next_cron_run("0 9 * * *", base)
    assert nxt.hour == 9
    assert nxt.minute == 0


def test_generate_report_without_google(admin):
    client, token = admin
    response = client.post(
        "/api/reports/generate",
        json={"report_type": "summary"},
        headers=headers(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "generated"
    assert data["spreadsheet_url"] == ""
    assert data["summary"]
    assert data["error"] == ""


def test_report_schedule_crud(admin):
    client, token = admin
    response = client.post(
        "/api/report-schedules",
        json={
            "report_type": "finance",
            "cron_expression": "0 9 * * *",
            "recipients_email": "owner@example.com",
            "channels": "email",
        },
        headers=headers(token),
    )
    assert response.status_code == 201, response.text
    schedule = response.json()
    assert schedule["is_active"] is True
    assert schedule["next_run_at"]

    response = client.get("/api/report-schedules")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = client.post(
        f"/api/report-schedules/{schedule['id']}/run",
        headers=headers(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["report_type"] == "finance"

    response = client.delete(
        f"/api/report-schedules/{schedule['id']}", headers=headers(token)
    )
    assert response.status_code == 200


def test_csv_export(admin):
    client, token = admin
    client.post(
        "/api/clients",
        json={"name": "Экспортный клиент", "company": "ООО Экспорт"},
        headers=headers(token),
    )
    response = client.get("/api/export/clients")
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "Экспортный клиент".encode() in response.content
