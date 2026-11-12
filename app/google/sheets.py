"""Google Sheets API: создание, запись и оформление отчётов."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings, get_logger
from app.google import GoogleIntegrationError
from app.google.auth import service_account_credentials
from app.google.drive import GoogleDriveClient

LOGGER = get_logger("google.sheets")

PRIMARY = {"red": 67 / 255, "green": 56 / 255, "blue": 202 / 255}
ACCENT = {"red": 13 / 255, "green": 148 / 255, "blue": 136 / 255}
DARK = {"red": 15 / 255, "green": 23 / 255, "blue": 42 / 255}
LIGHT = {"red": 247 / 255, "green": 248 / 255, "blue": 252 / 255}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
BORDER = {"red": 226 / 255, "green": 232 / 255, "blue": 240 / 255}


def quote_sheet(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def column_letter(index: int) -> str:
    """1 -> A, 27 -> AA."""
    if index < 1:
        raise ValueError("Индекс колонки начинается с 1")
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


class GoogleSheetsClient:
    def __init__(self, credentials=None, settings: Settings | None = None) -> None:  # type: ignore[no-untyped-def]
        if credentials is None:
            if settings is None:
                raise ValueError("Нужны credentials или settings")
            credentials = service_account_credentials(settings)
        self.credentials = credentials
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _raise(exc: HttpError, action: str) -> None:
        status = getattr(exc.resp, "status", None)
        detail = ""
        try:
            detail = exc.content.decode("utf-8", errors="replace")[:1000]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        raise GoogleIntegrationError(f"{action}: Google Sheets API HTTP {status}: {detail}") from exc

    def get_spreadsheet(self, spreadsheet_id: str) -> dict[str, Any]:
        try:
            return self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        except HttpError as exc:
            self._raise(exc, "Чтение таблицы")
        return {}

    def create_spreadsheet(self, title: str, folder_id: str | None = None) -> dict[str, Any]:
        try:
            result = (
                self.service.spreadsheets()
                .create(body={"properties": {"title": title}})
                .execute()
            )
        except HttpError as exc:
            self._raise(exc, "Создание таблицы")
        spreadsheet_id = result.get("spreadsheetId", "")
        url = result.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
        if folder_id:
            drive = GoogleDriveClient(self.credentials)
            drive.move_file(spreadsheet_id, folder_id, old_parent="root")
        LOGGER.info("Создана Google Таблица %s", spreadsheet_id)
        return {
            "id": spreadsheet_id,
            "name": title,
            "url": url,
            "mime_type": "application/vnd.google-apps.spreadsheet",
        }

    def add_sheet(self, spreadsheet_id: str, title: str) -> int:
        body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
        try:
            result = self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body=body
            ).execute()
            return int(result["replies"][0]["addSheet"]["properties"]["sheetId"])
        except HttpError as exc:
            self._raise(exc, "Создание листа")
        return 0

    def sheet_exists(self, spreadsheet_id: str, title: str) -> bool:
        meta = self.get_spreadsheet(spreadsheet_id)
        return any(
            sheet.get("properties", {}).get("title") == title
            for sheet in meta.get("sheets", [])
        )

    def write_values(
        self,
        spreadsheet_id: str,
        sheet_title: str,
        values: Sequence[Sequence[Any]],
        start_row: int = 1,
        start_col: int = 1,
    ) -> None:
        start = f"{column_letter(start_col)}{start_row}"
        a1_range = f"{quote_sheet(sheet_title)}!{start}"
        body = {"values": [list(row) for row in values]}
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=a1_range,
                valueInputOption="USER_ENTERED",
                body=body,
            ).execute()
        except HttpError as exc:
            self._raise(exc, "Запись данных")

    def read_values(self, spreadsheet_id: str, a1_range: str) -> list[list[Any]]:
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=a1_range)
                .execute()
            )
            return result.get("values", [])
        except HttpError as exc:
            self._raise(exc, "Чтение данных")
        return []

    def batch_update(self, spreadsheet_id: str, requests: list[dict[str, Any]]) -> None:
        if not requests:
            return
        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests}
            ).execute()
        except HttpError as exc:
            self._raise(exc, "Форматирование таблицы")

    def format_report(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        *,
        title_rows: int = 2,
        header_row: int = 4,
        last_row: int = 20,
        columns: int = 6,
        column_widths: list[int] | None = None,
    ) -> None:
        """Оформление отчёта: заголовок, шапка, границы, ширины, закрепление."""
        requests: list[dict[str, Any]] = []
        # Заголовок
        requests.append(
            {
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": columns,
                    },
                    "mergeType": "MERGE_ALL",
                }
            }
        )
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": columns,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": PRIMARY,
                            "textFormat": {
                                "foregroundColor": WHITE,
                                "fontSize": 18,
                                "bold": True,
                                "fontFamily": "Arial",
                            },
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            }
        )
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 42},
                    "fields": "pixelSize",
                }
            }
        )
        # Шапка таблицы
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": header_row - 1,
                        "endRowIndex": header_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": columns,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": ACCENT,
                            "textFormat": {
                                "foregroundColor": WHITE,
                                "fontSize": 10,
                                "bold": True,
                                "fontFamily": "Arial",
                            },
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)",
                }
            }
        )
        # Границы и выравнивание
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": last_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": columns,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "borders": {
                                "top": {"style": "SOLID", "color": BORDER},
                                "bottom": {"style": "SOLID", "color": BORDER},
                                "left": {"style": "SOLID", "color": BORDER},
                                "right": {"style": "SOLID", "color": BORDER},
                            }
                        }
                    },
                    "fields": "userEnteredFormat.borders",
                }
            }
        )
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": header_row},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )
        for index, width in enumerate(column_widths or [180, 140, 140, 140, 140, 160]):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": index,
                            "endIndex": index + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )
        self.batch_update(spreadsheet_id, requests)

    def add_column_chart(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        *,
        title: str,
        start_row: int,
        end_row: int,
        category_column: int = 0,
        value_column: int = 1,
        anchor_row: int = 1,
        anchor_column: int = 7,
    ) -> None:
        chart = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": title,
                        "basicChart": {
                            "chartType": "COLUMN",
                            "legendPosition": "BOTTOM_LEGEND",
                            "headerCount": 1,
                            "domains": [
                                {
                                    "domain": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": sheet_id,
                                                    "startRowIndex": start_row,
                                                    "endRowIndex": end_row,
                                                    "startColumnIndex": category_column,
                                                    "endColumnIndex": category_column + 1,
                                                }
                                            ]
                                        }
                                    }
                                }
                            ],
                            "series": [
                                {
                                    "series": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": sheet_id,
                                                    "startRowIndex": start_row,
                                                    "endRowIndex": end_row,
                                                    "startColumnIndex": value_column,
                                                    "endColumnIndex": value_column + 1,
                                                }
                                            ]
                                        }
                                    },
                                    "targetAxis": "LEFT_AXIS",
                                }
                            ],
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": sheet_id,
                                "rowIndex": anchor_row,
                                "columnIndex": anchor_column,
                            },
                            "widthPixels": 620,
                            "heightPixels": 360,
                        }
                    },
                }
            }
        }
        self.batch_update(spreadsheet_id, [chart])
