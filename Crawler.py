"""
crawler.py — Headless Ads.txt / App-Ads.txt / CTV crawler
Extracted from Completed.py v7. No Streamlit dependency.
"""

import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional


# ── Domain / line helpers ──────────────────────────────────────────────────────

def normalize_domain(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^https?://", "", raw, flags=re.IGNORECASE)
    return raw.split("/")[0].split("?")[0].split("#")[0].lower().strip()


def parse_ads_line(raw: str) -> Optional[Dict]:
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    raw = raw.split("#")[0].strip()
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) < 3:
        return None
    return {
        "domain":    parts[0].lower(),
        "seller_id": parts[1],
        "relation":  parts[2].upper(),
        "tag":       parts[3].lower() if len(parts) > 3 else "",
    }


def lines_match(entry: Dict, query: Dict, match_fields: int = 2) -> bool:
    if entry["domain"] != query["domain"]:
        return False
    if match_fields >= 2 and entry["seller_id"].lower() != query["seller_id"].lower():
        return False
    if match_fields >= 3 and entry["relation"] != query["relation"]:
        return False
    if match_fields >= 4 and query["tag"] and entry["tag"].lower() != query["tag"]:
        return False
    return True


def _qkey(q: Dict) -> str:
    parts = [q["domain"], q["seller_id"], q["relation"]]
    if q["tag"]:
        parts.append(q["tag"])
    return ", ".join(parts)


def parse_domain_list(text: str) -> List[str]:
    seen, result = set(), []
    for line in text if isinstance(text, list) else text.splitlines():
        line = str(line).strip()
        if not line or line.startswith("#"):
            continue
        d = normalize_domain(line)
        if d and d not in seen:
            seen.add(d)
            result.append(d)
    return result


def parse_query_list(text_or_list) -> List[Dict]:
    result, seen = [], set()
    lines = text_or_list if isinstance(text_or_list, list) else text_or_list.splitlines()
    for line in lines:
        q = parse_ads_line(str(line))
        if q:
            key = _qkey(q)
            if key not in seen:
                seen.add(key)
                result.append(q)
    return result


def parse_seller_ids(text_or_list) -> List[str]:
    ids, seen = [], set()
    items = text_or_list if isinstance(text_or_list, list) else text_or_list.splitlines()
    for line in items:
        for part in str(line).split(","):
            sid = part.strip()
            if sid and not sid.startswith("#") and sid not in seen:
                seen.add(sid)
                ids.append(sid)
    return ids


# ── HTTP fetcher ───────────────────────────────────────────────────────────────

def fetch_file(domain: str, file_type: str, timeout: int) -> Dict:
    headers = {
        "User-Agent": "AdsTxtCrawler/7.0",
        "Accept":     "text/plain, text/*, */*",
    }
    last_error   = "Connection failed"
    max_attempts = 2

    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(0.8)

        for scheme in ("https", "http"):
            url = f"{scheme}://{domain}/{file_type}"
            try:
                r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)

                if r.status_code == 200:
                    ctype   = r.headers.get("Content-Type", "")
                    content = r.text.strip()
                    if not content:
                        last_error = "Empty file (200 OK but no content)"
                        continue
                    if "html" in ctype.lower() or re.match(r"<\s*(!doctype|html)", content[:40], re.I):
                        last_error = "HTML page returned (file probably missing)"
                        continue
                    return {"ok": True, "url": url, "text": r.text, "error": ""}

                elif r.status_code == 404:
                    return {"ok": False, "url": url, "text": "", "error": "File not found (404)"}
                elif r.status_code in (401, 403):
                    return {"ok": False, "url": url, "text": "", "error": f"Access denied (HTTP {r.status_code})"}
                elif r.status_code >= 500:
                    last_error = f"Server error (HTTP {r.status_code})"
                else:
                    last_error = f"Unexpected HTTP {r.status_code}"

            except requests.exceptions.Timeout:
                last_error = f"Request timed out ({timeout}s)"
                continue
            except requests.exceptions.SSLError:
                last_error = "SSL / certificate error"
            except requests.exceptions.ConnectionError as exc:
                msg = str(exc).lower()
                if any(k in msg for k in ("getaddrinfo", "name or service", "nodename", "nxdomain")):
                    return {"ok": False, "url": url, "text": "", "error": "DNS lookup failed"}
                elif "connection refused" in msg:
                    return {"ok": False, "url": url, "text": "", "error": "Connection refused"}
                else:
                    last_error = "Network connection error"
            except Exception as exc:
                last_error = f"Unexpected error: {str(exc)[:60]}"

    return {"ok": False, "url": f"https://{domain}/{file_type}", "text": "", "error": last_error}


