#!/usr/bin/env python3
"""
SAPO Daily Report Orchestrator — fetch + build + send in one go.

Designed for GitHub Actions (or any cron). Reads all config from env vars.

Required env vars:
  SAPO_STORE_NAME, SAPO_ACCESS_TOKEN (or SAPO_API_KEY + SAPO_API_SECRET)
  GMAIL_USER, GMAIL_APP_PASSWORD
  EMAIL_TO              — comma-separated list of recipients
  EMAIL_CC              — optional, comma-separated
  SLOT                  — "morning" | "afternoon" | "eod"
  TODAY                 — optional override YYYY-MM-DD; default = today in UTC+7
"""
import os
import sys
import subprocess
import io
import tempfile
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def get_today_vn() -> str:
    override = os.environ.get("TODAY")
    if override:
        return override
    tz = timezone(timedelta(hours=7))
    return datetime.now(tz).strftime("%Y-%m-%d")


def run(cmd: list, env: dict = None):
    print(f"[RUN] {' '.join(cmd)}")
    r = subprocess.run(cmd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.returncode != 0:
        sys.exit(r.returncode)
    return r


def write_email_config():
    """Write config.json that send_email.py expects, from env vars."""
    cfg = {
        "smtp_user": os.environ["GMAIL_USER"],
        "smtp_password": os.environ["GMAIL_APP_PASSWORD"],
        "to": [x.strip() for x in os.environ["EMAIL_TO"].split(",") if x.strip()],
        "cc": [x.strip() for x in os.environ.get("EMAIL_CC", "").split(",") if x.strip()],
    }
    import json
    path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return path


def main():
    slot = os.environ.get("SLOT", "eod")
    if slot not in ("morning", "afternoon", "eod"):
        print(f"[ERROR] Invalid SLOT: {slot}", file=sys.stderr)
        sys.exit(2)
    today = get_today_vn()
    print(f"[ORCH] Slot={slot} Today={today}")

    repo_root = os.path.dirname(os.path.abspath(__file__))

    # 1. Fetch SAPO data into a temp dir
    with tempfile.TemporaryDirectory(prefix="sapo-") as tmp:
        run([sys.executable, os.path.join(repo_root, "fetch_sapo.py"),
             "--today", today, "--out-dir", tmp])

        # 2. Build HTML report
        out_dir = os.path.join(repo_root, "reports")
        run([sys.executable, os.path.join(repo_root, "build_report.py"),
             "--orders", os.path.join(tmp, "orders_active.json"),
             "--returns", os.path.join(tmp, "order_returns.json"),
             "--cancelled", os.path.join(tmp, "orders_cancelled.json"),
             "--today", today, "--slot", slot, "--out-dir", out_dir])

    html_path = os.path.join(out_dir, f"{today}_{slot}.html")
    if not os.path.exists(html_path):
        print(f"[ERROR] Expected HTML not found: {html_path}", file=sys.stderr)
        sys.exit(3)

    # 3. Send email
    write_email_config()
    slot_label = {"morning": "Snapshot sáng (10h)",
                  "afternoon": "Snapshot chiều (17h)",
                  "eod": "CHỐT NGÀY (23:59)"}[slot]
    emoji = {"morning": "📊", "afternoon": "📈", "eod": "🌙"}[slot]
    subject = f"{emoji} Doanh thu SAPO {today} — {slot_label}"

    run([sys.executable, os.path.join(repo_root, "send_email.py"),
         "--subject", subject, "--html-file", html_path])

    print(f"\n[ORCH] ✓ Done. Report: {html_path}")


if __name__ == "__main__":
    main()
