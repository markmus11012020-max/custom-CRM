"""Google Docs API: создание документов от имени пользователя."""

from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings, get_logger
from app.google import GoogleIntegrationError
from app.google.auth import load_user_credentials
from app.google.drive import GoogleDriveClient

LOGGER = get_logger("google.docs")


class GoogleDocsClient:
    def __init__(self, credentials=None, settings: Settings | None = None) -> None:  # type: ignore[no-untyped-def]
        if credentials is None:
            if settings is None:
                raise ValueError("Нужны credentials или settings")
            credentials = load_user_credentials(settings)
        self.credentials = credentials
        self.service = build("docs", "v1", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _raise(exc: HttpError, action: str) -> None:
        status = getattr(exc.resp, "status", None)
        detail = ""
        try:
            detail = exc.content.decode("utf-8", errors="replace")[:1000]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        raise GoogleIntegrationError(f"{action}: Google Docs API HTTP {status}: {detail}") from exc

    def create_document(self, title: str, folder_id: str | None = None) -> dict[str, Any]:
        try:
            document = self.service.documents().create(body={"title": title}).execute()
        except HttpError as exc:
            self._raise(exc, "Создание документа")
        document_id = document.get("documentId", "")
        url = f"https://docs.google.com/document/d/{document_id}/edit"
        if folder_id:
            drive = GoogleDriveClient(self.credentials)
            drive.move_file(document_id, folder_id, old_parent="root")
        LOGGER.info("Создан Google Документ %s", document_id)
        return {"id": document_id, "name": title, "url": url, "mime_type": "application/vnd.google-apps.document"}

    def get_document(self, document_id: str) -> dict[str, Any]:
        try:
            return self.service.documents().get(documentId=document_id).execute()
        except HttpError as exc:
            self._raise(exc, "Чтение документа")
        return {}

    def append_text(self, document_id: str, text: str) -> None:
        document = self.get_document(document_id)
        body = document.get("body", {}).get("content", [])
        end_index = 1
        if body:
            end_index = max(int(item.get("endIndex", 2)) for item in body) - 1
        requests = [
            {
                "insertText": {
                    "location": {"index": max(1, end_index)},
                    "text": text,
                }
            }
        ]
        try:
            self.service.documents().batchUpdate(
                documentId=document_id, body={"requests": requests}
            ).execute()
        except HttpError as exc:
            self._raise(exc, "Запись в документ")

    def create_text_document(
        self, title: str, text: str, folder_id: str | None = None
    ) -> dict[str, Any]:
        result = self.create_document(title, folder_id)
        if text:
            self.append_text(result["id"], text)
        return result
