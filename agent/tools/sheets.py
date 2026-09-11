from __future__ import annotations

import csv
import os
import uuid
from pathlib import Path

from googleapiclient.discovery import build

from agent.schemas import LogToSheetInput, LogToSheetOutput, ToolError
from integrations import google_auth

# Local CSV — the free/offline default. Real Google Sheets (below) is used
# automatically once GOOGLE_SHEETS_SPREADSHEET_ID + Gmail OAuth are both
# configured, same auto-detect spirit as api/pipeline.py's build_llm().
LOCAL_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sheet_log.csv"

_FIELDNAMES = ["row_id", "timestamp", "email_id", "sender", "category", "urgency", "action_taken", "approver"]

_SHEET_RANGE = "Sheet1!A:H"


def _row_dict(input: LogToSheetInput, row_id: str) -> dict:
    """Single source of truth for column order/values — shared by both destinations."""
    return {
        "row_id": row_id,
        "timestamp": input.timestamp.isoformat(),
        "email_id": input.email_id,
        "sender": input.sender,
        "category": input.category,
        "urgency": input.urgency,
        "action_taken": input.action_taken,
        "approver": input.approver or "",
    }


def _sheets_configured() -> bool:
    return bool(os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")) and google_auth.is_configured()


def log_to_sheet(input: LogToSheetInput) -> LogToSheetOutput | ToolError:
    """Appends one row per handled email — to a real Google Sheet if
    configured, otherwise the local CSV (see LOCAL_LOG_PATH)."""
    if _sheets_configured():
        try:
            return _log_to_google_sheets(input)
        except Exception as e:
            return ToolError(tool="log_to_sheet", error_type="external_api_error", message=str(e))
    return _log_to_local_csv(input)


def _log_to_local_csv(input: LogToSheetInput) -> LogToSheetOutput | ToolError:
    try:
        LOCAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_exists = LOCAL_LOG_PATH.exists()
        row = _row_dict(input, row_id=str(uuid.uuid4())[:8])

        with open(LOCAL_LOG_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        return LogToSheetOutput(success=True, sheet_row_id=row["row_id"], destination="local_csv")
    except OSError as e:
        return ToolError(tool="log_to_sheet", error_type="external_api_error", message=str(e))


def _log_to_google_sheets(input: LogToSheetInput) -> LogToSheetOutput:
    creds = google_auth.get_credentials()
    service = build("sheets", "v4", credentials=creds)
    row = _row_dict(input, row_id=str(uuid.uuid4())[:8])

    service.spreadsheets().values().append(
        spreadsheetId=os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"],
        range=_SHEET_RANGE,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [[row[k] for k in _FIELDNAMES]]},
    ).execute()

    return LogToSheetOutput(success=True, sheet_row_id=row["row_id"], destination="google_sheets")
