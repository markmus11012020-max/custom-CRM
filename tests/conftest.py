from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.helpers import ADMIN_EMAIL, ADMIN_PASSWORD, headers, login


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        scheduler_enabled=False,
        seed_demo=False,
        admin_email=ADMIN_EMAIL,
        admin_password=ADMIN_PASSWORD,
        admin_name="Test Admin",
        secret_key="test-secret-key-for-pytest-only",
        aitunnel_api_key="",
        report_spreadsheet_id="",
        smtp_host="",
        smtp_from="",
        telegram_bot_token="",
        robokassa_merchant_login="test_merchant",
        robokassa_password1="test_password_1",
        robokassa_password2="test_password_2",
        robokassa_test_mode=True,
    )


@pytest.fixture()
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture()
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin(client: TestClient) -> tuple[TestClient, str]:
    token = login(client)
    return client, token


@pytest.fixture()
def auth_headers(admin: tuple[TestClient, str]) -> dict[str, str]:
    _, token = admin
    return headers(token)
