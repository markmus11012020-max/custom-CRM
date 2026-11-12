"""API Google-интеграций."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.google import GoogleIntegrationError
from app.google.auth import (
    load_user_credentials,
    oauth_status,
    service_account_status,
)
from app.google.bootstrap import ensure_folder, resolve_folder_id
from app.google.docs import GoogleDocsClient
from app.google.drive import GoogleDriveClient
from app.google.sheets import GoogleSheetsClient
from app.models import Client, Deal, GoogleFile
from app.schemas import GoogleDocCreate, GoogleSheetCreate
from app.services.access import get_project_for_user

router = APIRouter(prefix="/api/google", tags=["google"])


def _folder_id(request: Request) -> str:
    database = request.app.state.db
    return resolve_folder_id(request.app.state.settings, database)


def _save_file(
    db: DbSession,
    *,
    entity_type: str,
    entity_id: int | None,
    file_data: dict,
) -> None:
    if not entity_type or not entity_id:
        return
    db.add(
        GoogleFile(
            entity_type=entity_type,
            entity_id=entity_id,
            file_id=file_data.get("id", ""),
            name=file_data.get("name", ""),
            mime_type=file_data.get("mime_type", ""),
            web_url=file_data.get("url", file_data.get("web_url", "")),
        )
    )


@router.get("/status")
def status(request: Request, user: CurrentUser):
    settings = request.app.state.settings
    database = request.app.state.db
    return {
        "service_account": service_account_status(settings),
        "oauth": oauth_status(settings),
        "folder_id": resolve_folder_id(settings, database),
        "report_spreadsheet_id": settings.report_spreadsheet_id,
        "drive_folder_name": settings.google_drive_folder_name,
        "service_account_email": settings.google_service_account_email,
    }


@router.get("/files")
def list_files(request: Request, db: DbSession, user: CurrentUser, folder_id: str | None = None):
    settings = request.app.state.settings
    folder = folder_id or _folder_id(request) or None
    try:
        client = GoogleDriveClient(settings=settings)
        return {"folder_id": folder or "", "files": client.list_files(folder_id=folder)}
    except GoogleIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/bootstrap")
def bootstrap(request: Request, db: DbSession, user: CurrentUser):
    settings = request.app.state.settings
    database = request.app.state.db
    try:
        folder = ensure_folder(settings, database=database)
        return {"folder_id": folder["id"], "url": folder["web_url"], "name": folder["name"]}
    except GoogleIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/docs", status_code=201)
def create_document(payload: GoogleDocCreate, request: Request, db: DbSession, user: CurrentUser):
    settings = request.app.state.settings
    folder_id = _folder_id(request)
    try:
        credentials = load_user_credentials(settings)
        client = GoogleDocsClient(credentials)
        text = payload.body
        if payload.entity_type == "client" and payload.entity_id:
            client_obj = db.get(Client, payload.entity_id)
            if client_obj is None:
                raise HTTPException(status_code=404, detail="Клиент не найден")
            get_project_for_user(db, client_obj.project_id, user)
            text = text or (
                f"Клиент: {client_obj.name}\n"
                f"Компания: {client_obj.company}\n"
                f"Email: {client_obj.email}\n"
                f"Телефон: {client_obj.phone}\n"
                f"Заметки: {client_obj.notes}\n"
            )
        elif payload.entity_type == "deal" and payload.entity_id:
            deal = db.get(Deal, payload.entity_id)
            if deal is None:
                raise HTTPException(status_code=404, detail="Сделка не найдена")
            get_project_for_user(db, deal.project_id, user)
            text = text or (
                f"Сделка: {deal.title}\n"
                f"Сумма: {deal.amount} {deal.currency}\n"
                f"Этап: {deal.stage}\n"
                f"Описание: {deal.description}\n"
            )
        document = client.create_text_document(payload.title, text, folder_id or None)
        _save_file(
            db,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            file_data=document,
        )
        db.commit()
        return document
    except GoogleIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sheets", status_code=201)
def create_sheet(payload: GoogleSheetCreate, request: Request, db: DbSession, user: CurrentUser):
    settings = request.app.state.settings
    folder_id = _folder_id(request)
    try:
        credentials = load_user_credentials(settings)
        client = GoogleSheetsClient(credentials)
        spreadsheet = client.create_spreadsheet(payload.title, folder_id or None)
        _save_file(
            db,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            file_data=spreadsheet,
        )
        db.commit()
        return spreadsheet
    except GoogleIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
