#!/usr/bin/env python3
"""
SAPO Daily Revenue Report — Email Sender
Usage:
  python send_email.py --subject "..." --html-file report.html [--text-file report.txt]
Reads config from config.json next to this script.
"""
import sys, os, json, argparse, smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[ERROR] Config not found: {CONFIG_PATH}", file=sys.stderr)
        print("Create config.json with: smtp_user, smtp_password (Gmail App Password), to (list), cc (list, optional)", file=sys.stderr)
        sys.exit(2)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for k in ("smtp_user", "smtp_password", "to"):
        if not cfg.get(k):
            print(f"[ERROR] Missing config key: {k}", file=sys.stderr)
            sys.exit(2)
    return cfg

def send(subject: str, html_body: str, text_body: str | None = None, cfg=None):
    cfg = cfg or load_config()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["smtp_user"]
    msg["To"] = ", ".join(cfg["to"])
    if cfg.get("cc"):
        msg["Cc"] = ", ".join(cfg["cc"])

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    recipients = list(cfg["to"]) + list(cfg.get("cc") or [])

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(cfg["smtp_user"], cfg["smtp_password"])
        server.sendmail(cfg["smtp_user"], recipients, msg.as_string())
    print(f"[OK] Sent to {recipients} at {datetime.now().isoformat()}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--html-file", required=True)
    ap.add_argument("--text-file", required=False)
    args = ap.parse_args()

    with open(args.html_file, "r", encoding="utf-8") as f:
        html = f.read()
    text = None
    if args.text_file and os.path.exists(args.text_file):
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read()
    send(args.subject, html, text)

if __name__ == "__main__":
    main()
