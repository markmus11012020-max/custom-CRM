"""Настройки приложения, читаемые из .env."""

from __future__ import annotations

import logging
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Custom-CRM"
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./data/crm.db"
    admin_email: str = "admin@example.com"
    admin_password: str = "ChangeMe123!"
    admin_name: str = "Администратор"
    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    scheduler_enabled: bool = True
    per_page: int = 20
    seed_demo: bool = True

    google_service_account_file: str = "secrets/service_account.json"
    google_oauth_client_secret_file: str = "secrets/client_secret.json"
    google_oauth_token_file: str = "secrets/token.json"
    google_drive_folder_id: str = ""
    google_drive_folder_name: str = "custom-CRM"
    google_service_account_email: str = ""
    report_spreadsheet_id: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8765/"
    google_oauth_scopes: str = (
        "https://www.googleapis.com/auth/drive,"
        "https://www.googleapis.com/auth/documents,"
        "https://www.googleapis.com/auth/spreadsheets"
    )

    robokassa_merchant_login: str = "demo_merchant"
    robokassa_password1: str = "demo_password_1"
    robokassa_password2: str = "demo_password_2"
    robokassa_test_mode: bool = True
    robokassa_result_url: str = "http://127.0.0.1:8000/payments/robokassa/result"
    robokassa_success_url: str = "http://127.0.0.1:8000/payments/robokassa/success"
    robokassa_fail_url: str = "http://127.0.0.1:8000/payments/robokassa/fail"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True

    telegram_bot_token: str = ""
    telegram_default_chat_id: str = ""

    aitunnel_api_key: str = ""
    aitunnel_base_url: str = "https://api.aitunnel.ru/v1"
    aitunnel_model: str = "deepseek-v4.1-flash-1017"
    ai_timeout: float = 30.0
    ai_retries: int = 2

    # ---- пути и производные значения ------------------------------------
    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def service_account_path(self) -> Path:
        return self.resolve_path(self.google_service_account_file)

    @property
    def oauth_client_secret_path(self) -> Path:
        return self.resolve_path(self.google_oauth_client_secret_file)

    @property
    def oauth_token_path(self) -> Path:
        return self.resolve_path(self.google_oauth_token_file)

    @property
    def google_scopes_list(self) -> list[str]:
        return [item.strip() for item in self.google_oauth_scopes.split(",") if item.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def google_service_account_configured(self) -> bool:
        return self.service_account_path.exists()

    @property
    def google_oauth_configured(self) -> bool:
        return self.oauth_client_secret_path.exists()

    @property
    def google_oauth_authorized(self) -> bool:
        return self.oauth_token_path.exists()

    @property
    def robokassa_configured(self) -> bool:
        return bool(
            self.robokassa_merchant_login
            and self.robokassa_password1
            and self.robokassa_password2
            and not self.robokassa_merchant_login.startswith("demo_")
        )

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def ai_configured(self) -> bool:
        return bool(self.aitunnel_api_key and self.aitunnel_base_url and self.aitunnel_model)

    def ensure_directories(self) -> None:
        for path in (
            BASE_DIR / "data",
            BASE_DIR / "data" / "backups",
            BASE_DIR / "logs",
            BASE_DIR / "secrets",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


def setup_logging(settings: Settings | None = None) -> logging.Logger:
    settings = settings or get_settings()
    logger = logging.getLogger("custom_crm")
    if getattr(logger, "_custom_crm_configured", False):
        return logger

    settings.ensure_directories()
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%d.%m.%Y %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        BASE_DIR / "logs" / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    logger.propagate = False
    logger._custom_crm_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"custom_crm.{name}" if name else "custom_crm")
