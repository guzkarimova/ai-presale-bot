import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings
from database.database import SessionLocal
from database.models import Application


class GoogleDocsService:
    """Keep one row per client and append their messages horizontally."""

    @staticmethod
    def _get_credentials():
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if settings.google_service_account_file:
            return service_account.Credentials.from_service_account_file(
                Path(settings.google_service_account_file).expanduser(), scopes=scopes
            )
        if not settings.google_service_account_json:
            raise ValueError("Google service account credentials are not configured")
        service_account_info = json.loads(settings.google_service_account_json)
        return service_account.Credentials.from_service_account_info(service_account_info, scopes=scopes)

    @staticmethod
    def _build_service():
        return build("sheets", "v4", credentials=GoogleDocsService._get_credentials(), cache_discovery=False)

    @staticmethod
    def _get_sheet_title(service) -> str:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=settings.google_sheet_id,
            fields="sheets.properties(sheetId,title)",
        ).execute()
        requested_gid = settings.google_sheet_gid
        sheets = spreadsheet.get("sheets", [])
        for sheet in sheets:
            properties = sheet.get("properties", {})
            if requested_gid and str(properties.get("sheetId")) == requested_gid:
                return properties["title"]
        if sheets:
            return sheets[0]["properties"]["title"]
        raise ValueError("The Google spreadsheet has no sheets")

    @staticmethod
    def _column_letter(column_number: int) -> str:
        result = ""
        while column_number:
            column_number, remainder = divmod(column_number - 1, 26)
            result = chr(65 + remainder) + result
        return result

    @staticmethod
    def _client_label(application: Application, event: dict[str, Any]) -> str:
        name = event.get("full_name") or event.get("first_name") or "Клиент"
        username = event.get("username") or application.username
        parts = [name]
        if username:
            parts.append(f"@{str(username).lstrip('@')}")
        parts.append(f"ID {application.telegram_user_id}")
        return " (".join([parts[0], ", ".join(parts[1:]) + ")"])

    @staticmethod
    def _ensure_column_capacity(service, required_columns: int) -> None:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=settings.google_sheet_id,
            fields="sheets.properties(sheetId,gridProperties.columnCount)",
        ).execute()
        sheets = spreadsheet.get("sheets", [])
        target = next(
            (
                item["properties"]
                for item in sheets
                if str(item["properties"].get("sheetId")) == settings.google_sheet_gid
            ),
            sheets[0]["properties"],
        )
        current = target["gridProperties"]["columnCount"]
        if required_columns > current:
            service.spreadsheets().batchUpdate(
                spreadsheetId=settings.google_sheet_id,
                body={
                    "requests": [
                        {
                            "appendDimension": {
                                "sheetId": target["sheetId"],
                                "dimension": "COLUMNS",
                                "length": required_columns - current,
                            }
                        }
                    ]
                },
            ).execute()

    @staticmethod
    def append_chat_event(application: Application, event: dict[str, Any]) -> str | None:
        if not (settings.google_service_account_json or settings.google_service_account_file) or not settings.google_sheet_id:
            logging.info("Google Sheets export is disabled because credentials or sheet ID are empty")
            return None

        document_path = f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}"
        if event.get("sender") != "user":
            return document_path

        try:
            service = GoogleDocsService._build_service()
            sheet_title = GoogleDocsService._get_sheet_title(service)
            escaped_title = sheet_title.replace("'", "''")
            client_label = GoogleDocsService._client_label(application, event)
            result = service.spreadsheets().values().get(
                spreadsheetId=settings.google_sheet_id,
                range=f"'{escaped_title}'!A:ZZ",
            ).execute()
            rows = result.get("values", [])

            row_number = None
            for index, row in enumerate(rows[1:], start=2):
                if row and row[0].endswith(f"ID {application.telegram_user_id})"):
                    row_number = index
                    break
            if row_number is None:
                row_number = max(2, len(rows) + 1)
                current_row = [client_label]
            else:
                current_row = rows[row_number - 1]

            message_number = max(1, len(current_row))
            target_column = message_number + 1
            GoogleDocsService._ensure_column_capacity(service, target_column)
            column_letter = GoogleDocsService._column_letter(target_column)
            message_text = str(event.get("text", "")).replace("\r", " ").replace("\n", " ")
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=settings.google_sheet_id,
                body={
                    "valueInputOption": "RAW",
                    "data": [
                        {"range": f"'{escaped_title}'!A1", "values": [["Клиент"]]},
                        {
                            "range": f"'{escaped_title}'!{column_letter}1",
                            "values": [[f"Сообщение {message_number}"]],
                        },
                        {"range": f"'{escaped_title}'!A{row_number}", "values": [[client_label]]},
                        {"range": f"'{escaped_title}'!{column_letter}{row_number}", "values": [[message_text]]},
                    ],
                },
            ).execute()

            with SessionLocal() as session:
                db_app = session.get(Application, application.id)
                if db_app is not None:
                    db_app.document_path = document_path
                    session.commit()
            return document_path
        except Exception:
            logging.exception("Failed to append client message to Google Sheets")
            return None

    @staticmethod
    def create_application_document(application: Application) -> str | None:
        if not settings.google_sheet_id:
            return None
        return f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}"

    @staticmethod
    def sync_application_document(application: Application) -> str | None:
        return GoogleDocsService.create_application_document(application)

    @staticmethod
    def sync_presale_result(application: Application, result: dict[str, Any]) -> str | None:
        """Add structured presale fields to the existing client row without changing chat columns."""
        if not (settings.google_service_account_json or settings.google_service_account_file) or not settings.google_sheet_id:
            logging.info("Google presale export is disabled because credentials or sheet ID are empty")
            return None
        try:
            service = GoogleDocsService._build_service()
            sheet_title = GoogleDocsService._get_sheet_title(service)
            escaped_title = sheet_title.replace("'", "''")
            values = service.spreadsheets().values().get(
                spreadsheetId=settings.google_sheet_id, range=f"'{escaped_title}'!A:ZZ"
            ).execute().get("values", [])
            row_number = next(
                (
                    index for index, row in enumerate(values[1:], start=2)
                    if row and row[0].endswith(f"ID {application.telegram_user_id})")
                ),
                None,
            )
            if row_number is None:
                logging.warning("Google row not found for application %s", application.id)
                return None
            headers = values[0] if values else []
            fields = {
                "Lead ID": application.id,
                "Статус": result.get("status", application.status),
                "AI-анализ": result.get("analysis", ""),
                "Решение": result.get("solution", ""),
                "Выбранные услуги": result.get("services", ""),
                "Интеграции": result.get("integrations", ""),
                "Сложность": result.get("complexity", ""),
                "Срок": result.get("timeline", ""),
                "Стоимость": result.get("price", ""),
                "Расчётная стоимость": result.get("calculated_price", ""),
                "Итоговая стоимость": result.get("final_price", ""),
                "Уровень проекта": result.get("project_level", ""),
                "Требуется ручная проверка": result.get("manual_check_required", ""),
                "Причины ручной проверки": result.get("manual_check_reasons", ""),
                "Статус КП": result.get("proposal_status", ""),
                "Требует уточнения": result.get("clarifications", ""),
                "PDF": result.get("pdf", ""),
                "КП требует обновления": result.get("proposal_needs_update", False),
            }
            data = []
            for header, value in fields.items():
                if header in headers:
                    column_number = headers.index(header) + 1
                else:
                    headers.append(header)
                    column_number = len(headers)
                column = GoogleDocsService._column_letter(column_number)
                data.extend([
                    {"range": f"'{escaped_title}'!{column}1", "values": [[header]]},
                    {"range": f"'{escaped_title}'!{column}{row_number}", "values": [[str(value)]]},
                ])
            GoogleDocsService._ensure_column_capacity(service, len(headers))
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=settings.google_sheet_id,
                body={"valueInputOption": "RAW", "data": data},
            ).execute()
            logging.info("Presale result saved to Google Sheets for application %s", application.id)
            return f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}"
        except Exception:
            logging.exception("Failed to save presale result to Google Sheets for application %s", application.id)
            return None

    @staticmethod
    def mark_proposal_needs_update(application: Application) -> None:
        if not (settings.google_service_account_json or settings.google_service_account_file) or not settings.google_sheet_id:
            return
        try:
            service = GoogleDocsService._build_service()
            sheet_title = GoogleDocsService._get_sheet_title(service)
            escaped_title = sheet_title.replace("'", "''")
            values = service.spreadsheets().values().get(
                spreadsheetId=settings.google_sheet_id, range=f"'{escaped_title}'!A:ZZ"
            ).execute().get("values", [])
            if not values:
                return
            row_number = next((i for i, row in enumerate(values[1:], start=2) if row and row[0].endswith(f"ID {application.telegram_user_id})")), None)
            if row_number is None:
                return
            headers = values[0]
            header = "КП требует обновления"
            column_number = headers.index(header) + 1 if header in headers else len(headers) + 1
            column = GoogleDocsService._column_letter(column_number)
            GoogleDocsService._ensure_column_capacity(service, column_number)
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=settings.google_sheet_id,
                body={"valueInputOption": "RAW", "data": [
                    {"range": f"'{escaped_title}'!{column}1", "values": [[header]]},
                    {"range": f"'{escaped_title}'!{column}{row_number}", "values": [["TRUE"]]},
                ]},
            ).execute()
            logging.info("Proposal update flag saved to Google Sheets for application %s", application.id)
        except Exception:
            logging.exception("Failed to save proposal update flag for application %s", application.id)