# ── Crawl workers ──────────────────────────────────────────────────────────────

def crawl_combined(domain, network, relation, seller_ids, queries, match_fields, timeout, file_type):
    """Run the 'Combined' crawl: network check + line checks in one fetch."""
    fetch = fetch_file(domain, file_type, timeout)
    row: Dict = {"Domain": domain}
    if not fetch["ok"]:
        row["Network Found"]   = "Error"
        row["Network Details"] = fetch["error"]
        for q in queries:
            row[_qkey(q)] = "Error"
        return row

    entries     = [e for ln in fetch["text"].splitlines() if (e := parse_ads_line(ln)) is not None]
    net_entries = [e for e in entries if e["domain"] == network.lower()
                   and (not relation or e["relation"] == relation.upper())]

    if seller_ids:
        available = {e["seller_id"].lower() for e in net_entries}
        matched   = [sid for sid in seller_ids if sid.lower() in available]
        n         = len(seller_ids)
        row["Network Found"]   = "Yes" if matched else "No"
        row["Network Details"] = (
            f"Matched {len(matched)} of {n}: " + ", ".join(matched)
            if matched else f"0 of {n} matched"
        )
    else:
        ids = [e["seller_id"] for e in net_entries]
        if ids:
            unit = "entry" if len(ids) == 1 else "entries"
            row["Network Found"]   = "Yes"
            row["Network Details"] = f"{len(ids)} {unit}: " + ", ".join(ids)
        else:
            row["Network Found"]   = "No"
            row["Network Details"] = "No matching entries"

    for q in queries:
        match = next((e for e in entries if lines_match(e, q, match_fields)), None)
        row[_qkey(q)] = "Yes" if match else "No"
    return row


def check_inventory_partner_domain(text: str, target_domain: str) -> str:
    if not target_domain.strip():
        return "N/A"
    target = target_domain.lower().strip()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.lower().startswith("inventorypartnerdomain="):
            val = line.split("=", 1)[1].strip().lower()
            if val == target:
                return "Yes"
    return "No"


def crawl_ctv_combined(domain, ipd_target, network, relation,
                        queries, match_fields, timeout):
    """CTV-specific combined crawl on app-ads.txt."""
    file_type = "app-ads.txt"
    fetch     = fetch_file(domain, file_type, timeout)
    row: Dict = {"Domain": domain}

    if not fetch["ok"]:
        row["IPD Found"]       = "Error"
        row["Network Found"]   = "Error"
        row["Network Details"] = fetch["error"]
        for q in queries:
            row[_qkey(q)] = "Error"
        return row

    text = fetch["text"]
    row["IPD Found"] = check_inventory_partner_domain(text, ipd_target)

    entries     = [e for ln in text.splitlines() if (e := parse_ads_line(ln)) is not None]
    net_entries = [e for e in entries if e["domain"] == network.lower()
                   and (not relation or e["relation"] == relation.upper())]

    ids = [e["seller_id"] for e in net_entries]
    if ids:
        unit = "entry" if len(ids) == 1 else "entries"
        row["Network Found"]   = "Yes"
        row["Network Details"] = f"{len(ids)} {unit}: " + ", ".join(ids)
    else:
        row["Network Found"]   = "No"
        row["Network Details"] = "No matching entries"

    for q in queries:
        match = next((e for e in entries if lines_match(e, q, match_fields)), None)
        row[_qkey(q)] = "Yes" if match else "No"

    return row


# ── Parallel runner ────────────────────────────────────────────────────────────

