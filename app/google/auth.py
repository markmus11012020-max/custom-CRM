"""Авторизация Google: сервисный аккаунт и OAuth2 пользователя."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import Settings, get_logger
from app.google import GoogleIntegrationError

LOGGER = get_logger("google.auth")
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
]


def service_account_credentials(settings: Settings) -> service_account.Credentials:
    path = settings.service_account_path
    if not path.exists():
        raise GoogleIntegrationError(
            f"Не найден JSON сервисного аккаунта: {path}. "
            "Положите ключ в secrets/service_account.json."
        )
    try:
        return service_account.Credentials.from_service_account_file(str(path), scopes=SCOPES)
    except Exception as exc:  # noqa: BLE001
        raise GoogleIntegrationError(f"Не удалось прочитать ключ сервисного аккаунта: {exc}") from exc


def load_user_credentials(settings: Settings, *, refresh: bool = True) -> Credentials:
    path = settings.oauth_token_path
    if not path.exists():
        raise GoogleIntegrationError(
            "OAuth2-токен не найден. Выполните: python -m app.google.oauth_user --login"
        )
    try:
        credentials = Credentials.from_authorized_user_file(str(path), SCOPES)
    except Exception as exc:  # noqa: BLE001
        raise GoogleIntegrationError(f"Не удалось прочитать token.json: {exc}") from exc

    if refresh and not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                save_user_credentials(settings, credentials)
            except Exception as exc:  # noqa: BLE001
                raise GoogleIntegrationError(
                    f"Не удалось обновить OAuth2-токен: {exc}. Повторите вход."
                ) from exc
    return credentials


def save_user_credentials(settings: Settings, credentials: Credentials) -> None:
    path = settings.oauth_token_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json(), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None
    state: str | None = None
    expected_state: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        error = query.get("error", [None])[0]
        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        if error:
            type(self).error = error
        elif state and type(self).expected_state and state != type(self).expected_state:
            type(self).error = "Неверный state OAuth2"
        elif code:
            type(self).code = code
            type(self).state = state
        body = (
            "<html><body style='font-family:Arial;background:#F7F8FC;color:#0F172A;"
            "display:flex;align-items:center;justify-content:center;height:100vh'>"
            "<div style='background:#fff;border:1px solid #E2E8F0;border-radius:12px;"
            "padding:32px;max-width:520px;box-shadow:0 18px 50px -28px rgba(15,23,42,.22)'>"
            "<h2 style='color:#4338CA'>Custom-CRM</h2>"
            "<p>Авторизация Google завершена. Можно закрыть эту страницу и вернуться в терминал.</p>"
            "</div></body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):  # noqa: A002
        LOGGER.debug("OAuth callback: " + format, *args)


def run_oauth_login(
    settings: Settings,
    *,
    port: int = 8765,
    open_browser: bool = True,
) -> Credentials:
    client_secret = settings.oauth_client_secret_path
    if not client_secret.exists():
        raise GoogleIntegrationError(
            f"Не найден client_secret JSON: {client_secret}. "
            "Положите OAuth-ключ в secrets/client_secret.json."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    redirect_uri = settings.google_oauth_redirect_uri or f"http://localhost:{port}/"
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        redirect_uri=redirect_uri,
    )

    handler = _OAuthCallbackHandler
    handler.code = None
    handler.error = None
    handler.state = None
    handler.expected_state = state
    server = HTTPServer(("0.0.0.0", port), handler)

    print("\nОткройте эту ссылку в браузере и подтвердите доступ:\n")
    print(auth_url)
    print(
        "\nЕсли Google сообщает о неверном redirect_uri, добавьте в OAuth-клиент "
        f"точный URI: {redirect_uri}\n"
    )
    if open_browser:
        try:
            webbrowser.open(auth_url)
        except Exception:  # noqa: BLE001
            pass

    server.serve_forever()
    server.server_close()
    if handler.error:
        raise GoogleIntegrationError(f"OAuth2 завершился ошибкой: {handler.error}")
    if not handler.code:
        raise GoogleIntegrationError("OAuth2 не вернул код авторизации")

    flow.fetch_token(code=handler.code, redirect_uri=redirect_uri)
    credentials = flow.credentials
    save_user_credentials(settings, credentials)
    LOGGER.info("OAuth2-токен сохранён: %s", settings.oauth_token_path)
    return credentials


def oauth_status(settings: Settings) -> dict:
    result = {
        "client_secret_exists": settings.oauth_client_secret_path.exists(),
        "token_exists": settings.oauth_token_path.exists(),
        "valid": False,
        "error": "",
    }
    if not result["token_exists"]:
        result["error"] = "Токен не создан"
        return result
    try:
        credentials = load_user_credentials(settings)
        result["valid"] = bool(credentials.valid or credentials.refresh_token)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def service_account_status(settings: Settings) -> dict:
    result = {
        "file_exists": settings.service_account_path.exists(),
        "email": settings.google_service_account_email,
        "project": "",
        "error": "",
    }
    if not settings.service_account_path.exists():
        result["error"] = "JSON сервисного аккаунта не найден"
        return result
    try:
        data = json.loads(settings.service_account_path.read_text(encoding="utf-8"))
        result["email"] = data.get("client_email", result["email"])
        result["project"] = data.get("project_id", "")
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"Не удалось прочитать JSON: {exc}"
    return result
