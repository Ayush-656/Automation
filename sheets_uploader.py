import json
import re

from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
"https://www.googleapis.com/auth/spreadsheets",
"https://www.googleapis.com/auth/drive",
]

def get_client(service_json):

```
info = json.loads(service_json)

creds = Credentials.from_service_account_info(
    info,
    scopes=SCOPES
)

return gspread.authorize(creds)
```

def load_config_from_sheet(
service_json,
spreadsheet_id
):

```
gc = get_client(service_json)

sh = gc.open_by_key(spreadsheet_id)

cfg = {
    "web": {},
    "inapp": {},
    "ctv": {},
    "settings": {
        "timeout": 10,
        "workers": 10,
        "match_fields": 2
    }
}

mapping = {
    "Config_ADS": "web",
    "Config_APPADS": "inapp",
    "Config_CTV": "ctv"
}

for tab_name, key in mapping.items():

    ws = sh.worksheet(tab_name)

    rows = ws.get_all_values()

    domains = []
    seller_ids = []
    lines = []

    section = None

    network = ""
    relation = ""

    ipd = ""

    for row in rows:

        value = row[0].strip() if row else ""

        if value == "[DOMAINS]":
            section = "domains"
            continue

        if value == "[SELLER_IDS]":
            section = "seller_ids"
            continue

        if value == "[LINES]":
            section = "lines"
            continue

        if row and len(row) > 1:

            k = row[0].strip().lower()
            v = row[1].strip()

            if k == "network":
                network = v

            elif k == "relation":
                relation = v

            elif k == "ipd":
                ipd = v

        else:

            if section == "domains":
                domains.append(value)

            elif section == "seller_ids":
                seller_ids.append(value)

            elif section == "lines":
                lines.append(value)

    cfg[key] = {
        "enabled": True,
        "domains": domains,
        "seller_ids": seller_ids,
        "lines": lines,
        "network": network,
        "relation": relation,
        "ipd": ipd
    }

return cfg
```

def create_or_replace_tab(
spreadsheet,
title,
rows
):

```
try:
    old = spreadsheet.worksheet(title)
    spreadsheet.del_worksheet(old)
except:
    pass

cols = max(
    len(rows[0]) if rows else 10,
    10
)

ws = spreadsheet.add_worksheet(
    title=title,
    rows=max(len(rows) + 50, 100),
    cols=cols
)

if rows:
    ws.update(rows)

return ws
```

def cleanup_old_tabs(
spreadsheet,
keep_days=5
):

```
cutoff = datetime.utcnow() - timedelta(days=keep_days)

patterns = [
    r"ADS_(\d{4}_\d{2}_\d{2})",
    r"APPADS_(\d{4}_\d{2}_\d{2})",
    r"CTV_(\d{4}_\d{2}_\d{2})"
]

for ws in spreadsheet.worksheets():

    title = ws.title

    for pattern in patterns:

        m = re.match(pattern, title)

        if not m:
            continue

        dt = datetime.strptime(
            m.group(1),
            "%Y_%m_%d"
        )

        if dt < cutoff:

            spreadsheet.del_worksheet(ws)

            print(
                f"Deleted old worksheet: {title}"
            )

            break
```

def dicts_to_rows(data):

```
if not data:
    return [["No Data"]]

headers = list(data[0].keys())

rows = [headers]

for row in data:

    rows.append(
        [row.get(h, "") for h in headers]
    )

return rows
```

def upload_daily_results(
service_json,
spreadsheet_id,
ads_rows,
app_rows,
ctv_rows
):

```
gc = get_client(service_json)

sh = gc.open_by_key(spreadsheet_id)

cleanup_old_tabs(
    sh,
    keep_days=5
)

today = datetime.utcnow().strftime(
    "%Y_%m_%d"
)

create_or_replace_tab(
    sh,
    f"ADS_{today}",
    dicts_to_rows(ads_rows)
)

create_or_replace_tab(
    sh,
    f"APPADS_{today}",
    dicts_to_rows(app_rows)
)

create_or_replace_tab(
    sh,
    f"CTV_{today}",
    dicts_to_rows(ctv_rows)
)
```
