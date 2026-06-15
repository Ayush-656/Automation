"""
run_daily.py — Main script: loads config, runs all crawlers, uploads to Google Sheets.
Run this directly or let GitHub Actions call it on a schedule.

Usage:
    python run_daily.py

Required environment variables (set as GitHub Secrets):
    GOOGLE_SERVICE_ACCOUNT_JSON  — full JSON content of your service account key
    SPREADSHEET_ID               — the ID of your Google Sheet
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List

from crawler import (
    _qkey, parse_query_list,
    run_web_crawler, run_inapp_crawler, run_ctv_crawler,
)
from sheets_uploader import upload_results

CONFIG_FILE = "config.json"


def load_config() -> Dict:
    """Load config.json from the project root."""
    if not os.path.exists(CONFIG_FILE):
        print(f"ERROR: {CONFIG_FILE} not found. Copy config.example.json to config.json and fill it in.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_line_keys(rows: List[Dict], static_cols: List[str]) -> List[str]:
    """Extract dynamic line-check column names from result rows."""
    seen = set()
    keys = []
    for row in rows:
        for k in row:
            if k not in static_cols and k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def main():
    print("=" * 60)
    print(f"  Ads.txt Daily Crawler — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # ── Load config ────────────────────────────────────────────────────────────
    cfg = load_config()

    # ── Read secrets from environment ──────────────────────────────────────────
    sa_json        = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "").strip()

    if not sa_json:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set.")
        sys.exit(1)
    if not spreadsheet_id:
        print("ERROR: SPREADSHEET_ID environment variable not set.")
        sys.exit(1)

    # ── Run crawlers ───────────────────────────────────────────────────────────

    web_rows, inapp_rows, ctv_rows           = None, None, None
    web_line_keys, inapp_line_keys, ctv_line_keys = [], [], []

    # Web (ads.txt)
    if cfg.get("web", {}).get("enabled", False):
        print("\n[1/3] Running Web (ads.txt) crawler...")
        web_rows = run_web_crawler(cfg)
        web_line_keys = _extract_line_keys(
            web_rows, ["Domain", "Network Found", "Network Details"]
        )
        print(f"  → {len(web_rows)} result rows, {len(web_line_keys)} line column(s)")
    else:
        print("\n[1/3] Web crawler disabled in config — skipping.")

    # InApp (app-ads.txt)
    if cfg.get("inapp", {}).get("enabled", False):
        print("\n[2/3] Running InApp (app-ads.txt) crawler...")
        inapp_rows = run_inapp_crawler(cfg)
        inapp_line_keys = _extract_line_keys(
            inapp_rows, ["Domain", "Network Found", "Network Details"]
        )
        print(f"  → {len(inapp_rows)} result rows, {len(inapp_line_keys)} line column(s)")
    else:
        print("\n[2/3] InApp crawler disabled in config — skipping.")

    # CTV
    if cfg.get("ctv", {}).get("enabled", False):
        print("\n[3/3] Running CTV crawler...")
        ctv_rows = run_ctv_crawler(cfg)
        ctv_line_keys = _extract_line_keys(
            ctv_rows, ["Domain", "IPD Found", "Network Found", "Network Details"]
        )
        print(f"  → {len(ctv_rows)} result rows, {len(ctv_line_keys)} line column(s)")
    else:
        print("\n[3/3] CTV crawler disabled in config — skipping.")

    # ── Upload to Google Sheets ────────────────────────────────────────────────
    print("\n[Uploading to Google Sheets...]")
    upload_results(
        service_account_json = sa_json,
        spreadsheet_id       = spreadsheet_id,
        web_rows             = web_rows,
        inapp_rows           = inapp_rows,
        ctv_rows             = ctv_rows,
        web_line_keys        = web_line_keys,
        inapp_line_keys      = inapp_line_keys,
        ctv_line_keys        = ctv_line_keys,
    )

    print("\n" + "=" * 60)
    print("  All done!")
    print("=" * 60)


if __name__ == "__main__":
    main()