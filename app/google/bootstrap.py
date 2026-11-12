"""Создание рабочей папки Google Drive и выдача доступа сервисному аккаунту."""

from __future__ import annotations

import argparse
import sys

from app.config import Settings, get_settings
from app.database import Database
from app.google import GoogleIntegrationError
from app.google.auth import load_user_credentials
from app.google.drive import GoogleDriveClient


def resolve_folder_id(settings: Settings, database: Database | None = None) -> str:
    if settings.google_drive_folder_id:
        return settings.google_drive_folder_id
    if database is not None:
        return database.get_setting("google_drive_folder_id", "")
    return ""


def ensure_folder(
    settings: Settings | None = None,
    *,
    folder_name: str | None = None,
    share_service_account: bool = True,
    database: Database | None = None,
) -> dict:
    settings = settings or get_settings()
    folder_name = folder_name or settings.google_drive_folder_name
    credentials = load_user_credentials(settings)
    drive = GoogleDriveClient(credentials)

    folder_id = resolve_folder_id(settings, database)
    if folder_id:
        try:
            return drive.get_file(folder_id)
        except GoogleIntegrationError:
            folder_id = ""

    folder = drive.find_folder(folder_name, parent_id="root")
    if folder is None:
        folder = drive.create_folder(folder_name, parent_id=None)
        print(f"Создана папка «{folder_name}»: {folder['web_url']}")
    else:
        print(f"Найдена папка «{folder_name}»: {folder['web_url']}")

    if share_service_account and settings.google_service_account_email:
        try:
            drive.share_file(folder["id"], settings.google_service_account_email, role="writer")
            print(f"Доступ выдан сервисному аккаунту {settings.google_service_account_email}")
        except GoogleIntegrationError as exc:
            print(f"Предупреждение при выдаче доступа: {exc}")

    if database is not None:
        database.set_setting("google_drive_folder_id", folder["id"])
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap папки Custom-CRM в Google Drive")
    parser.add_argument("--folder", default="", help="Имя папки")
    parser.add_argument("--no-share", action="store_true", help="Не выдавать доступ сервисному аккаунту")
    args = parser.parse_args(argv)
    settings = get_settings()
    database = Database(settings)
    database.create_all()
    try:
        folder = ensure_folder(
            settings,
            folder_name=args.folder or None,
            share_service_account=not args.no_share,
            database=database,
        )
    except GoogleIntegrationError as exc:
        print(f"[ОШИБКА] {exc}", file=sys.stderr)
        return 1
    print(f"Folder ID: {folder['id']}")
    print(f"URL: {folder['web_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
