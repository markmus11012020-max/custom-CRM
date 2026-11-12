"""Точка входа Google Drive через сервисный аккаунт.

Примеры:
    python -m app.google.service_account --list
    python -m app.google.service_account --list --folder-id 1AbC...
    python -m app.google.service_account --create-folder "Отчёты"
    python -m app.google.service_account --upload ./report.csv --folder-id 1AbC...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.google import GoogleIntegrationError
from app.google.drive import GoogleDriveClient


def _print_files(files: list[dict]) -> None:
    if not files:
        print("(файлов нет)")
        return
    for item in files:
        print(
            f"{item['name']}\n"
            f"  id: {item['id']}\n"
            f"  type: {item['mime_type']}\n"
            f"  modified: {item['modified_time']}\n"
            f"  url: {item['web_url']}\n"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Google Drive через сервисный аккаунт")
    parser.add_argument("--list", action="store_true", help="Показать файлы папки")
    parser.add_argument("--folder-id", default="", help="ID папки Google Drive")
    parser.add_argument("--create-folder", metavar="NAME", help="Создать папку")
    parser.add_argument("--upload", metavar="PATH", help="Загрузить файл")
    parser.add_argument("--delete", metavar="FILE_ID", help="Удалить файл безвозвратно")
    args = parser.parse_args(argv)

    settings = get_settings()
    folder_id = args.folder_id or settings.google_drive_folder_id
    try:
        client = GoogleDriveClient(settings=settings)
        if args.create_folder:
            folder = client.create_folder(args.create_folder, parent_id=folder_id or None)
            print(f"Создана папка: {folder['name']} ({folder['id']})")
            print(folder["web_url"])
            return 0
        if args.upload:
            file = client.upload_file(Path(args.upload), folder_id=folder_id or None)
            print(f"Загружен файл: {file['name']} ({file['id']})")
            print(file["web_url"])
            return 0
        if args.delete:
            client.delete_file(args.delete)
            print(f"Удалён файл {args.delete}")
            return 0
        files = client.list_files(folder_id=folder_id or None)
        print(f"Файлов: {len(files)}")
        print(f"Папка: {folder_id or '(все доступные файлы)'}\n")
        _print_files(files)
        return 0
    except GoogleIntegrationError as exc:
        print(f"[ОШИБКА] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
