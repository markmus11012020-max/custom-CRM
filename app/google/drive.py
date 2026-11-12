"""Google Drive API: файлы, папки, права."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.config import Settings, get_logger
from app.google import GoogleIntegrationError
from app.google.auth import service_account_credentials

LOGGER = get_logger("google.drive")

FILE_FIELDS = "id,name,mimeType,webViewLink,webContentLink,size,modifiedTime,parents,trashed"


class GoogleDriveClient:
    """CRUD Google Drive. По умолчанию работает через сервисный аккаунт."""

    def __init__(self, credentials=None, settings: Settings | None = None) -> None:  # type: ignore[no-untyped-def]
        if credentials is None:
            if settings is None:
                raise ValueError("Нужны credentials или settings")
            credentials = service_account_credentials(settings)
        self.credentials = credentials
        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    # ------------------------------------------------------------------
    @staticmethod
    def _file_dict(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "mime_type": item.get("mimeType", ""),
            "web_url": item.get("webViewLink", ""),
            "size": item.get("size", ""),
            "modified_time": item.get("modifiedTime", ""),
            "parents": item.get("parents", []),
        }

    @staticmethod
    def _raise(exc: HttpError, action: str) -> None:
        status = getattr(exc.resp, "status", None)
        detail = ""
        try:
            detail = exc.content.decode("utf-8", errors="replace")[:1000]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        if status == 403:
            raise GoogleIntegrationError(
                f"{action}: доступ запрещён. Проверьте, что папка/файл расшарены "
                f"сервисному аккаунту с ролью Editor. Детали: {detail}"
            ) from exc
        if status == 404:
            raise GoogleIntegrationError(f"{action}: файл или папка не найдены. {detail}") from exc
        raise GoogleIntegrationError(f"{action}: Google Drive API HTTP {status}: {detail}") from exc

    # ------------------------------------------------------------------
    def list_files(self, folder_id: str | None = None, page_size: int = 100) -> list[dict[str, Any]]:
        query = "trashed=false"
        if folder_id:
            query += f" and '{folder_id}' in parents"
        items: list[dict[str, Any]] = []
        page_token = None
        try:
            while True:
                response = (
                    self.service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields=f"nextPageToken,files({FILE_FIELDS})",
                        pageSize=min(page_size, 1000),
                        pageToken=page_token,
                        orderBy="modifiedTime desc",
                    )
                    .execute()
                )
                items.extend(self._file_dict(item) for item in response.get("files", []))
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            self._raise(exc, "Список файлов")
        return items

    def get_file(self, file_id: str) -> dict[str, Any]:
        try:
            item = self.service.files().get(fileId=file_id, fields=FILE_FIELDS).execute()
            return self._file_dict(item)
        except HttpError as exc:
            self._raise(exc, "Получение файла")
        return {}

    def find_folder(self, name: str, parent_id: str = "root") -> dict[str, Any] | None:
        query = (
            f"name = '{name.replace(chr(39), chr(92) + chr(39))}' "
            "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        if parent_id and parent_id != "root":
            query += f" and '{parent_id}' in parents"
        try:
            response = (
                self.service.files()
                .list(q=query, fields=f"files({FILE_FIELDS})", pageSize=1)
                .execute()
            )
        except HttpError as exc:
            self._raise(exc, "Поиск папки")
        files = response.get("files", [])
        return self._file_dict(files[0]) if files else None

    def create_folder(self, name: str, parent_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            body["parents"] = [parent_id]
        try:
            item = (
                self.service.files()
                .create(body=body, fields=FILE_FIELDS)
                .execute()
            )
            return self._file_dict(item)
        except HttpError as exc:
            self._raise(exc, "Создание папки")
        return {}

    def upload_file(
        self,
        local_path: str | Path,
        folder_id: str | None = None,
        name: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        path = Path(local_path)
        if not path.exists():
            raise GoogleIntegrationError(f"Локальный файл не найден: {path}")
        metadata: dict[str, Any] = {"name": name or path.name}
        if folder_id:
            metadata["parents"] = [folder_id]
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=False)
        try:
            item = (
                self.service.files()
                .create(body=metadata, media_body=media, fields=FILE_FIELDS)
                .execute()
            )
            return self._file_dict(item)
        except HttpError as exc:
            self._raise(exc, "Загрузка файла")
        return {}

    def move_file(self, file_id: str, folder_id: str, old_parent: str | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "fileId": file_id,
            "addParents": folder_id,
            "fields": FILE_FIELDS,
        }
        if old_parent:
            kwargs["removeParents"] = old_parent
        try:
            item = self.service.files().update(**kwargs).execute()
            return self._file_dict(item)
        except HttpError as exc:
            self._raise(exc, "Перемещение файла")
        return {}

    def rename_file(self, file_id: str, name: str) -> dict[str, Any]:
        try:
            item = (
                self.service.files()
                .update(fileId=file_id, body={"name": name}, fields=FILE_FIELDS)
                .execute()
            )
            return self._file_dict(item)
        except HttpError as exc:
            self._raise(exc, "Переименование файла")
        return {}

    def trash_file(self, file_id: str) -> dict[str, Any]:
        try:
            item = (
                self.service.files()
                .update(fileId=file_id, body={"trashed": True}, fields=FILE_FIELDS)
                .execute()
            )
            return self._file_dict(item)
        except HttpError as exc:
            self._raise(exc, "Удаление в корзину")
        return {}

    def delete_file(self, file_id: str) -> None:
        try:
            self.service.files().delete(fileId=file_id).execute()
        except HttpError as exc:
            self._raise(exc, "Удаление файла")

    def share_file(self, file_id: str, email: str, role: str = "writer") -> dict[str, Any]:
        body = {"type": "user", "role": role, "emailAddress": email}
        try:
            permission = (
                self.service.permissions()
                .create(fileId=file_id, body=body, fields="id,emailAddress,role,type")
                .execute()
            )
            return dict(permission)
        except HttpError as exc:
            self._raise(exc, "Выдача доступа")
        return {}

    def export_file(self, file_id: str, mime_type: str, destination: str | Path) -> Path:
        destination = Path(destination)
        try:
            data = self.service.files().export(fileId=file_id, mimeType=mime_type).execute()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            return destination
        except HttpError as exc:
            self._raise(exc, "Экспорт файла")
        return destination

    def download_file(self, file_id: str, destination: str | Path) -> Path:
        destination = Path(destination)
        try:
            data = self.service.files().get_media(fileId=file_id).execute()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            return destination
        except HttpError as exc:
            self._raise(exc, "Скачивание файла")
        return destination