def run_parallel(domain_list: List[str], task_fn, workers: int = 10) -> List[Dict]:
    """Run task_fn(domain) in parallel for all domains. Returns list of result dicts."""
    all_results, done, total = [], 0, len(domain_list)
    print(f"  Starting {total} domains with {workers} workers...")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        fmap = {pool.submit(task_fn, d): d for d in domain_list}
        for fut in as_completed(fmap):
            dom = fmap[fut]
            try:
                res = fut.result()
                if isinstance(res, list):
                    all_results.extend(res)
                else:
                    all_results.append(res)
            except Exception as exc:
                all_results.append({
                    "Domain": dom, "Network Found": "Error",
                    "Network Details": f"Internal error: {str(exc)[:80]}",
                })
            done += 1
            if done % 10 == 0 or done == total:
                print(f"  Progress: {done}/{total} domains done")

    # Restore original domain order
    by_domain = {}
    for r in all_results:
        by_domain.setdefault(r.get("Domain", ""), r)

    ordered = []
    for d in domain_list:
        ordered.append(by_domain.get(d, {
            "Domain": d, "Network Found": "Error",
            "Network Details": "No result returned",
        }))
    return ordered


# ── High-level run functions ───────────────────────────────────────────────────

def run_web_crawler(cfg: Dict) -> List[Dict]:
    """Run Web (ads.txt) combined crawl from config."""
    web_cfg     = cfg.get("web", {})
    settings    = cfg.get("settings", {})
    domains     = parse_domain_list(web_cfg.get("domains", []))
    queries     = parse_query_list(web_cfg.get("lines", []))
    seller_ids  = parse_seller_ids(web_cfg.get("seller_ids", []))
    network     = normalize_domain(web_cfg.get("network", ""))
    relation    = web_cfg.get("relation", "Any")
    rel         = "" if relation == "Any" else relation.upper()
    timeout     = settings.get("timeout", 10)
    workers     = settings.get("workers", 10)
    match_fields= settings.get("match_fields", 2)

    if not domains:
        print("  [Web] No domains configured — skipping.")
        return []
    if not network:
        print("  [Web] No network configured — skipping.")
        return []

    print(f"  [Web] {len(domains)} domains | network={network} | {len(queries)} lines")
    return run_parallel(
        domains,
        lambda d: crawl_combined(d, network, rel, seller_ids, queries, match_fields, timeout, "ads.txt"),
        workers,
    )


def run_inapp_crawler(cfg: Dict) -> List[Dict]:
    """Run In-App (app-ads.txt) combined crawl from config."""
    app_cfg     = cfg.get("inapp", {})
    settings    = cfg.get("settings", {})
    domains     = parse_domain_list(app_cfg.get("domains", []))
    queries     = parse_query_list(app_cfg.get("lines", []))
    seller_ids  = parse_seller_ids(app_cfg.get("seller_ids", []))
    network     = normalize_domain(app_cfg.get("network", ""))
    relation    = app_cfg.get("relation", "Any")
    rel         = "" if relation == "Any" else relation.upper()
    timeout     = settings.get("timeout", 10)
    workers     = settings.get("workers", 10)
    match_fields= settings.get("match_fields", 2)

    if not domains:
        print("  [InApp] No domains configured — skipping.")
        return []
    if not network:
        print("  [InApp] No network configured — skipping.")
        return []

    print(f"  [InApp] {len(domains)} domains | network={network} | {len(queries)} lines")
    return run_parallel(
        domains,
        lambda d: crawl_combined(d, network, rel, seller_ids, queries, match_fields, timeout, "app-ads.txt"),
        workers,
    )


def run_ctv_crawler(cfg: Dict) -> List[Dict]:
    """Run CTV (app-ads.txt) combined crawl from config."""
    ctv_cfg     = cfg.get("ctv", {})
    settings    = cfg.get("settings", {})
    domains     = parse_domain_list(ctv_cfg.get("domains", []))
    queries     = parse_query_list(ctv_cfg.get("lines", []))
    network     = normalize_domain(ctv_cfg.get("network", ""))
    ipd         = ctv_cfg.get("ipd", "").strip()
    relation    = ctv_cfg.get("relation", "Any")
    rel         = "" if relation == "Any" else relation.upper()
    timeout     = settings.get("timeout", 10)
    workers     = settings.get("workers", 10)
    match_fields= settings.get("match_fields", 2)

    if not domains:
        print("  [CTV] No domains configured — skipping.")
        return []
    if not network:
        print("  [CTV] No network configured — skipping.")
        return []

    print(f"  [CTV] {len(domains)} domains | network={network} | IPD={ipd} | {len(queries)} lines")
    return run_parallel(
        domains,
        lambda d: crawl_ctv_combined(d, ipd, network, rel, queries, match_fields, timeout),
        workers,
    )