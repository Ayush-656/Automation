import os
from datetime import datetime

from crawler import (
run_web_crawler,
run_inapp_crawler,
run_ctv_crawler,
)

from sheets_uploader import (
load_config_from_sheet,
upload_daily_results,
)

def main():

config_sheet_id = os.environ["CONFIG_SHEET_ID"]
results_sheet_id = os.environ["RESULTS_SHEET_ID"]
service_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]

print("Loading config from Google Sheets...")
cfg = load_config_from_sheet(
    service_json,
    config_sheet_id
)

print("Running ADS...")
ads_rows = run_web_crawler(cfg)

print("Running APPADS...")
app_rows = run_inapp_crawler(cfg)

print("Running CTV...")
ctv_rows = run_ctv_crawler(cfg)

upload_daily_results(
    service_json,
    results_sheet_id,
    ads_rows,
    app_rows,
    ctv_rows
)

print("Done.")
```

if **name** == "**main**":
main()
