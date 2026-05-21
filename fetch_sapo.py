#!/usr/bin/env python3
"""
Fetch SAPO orders + returns for a given day, save JSON files compatible with build_report.py.

Reads credentials from env vars:
  SAPO_STORE_NAME       — e.g. "ajido" (the part before .mysapo.net)
  SAPO_ACCESS_TOKEN     — OAuth admin token (preferred)
  OR
  SAPO_API_KEY + SAPO_API_SECRET  — Private App credentials (HTTP Basic Auth)

Usage:
  python fetch_sapo.py --today 2026-05-21 --out-dir /tmp/sapo
"""
import os
import sys
import json
import argparse
import io
from datetime import datetime
import urllib.request
import urllib.parse
import base64

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def get_auth():
    store = os.environ.get("SAPO_STORE_NAME")
    if not store:
        print("[ERROR] SAPO_STORE_NAME env var required", file=sys.stderr)
        sys.exit(2)
    token = os.environ.get("SAPO_ACCESS_TOKEN")
    api_key = os.environ.get("SAPO_API_KEY")
    api_secret = os.environ.get("SAPO_API_SECRET")
    if token:
        return store, {"X-Sapo-Access-Token": token}
    if api_key and api_secret:
        creds = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        return store, {"Authorization": f"Basic {creds}"}
    print("[ERROR] Provide either SAPO_ACCESS_TOKEN or SAPO_API_KEY + SAPO_API_SECRET", file=sys.stderr)
    sys.exit(2)


def call_api(store: str, headers: dict, path: str, params: dict) -> dict:
    """GET https://<store>.mysapo.net/admin/<path> with query params.

    Note: SAPO's Cloudflare layer blocks the default Python User-Agent
    (returns 403). We send a browser-like UA to bypass that filter.
    """
    qs = urllib.parse.urlencode(params)
    url = f"https://{store}.mysapo.net/admin/{path}?{qs}"
    req = urllib.request.Request(url, headers={
        **headers,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (sapo-daily-report/1.0)",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_orders(store, headers, created_on_min, created_on_max, status=None, limit=100):
    """Paginate through orders, return combined list."""
    all_orders = []
    page = 1
    while True:
        params = {
            "created_on_min": created_on_min,
            "created_on_max": created_on_max,
            "limit": limit,
            "page": page,
        }
        if status:
            params["status"] = status
        data = call_api(store, headers, "orders.json", params)
        orders = data.get("orders", [])
        all_orders.extend(orders)
        print(f"  fetched orders page {page}: {len(orders)} (status={status or 'active'})")
        if len(orders) < limit:
            break
        page += 1
        if page > 50:
            print("[WARN] >50 pages, stopping pagination", file=sys.stderr)
            break
    return all_orders


def fetch_returns(store, headers, created_on_min, created_on_max, limit=100):
    """Paginate through order returns."""
    all_returns = []
    page = 1
    while True:
        params = {
            "created_on_min": created_on_min,
            "created_on_max": created_on_max,
            "limit": limit,
            "page": page,
        }
        data = call_api(store, headers, "order_returns.json", params)
        returns = data.get("order_returns", [])
        all_returns.extend(returns)
        print(f"  fetched returns page {page}: {len(returns)}")
        if len(returns) < limit:
            break
        page += 1
        if page > 20:
            break
    return all_returns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", required=True, help="YYYY-MM-DD (Asia/Ho_Chi_Minh)")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    store, headers = get_auth()
    print(f"[INFO] Store: {store}.mysapo.net")
    print(f"[INFO] Day: {args.today}")

    created_on_min = f"{args.today}T00:00:00+07:00"
    created_on_max = f"{args.today}T23:59:59+07:00"

    os.makedirs(args.out_dir, exist_ok=True)

    print("[INFO] Fetching active orders...")
    active_orders = fetch_orders(store, headers, created_on_min, created_on_max)
    active_path = os.path.join(args.out_dir, "orders_active.json")
    with open(active_path, "w", encoding="utf-8") as f:
        json.dump({"orders": active_orders}, f, ensure_ascii=False, default=str)

    print("[INFO] Fetching cancelled orders...")
    cancelled_orders = fetch_orders(store, headers, created_on_min, created_on_max, status="cancelled")
    cancelled_path = os.path.join(args.out_dir, "orders_cancelled.json")
    with open(cancelled_path, "w", encoding="utf-8") as f:
        json.dump({"orders": cancelled_orders}, f, ensure_ascii=False, default=str)

    print("[INFO] Fetching returns...")
    returns = fetch_returns(store, headers, created_on_min, created_on_max)
    returns_path = os.path.join(args.out_dir, "order_returns.json")
    with open(returns_path, "w", encoding="utf-8") as f:
        json.dump({"order_returns": returns}, f, ensure_ascii=False, default=str)

    print(f"\n[OK] Wrote 3 files to {args.out_dir}")
    print(f"     Active:    {len(active_orders)} orders → {active_path}")
    print(f"     Cancelled: {len(cancelled_orders)} orders → {cancelled_path}")
    print(f"     Returns:   {len(returns)} returns → {returns_path}")


if __name__ == "__main__":
    main()
