"""
sheets_uploader.py — Upload crawler results to Google Sheets.
- Creates 3 tabs: "Web", "InApp", "CTV"
- Each row has a "Run Date" column
- Rows older than 7 days are automatically deleted at start of each run
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Tab names in Google Sheets
TAB_WEB   = "Web (ads.txt)"
TAB_INAPP = "InApp (app-ads.txt)"
TAB_CTV   = "CTV"

# First column is always Run Date; rest follow
WEB_HEADERS   = ["Run Date", "Domain", "Network Found", "Network Details"]
INAPP_HEADERS = ["Run Date", "Domain", "Network Found", "Network Details"]
CTV_HEADERS   = ["Run Date", "Domain", "IPD Found", "Network Found", "Network Details"]


def _get_client(service_account_json: str) -> gspread.Client:
    """Authenticate with Google Sheets using a service account JSON string."""
    info = json.loads(service_account_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_tab(spreadsheet, tab_name: str, headers: List[str]) -> gspread.Worksheet:
    """Return existing tab or create it with the given headers."""
    try:
        ws = spreadsheet.worksheet(tab_name)
        # If tab exists but has no header row, add one
        if ws.row_count == 0 or ws.cell(1, 1).value != headers[0]:
            ws.clear()
            ws.append_row(headers, value_input_option="RAW")
        return ws
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=5000, cols=len(headers) + 20)
        ws.append_row(headers, value_input_option="RAW")
        # Format header row: bold + freeze
        ws.format("1:1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
        })
        ws.freeze(rows=1)
        return ws


def _delete_old_rows(ws: gspread.Worksheet, cutoff_date: datetime) -> int:
    """Delete all data rows where 'Run Date' is older than cutoff_date."""
    all_values = ws.get_all_values()
    if len(all_values) <= 1:
        return 0  # Only header or empty

    cutoff_str = cutoff_date.strftime("%Y-%m-%d")
    rows_to_delete = []

    for idx, row in enumerate(all_values[1:], start=2):   # start=2 because row 1 is header
        run_date = row[0].strip() if row else ""
        if run_date and run_date < cutoff_str:             # lexicographic compare works for YYYY-MM-DD
            rows_to_delete.append(idx)

    if not rows_to_delete:
        return 0

    # Delete in reverse order to preserve row indices
    deleted = 0
    for row_idx in reversed(rows_to_delete):
        ws.delete_rows(row_idx)
        deleted += 1

    print(f"    Deleted {deleted} rows older than {cutoff_str}")
    return deleted


def _rows_to_values(rows: List[Dict], base_headers: List[str],
                    run_date_str: str, line_keys: List[str]) -> List[List]:
    """Convert list-of-dicts to list-of-lists for gspread upload."""
    all_values = []
    for row in rows:
        vals = [run_date_str]
        # Fixed columns
        for col in base_headers[1:]:     # skip "Run Date"
            vals.append(str(row.get(col, "")))
        # Dynamic line-check columns
        for key in line_keys:
            vals.append(str(row.get(key, "")))
        all_values.append(vals)
    return all_values


def upload_results(
    service_account_json: str,
    spreadsheet_id: str,
    web_rows: Optional[List[Dict]],
    inapp_rows: Optional[List[Dict]],
    ctv_rows: Optional[List[Dict]],
    web_line_keys: List[str] = None,
    inapp_line_keys: List[str] = None,
    ctv_line_keys: List[str] = None,
) -> None:
    """
    Upload all crawler results to Google Sheets.
    Deletes rows older than 7 days before uploading new data.
    """
    client        = _get_client(service_account_json)
    spreadsheet   = client.open_by_key(spreadsheet_id)
    today_str     = datetime.utcnow().strftime("%Y-%m-%d")
    cutoff        = datetime.utcnow() - timedelta(days=7)

    web_line_keys   = web_line_keys   or []
    inapp_line_keys = inapp_line_keys or []
    ctv_line_keys   = ctv_line_keys   or []

    # ── Web tab ────────────────────────────────────────────────────────────────
    if web_rows is not None:
        print(f"\n  [Sheets] Updating '{TAB_WEB}'...")
        full_web_headers = WEB_HEADERS + web_line_keys
        ws_web = _get_or_create_tab(spreadsheet, TAB_WEB, full_web_headers)

        # Ensure new line columns exist in header
        _ensure_columns(ws_web, full_web_headers)

        # Delete rows older than 7 days
        _delete_old_rows(ws_web, cutoff)

        # Append new rows
        if web_rows:
            values = _rows_to_values(web_rows, WEB_HEADERS, today_str, web_line_keys)
            ws_web.append_rows(values, value_input_option="RAW")
            print(f"    Appended {len(values)} rows to '{TAB_WEB}'")
        else:
            print(f"    No web results to upload.")

    # ── InApp tab ──────────────────────────────────────────────────────────────
    if inapp_rows is not None:
        print(f"\n  [Sheets] Updating '{TAB_INAPP}'...")
        full_inapp_headers = INAPP_HEADERS + inapp_line_keys
        ws_inapp = _get_or_create_tab(spreadsheet, TAB_INAPP, full_inapp_headers)
        _ensure_columns(ws_inapp, full_inapp_headers)
        _delete_old_rows(ws_inapp, cutoff)

        if inapp_rows:
            values = _rows_to_values(inapp_rows, INAPP_HEADERS, today_str, inapp_line_keys)
            ws_inapp.append_rows(values, value_input_option="RAW")
            print(f"    Appended {len(values)} rows to '{TAB_INAPP}'")
        else:
            print(f"    No in-app results to upload.")

    # ── CTV tab ────────────────────────────────────────────────────────────────
    if ctv_rows is not None:
        print(f"\n  [Sheets] Updating '{TAB_CTV}'...")
        full_ctv_headers = CTV_HEADERS + ctv_line_keys
        ws_ctv = _get_or_create_tab(spreadsheet, TAB_CTV, full_ctv_headers)
        _ensure_columns(ws_ctv, full_ctv_headers)
        _delete_old_rows(ws_ctv, cutoff)

        if ctv_rows:
            values = _rows_to_values(ctv_rows, CTV_HEADERS, today_str, ctv_line_keys)
            ws_ctv.append_rows(values, value_input_option="RAW")
            print(f"    Appended {len(values)} rows to '{TAB_CTV}'")
        else:
            print(f"    No CTV results to upload.")

    print(f"\n  [Sheets] Done. View your sheet:")
    print(f"  https://docs.google.com/spreadsheets/d/{spreadsheet_id}")


def _ensure_columns(ws: gspread.Worksheet, expected_headers: List[str]) -> None:
    """Add any missing columns to the header row."""
    current_headers = ws.row_values(1)
    missing = [h for h in expected_headers if h not in current_headers]
    if missing:
        next_col = len(current_headers) + 1
        for i, h in enumerate(missing):
            ws.update_cell(1, next_col + i, h)
        print(f"    Added {len(missing)} new column(s) to header")