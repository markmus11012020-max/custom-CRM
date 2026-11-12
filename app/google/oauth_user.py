"""OAuth2-вход и создание Google Документов/Таблиц от имени пользователя.

Примеры:
    python -m app.google.oauth_user --login
    python -m app.google.oauth_user --status
    python -m app.google.oauth_user --create-test
    python -m app.google.oauth_user --list-files
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.database import Database
from app.google import GoogleIntegrationError
from app.google.auth import load_user_credentials, oauth_status, run_oauth_login
from app.google.bootstrap import ensure_folder, resolve_folder_id
from app.google.docs import GoogleDocsClient
from app.google.drive import GoogleDriveClient
from app.google.sheets import GoogleSheetsClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OAuth2 Google для Custom-CRM")
    parser.add_argument("--login", action="store_true", help="Выполнить вход через браузер")
    parser.add_argument("--no-browser", action="store_true", help="Не открывать браузер автоматически")
    parser.add_argument("--port", type=int, default=8765, help="Порт локального OAuth callback")
    parser.add_argument("--status", action="store_true", help="Показать статус OAuth2")
    parser.add_argument("--create-test", action="store_true", help="Создать тестовые Документ и Таблицу")
    parser.add_argument("--create-doc", metavar="TITLE", help="Создать Google Документ")
    parser.add_argument("--create-sheet", metavar="TITLE", help="Создать Google Таблицу")
    parser.add_argument("--list-files", action="store_true", help="Показать файлы рабочей папки")
    args = parser.parse_args(argv)

    settings = get_settings()
    database = Database(settings)
    database.create_all()

    if args.status:
        status = oauth_status(settings)
        print(f"client_secret: {status['client_secret_exists']}")
        print(f"token.json: {status['token_exists']}")
        print(f"authorized: {status['valid']}")
        if status["error"]:
            print(f"error: {status['error']}")
        return 0

    if args.login:
        try:
            run_oauth_login(
                settings,
                port=args.port,
                open_browser=not args.no_browser,
            )
        except GoogleIntegrationError as exc:
            print(f"[ОШИБКА] {exc}", file=sys.stderr)
            return 1
        print("OAuth2-токен сохранён.")
        return 0

    try:
        credentials = load_user_credentials(settings)
        folder_id = resolve_folder_id(settings, database)
        if not folder_id:
            folder = ensure_folder(settings, database=database)
            folder_id = folder["id"]
            print(f"Рабочая папка: {folder['web_url']}")

        if args.create_test:
            docs = GoogleDocsClient(credentials)
            sheets = GoogleSheetsClient(credentials)
            document = docs.create_text_document(
                "Custom-CRM: тестовый документ",
                "Этот документ создан Custom-CRM от имени пользователя через OAuth2.\n",
                folder_id,
            )
            spreadsheet = sheets.create_spreadsheet("Custom-CRM: тестовая таблица", folder_id)
            print(f"Документ: {document['url']}")
            print(f"Таблица: {spreadsheet['url']}")
            return 0
        if args.create_doc:
            docs = GoogleDocsClient(credentials)
            document = docs.create_text_document(args.create_doc, "Создано Custom-CRM.\n", folder_id)
            print(document["url"])
            return 0
        if args.create_sheet:
            sheets = GoogleSheetsClient(credentials)
            spreadsheet = sheets.create_spreadsheet(args.create_sheet, folder_id)
            print(spreadsheet["url"])
            return 0
        if args.list_files:
            drive = GoogleDriveClient(credentials)
            files = drive.list_files(folder_id=folder_id)
            print(f"Файлов: {len(files)}")
            for item in files:
                print(f"{item['name']} | {item['id']} | {item['web_url']}")
            return 0
    except GoogleIntegrationError as exc:
        print(f"[ОШИБКА] {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
