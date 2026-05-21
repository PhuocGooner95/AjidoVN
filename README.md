# SAPO Daily Revenue Report

3 lần/ngày, tự động gửi báo cáo doanh thu TikTok Shop + Shopee qua email.

**2 chế độ chạy** trong cùng codebase:
- **Local** (Claude Code scheduled-tasks plugin) — cần máy bật + app mở
- **GitHub Actions** (cloud, 24/7) — chạy free trên server GitHub, không cần máy bật ⭐ Recommended

## Cấu trúc

```
daily-report/
├── .github/workflows/sapo-daily-report.yml   ← GitHub Actions cron
├── fetch_sapo.py        ← Gọi SAPO REST API trực tiếp (cho GHA)
├── build_report.py      ← Aggregator + HTML generator
├── send_email.py        ← SMTP sender via Gmail
├── orchestrator.py      ← Glue: fetch → build → send (entry cho GHA)
├── config.example.json  ← Template config (local mode)
├── config.json          ← GITIGNORED — chứa App Password (local mode)
├── reports/             ← Output HTML, lưu mỗi lần chạy
└── requirements.txt     ← Chỉ stdlib, không deps ngoài
```

## Logic doanh thu

Mỗi báo cáo show **2 số** để cross-check:

- **Net A — Strict**: chỉ đơn tạo trong ngày, đã trừ refund processed.
  Phản ánh đúng performance trong ngày.
- **Net B — Dashboard logic**: trừ luôn returns ghi nhận trong ngày (kể cả đơn cũ).
  Khớp số trên SAPO Dashboard.

Đơn cancelled tự động bị loại khỏi doanh thu. Returns được hiển thị riêng kèm trạng thái `refund_status`.

---

## ☁️ Setup GitHub Actions (Recommended)

### Bước 1 — Lấy SAPO API credentials

Vào SAPO Admin → **Cài đặt** → **Tài khoản & Quyền** → **Phát triển ứng dụng** (hoặc **Apps** → **Private apps**).

Tạo private app mới hoặc chọn app có sẵn, lấy **1 trong 2 cách**:

**Cách A — Access Token (đơn giản hơn, recommended):**
- Copy `access_token` (chuỗi dài ~40 ký tự)

**Cách B — API Key + Secret:**
- Copy cả `api_key` và `api_secret`

Quyền cần thiết: **read_orders**, **read_returns** (chỉ đọc, không cần write).

### Bước 2 — Tạo GitHub repo

```bash
cd "D:\06_AI_Dev\Claude Code\tiktok-ads-mcp\daily-report"
git init
git add .
git commit -m "Initial: SAPO daily report automation"

# Tạo private repo trên github.com, copy URL
git remote add origin https://github.com/<your-user>/sapo-daily-report.git
git branch -M main
git push -u origin main
```

⚠️ **Phải là PRIVATE repo** — code có chứa email user.

### Bước 3 — Thêm secrets

Vào repo trên GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

Thêm 6-7 secrets (tên + value):

| Secret name | Value |
|---|---|
| `SAPO_STORE_NAME` | `ajido` (phần trước `.mysapo.net`) |
| `SAPO_ACCESS_TOKEN` | Access token từ bước 1 (nếu dùng cách A) |
| `SAPO_API_KEY` | API key (nếu dùng cách B — bỏ qua nếu đã có access_token) |
| `SAPO_API_SECRET` | API secret (nếu dùng cách B) |
| `GMAIL_USER` | `ajido.vn@gmail.com` |
| `GMAIL_APP_PASSWORD` | 16 ký tự App Password (đã có) |
| `EMAIL_TO` | `ajido.vn@gmail.com` (hoặc nhiều, ngăn cách bằng dấu phẩy) |
| `EMAIL_CC` | (optional) ngăn cách bằng dấu phẩy |

### Bước 4 — Test workflow

Vào tab **Actions** → workflow "SAPO Daily Revenue Report" → click **Run workflow** → chọn `slot=eod` → **Run workflow**.

Đợi 1-2 phút, xem log. Nếu thành công → email gửi đến `EMAIL_TO`.

### Bước 5 — Sau khi test ngon

Workflow tự động chạy 3 lần/ngày theo cron. Không cần làm gì thêm.

**Tắt local routines:**
- Mở Claude Code → sidebar **Scheduled** → toggle off 3 task `sapo-daily-report-*` (để tránh gửi 2 email)

---

## 💻 Setup Local Mode (Claude Code scheduled-tasks)

(Đã setup xong trong session trước — chỉ document để tham khảo.)

3 tasks được tạo qua MCP `scheduled-tasks` plugin:
- `sapo-daily-report-morning` @ `3 10 * * *`
- `sapo-daily-report-afternoon` @ `3 17 * * *`
- `sapo-daily-report-eod` @ `59 23 * * *`

Mỗi task khi chạy:
1. Claude (trong fresh session) gọi `mcp__sapo__sapo_list_orders` + `sapo_list_order_returns`
2. Run `build_report.py` → tạo HTML
3. Run `send_email.py` → gửi email qua Gmail SMTP

**Limitation:** Cần máy bật + Claude Code app mở khi task fire.

---

## 🧪 Test local (CLI)

Test fetch_sapo.py với credentials ENV:

```powershell
$env:SAPO_STORE_NAME = "ajido"
$env:SAPO_ACCESS_TOKEN = "your_token_here"
python fetch_sapo.py --today 2026-05-21 --out-dir /tmp/sapo-test
```

Test full pipeline:

```powershell
$env:SAPO_STORE_NAME = "ajido"
$env:SAPO_ACCESS_TOKEN = "..."
$env:GMAIL_USER = "ajido.vn@gmail.com"
$env:GMAIL_APP_PASSWORD = "..."
$env:EMAIL_TO = "ajido.vn@gmail.com"
$env:SLOT = "eod"
python orchestrator.py
```

---

## 🔧 Troubleshooting

**SAPO 401 Unauthorized**: Token sai hoặc app không có scope `read_orders`/`read_returns`. Quay lại admin tạo lại.

**Gmail 535 Authentication Failed**: App Password không đúng hoặc 2FA chưa bật. Vào `https://myaccount.google.com/apppasswords` tạo lại.

**Workflow run nhưng email không đến**: Check spam folder. Check `EMAIL_TO` secret có đúng không. Xem log step "Run orchestrator" tìm exception.

**Cron không trigger**: GitHub đôi khi delay 5-10 phút với scheduled workflow. Nếu repo không có commit nào trong 60 ngày, GitHub tự disable scheduled workflows — push 1 commit dummy để bật lại.

---

## 📅 Cron timing reference

| Local time (VN, UTC+7) | UTC cron | Slot |
|---|---|---|
| 10:03 | `3 3 * * *` | morning |
| 17:03 | `3 10 * * *` | afternoon |
| 23:59 | `59 16 * * *` | eod |

GitHub Actions có jitter ~5-15 phút trên schedule.
