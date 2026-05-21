#!/usr/bin/env python3
"""
SAPO Daily Revenue Report — Aggregator + HTML Builder

Input: orders.json (from sapo_list_orders, can be multiple pages combined),
       returns.json (from sapo_list_order_returns),
       cancelled.json (from sapo_list_orders with status=cancelled, optional)

Output: HTML report file + JSON summary

Usage:
  python build_report.py \
    --orders orders.json [orders2.json ...] \
    --returns returns.json \
    --cancelled cancelled.json \
    --today 2026-05-21 \
    --slot "morning" \
    --out-dir reports/
"""
import sys, os, json, argparse, io
from collections import defaultdict
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def load_orders_file(path: str) -> list:
    """Load a SAPO list_orders JSON file → list of order dicts."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("orders", [])


def load_returns_file(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("order_returns", [])


def aggregate(active_orders: list, returns: list, cancelled_orders: list) -> dict:
    by_src = defaultdict(lambda: {
        "open": 0, "closed": 0,
        "gross_active": 0.0,
        "refunded_in_active": 0.0,
        "discount": 0.0,
    })
    canc_by_src = defaultdict(lambda: {"count": 0, "amount": 0.0})
    ret_by_src = defaultdict(lambda: {"count": 0, "amount": 0.0, "refunded_count": 0})

    for o in active_orders:
        src = (o.get("source_name") or "unknown").lower()
        status = (o.get("status") or "unknown").lower()
        ctp = float(o.get("current_total_price") or 0)
        tref = float(o.get("total_refunded") or 0)
        disc = float(o.get("total_discounts") or 0)
        b = by_src[src]
        if status in ("open", "closed"):
            b[status] += 1
        b["gross_active"] += ctp
        b["refunded_in_active"] += tref
        b["discount"] += disc

    for o in cancelled_orders:
        src = (o.get("source_name") or "unknown").lower()
        amt = float(o.get("total_price") or 0)
        canc_by_src[src]["count"] += 1
        canc_by_src[src]["amount"] += amt

    for r in returns:
        src = (r.get("order_source") or "unknown").lower()
        amt = float(r.get("total_price") or 0)
        rf = (r.get("refund_status") or "").lower()
        ret_by_src[src]["count"] += 1
        ret_by_src[src]["amount"] += amt
        if rf in ("refund", "refunded"):
            ret_by_src[src]["refunded_count"] += 1

    # Totals
    T = {
        "open": sum(b["open"] for b in by_src.values()),
        "closed": sum(b["closed"] for b in by_src.values()),
        "gross_active": sum(b["gross_active"] for b in by_src.values()),
        "refunded_in_active": sum(b["refunded_in_active"] for b in by_src.values()),
        "discount": sum(b["discount"] for b in by_src.values()),
        "cancelled_count": sum(v["count"] for v in canc_by_src.values()),
        "cancelled_amount": sum(v["amount"] for v in canc_by_src.values()),
        "returns_count": sum(v["count"] for v in ret_by_src.values()),
        "returns_amount": sum(v["amount"] for v in ret_by_src.values()),
    }
    T["net_strict"] = T["gross_active"] - T["refunded_in_active"]
    T["net_dashboard"] = T["gross_active"] - T["returns_amount"]
    if (T["open"] + T["closed"]) > 0:
        T["aov"] = T["gross_active"] / (T["open"] + T["closed"])
    else:
        T["aov"] = 0

    return {
        "by_source": dict(by_src),
        "cancelled_by_source": dict(canc_by_src),
        "returns_by_source": dict(ret_by_src),
        "totals": T,
    }


def vnd(x: float) -> str:
    return f"{x:,.0f} đ"


def channel_label(src: str) -> str:
    if "tiktok" in src:
        return "TikTok Shop"
    if "shopee" in src:
        return "Shopee"
    return src.title()


def channel_emoji(src: str) -> str:
    if "tiktok" in src:
        return "&#x1F3B5;"  # 🎵 musical note (TikTok)
    if "shopee" in src:
        return "&#x1F7E0;"  # 🟠
    return "&#x1F4E6;"  # 📦


def render_html(summary: dict, today: str, slot: str) -> str:
    T = summary["totals"]
    now_str = datetime.now().strftime("%H:%M %d/%m/%Y")
    slot_label = {
        "morning": "Snapshot sáng",
        "afternoon": "Snapshot chiều",
        "eod": "Chốt cuối ngày",
    }.get(slot, slot)

    # Sort channels: tiktok first, shopee second
    def sortkey(k):
        if "tiktok" in k: return 0
        if "shopee" in k: return 1
        return 2

    rows_by_src = []
    for src in sorted(summary["by_source"].keys(), key=sortkey):
        b = summary["by_source"][src]
        active = b["open"] + b["closed"]
        net = b["gross_active"] - b["refunded_in_active"]
        rows_by_src.append(f"""
          <tr>
            <td>{channel_emoji(src)} <b>{channel_label(src)}</b></td>
            <td style="text-align:right">{active} (open {b['open']}, closed {b['closed']})</td>
            <td style="text-align:right">{vnd(b['gross_active'])}</td>
            <td style="text-align:right; color:#c00">-{vnd(b['refunded_in_active'])}</td>
            <td style="text-align:right; font-weight:bold">{vnd(net)}</td>
          </tr>""")

    cancelled_rows = []
    for src, v in sorted(summary["cancelled_by_source"].items(), key=lambda x: sortkey(x[0])):
        cancelled_rows.append(f"""
          <tr>
            <td>{channel_emoji(src)} {channel_label(src)}</td>
            <td style="text-align:right">{v['count']}</td>
            <td style="text-align:right">{vnd(v['amount'])}</td>
          </tr>""")

    returns_rows = []
    for src, v in sorted(summary["returns_by_source"].items(), key=lambda x: sortkey(x[0])):
        returns_rows.append(f"""
          <tr>
            <td>{channel_emoji(src)} {channel_label(src)}</td>
            <td style="text-align:right">{v['count']} ({v['refunded_count']} đã refund)</td>
            <td style="text-align:right">{vnd(v['amount'])}</td>
          </tr>""")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 720px; margin: 0 auto; color: #222; }}
h1 {{ color: #0a5; border-bottom: 2px solid #0a5; padding-bottom: 6px; }}
h2 {{ color: #555; margin-top: 28px; font-size: 16px; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0 20px; font-size: 14px; }}
th, td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
th {{ background: #f4f4f4; text-align: left; font-weight: 600; }}
.kpi {{ background: #f0fdf4; padding: 14px 20px; border-left: 4px solid #0a5; margin: 16px 0; border-radius: 4px; }}
.kpi .label {{ color: #666; font-size: 13px; }}
.kpi .value {{ font-size: 26px; font-weight: bold; color: #0a5; }}
.muted {{ color: #888; font-size: 12px; }}
.warn {{ background: #fff7ed; border-left: 4px solid #f59e0b; padding: 10px 14px; margin: 14px 0; border-radius: 4px; font-size: 13px; }}
</style></head><body>

<h1>\U0001F4CA Báo cáo Doanh thu &mdash; {today}</h1>
<p class="muted">{slot_label} &middot; Cập nhật {now_str}</p>

<div class="kpi">
  <div class="label">Doanh thu thuần &mdash; <b>Cách A</b> (Strict: chỉ đơn trong ngày, đã trừ refund processed)</div>
  <div class="value">{vnd(T['net_strict'])}</div>
</div>

<div class="kpi" style="background:#eff6ff;border-left-color:#3b82f6">
  <div class="label" style="color:#1e40af">Doanh thu thuần &mdash; <b>Cách B</b> (Dashboard logic: trừ returns ghi nhận hôm nay, kể cả đơn cũ)</div>
  <div class="value" style="color:#1e40af">{vnd(T['net_dashboard'])}</div>
</div>

<h2>Theo kênh</h2>
<table>
  <thead><tr>
    <th>Kênh</th>
    <th style="text-align:right">Đơn active</th>
    <th style="text-align:right">Doanh thu gross</th>
    <th style="text-align:right">Refund</th>
    <th style="text-align:right">Net</th>
  </tr></thead>
  <tbody>{''.join(rows_by_src)}
    <tr style="background:#fafafa;font-weight:bold">
      <td>TỔNG</td>
      <td style="text-align:right">{T['open']+T['closed']}</td>
      <td style="text-align:right">{vnd(T['gross_active'])}</td>
      <td style="text-align:right;color:#c00">-{vnd(T['refunded_in_active'])}</td>
      <td style="text-align:right">{vnd(T['net_strict'])}</td>
    </tr>
  </tbody>
</table>

<p><b>AOV:</b> {vnd(T['aov'])} &middot; <b>Discount cấp:</b> {vnd(T['discount'])}</p>

<h2>\U0001F6AB Đơn hủy hôm nay (đã loại khỏi doanh thu)</h2>
<table>
  <thead><tr><th>Kênh</th><th style="text-align:right">Đơn hủy</th><th style="text-align:right">Giá trị bị mất</th></tr></thead>
  <tbody>{''.join(cancelled_rows) or '<tr><td colspan="3" class="muted">Không có đơn hủy</td></tr>'}
    <tr style="background:#fafafa;font-weight:bold">
      <td>TỔNG</td><td style="text-align:right">{T['cancelled_count']}</td>
      <td style="text-align:right">{vnd(T['cancelled_amount'])}</td>
    </tr>
  </tbody>
</table>

<h2>↩️ Returns ghi nhận hôm nay</h2>
<table>
  <thead><tr><th>Kênh</th><th style="text-align:right">Returns</th><th style="text-align:right">Giá trị</th></tr></thead>
  <tbody>{''.join(returns_rows) or '<tr><td colspan="3" class="muted">Không có return</td></tr>'}
    <tr style="background:#fafafa;font-weight:bold">
      <td>TỔNG</td><td style="text-align:right">{T['returns_count']}</td>
      <td style="text-align:right">{vnd(T['returns_amount'])}</td>
    </tr>
  </tbody>
</table>

<div class="warn">
ℹ️ <b>Ghi chú:</b> Returns ghi nhận hôm nay có thể thuộc đơn cũ (khách nhận hàng trước đó mới yêu cầu trả). Thông tin "refund_status: unrefund" nghĩa là tiền CHƯA được hoàn thực sự.<br>
<b>Cách A</b> = doanh thu thực của đơn tạo hôm nay sau khi trừ refund đã xử lý.<br>
<b>Cách B</b> = khớp SAPO Dashboard, trừ toàn bộ returns ghi nhận hôm nay.
</div>

<p class="muted">Generated by SAPO Daily Report automation &middot; Source: SAPO MCP</p>

</body></html>"""
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", nargs="+", required=True, help="One or more sapo_list_orders JSON page files")
    ap.add_argument("--returns", required=True)
    ap.add_argument("--cancelled", required=False, help="sapo_list_orders JSON with status=cancelled")
    ap.add_argument("--today", required=True, help="YYYY-MM-DD")
    ap.add_argument("--slot", required=True, choices=["morning", "afternoon", "eod"])
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args()

    active = []
    for p in args.orders:
        active.extend(load_orders_file(p))
    returns = load_returns_file(args.returns)
    cancelled = load_orders_file(args.cancelled) if args.cancelled and os.path.exists(args.cancelled) else []

    summary = aggregate(active, returns, cancelled)
    html = render_html(summary, args.today, args.slot)

    os.makedirs(args.out_dir, exist_ok=True)
    base = f"{args.today}_{args.slot}"
    html_path = os.path.join(args.out_dir, f"{base}.html")
    json_path = os.path.join(args.out_dir, f"{base}.json")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    T = summary["totals"]
    print(f"[OK] Report written: {html_path}")
    print(f"     Net A (strict):    {vnd(T['net_strict'])}")
    print(f"     Net B (dashboard): {vnd(T['net_dashboard'])}")
    print(f"     Active orders:     {T['open'] + T['closed']}")
    print(f"     Cancelled:         {T['cancelled_count']} ({vnd(T['cancelled_amount'])})")
    print(f"     Returns today:     {T['returns_count']} ({vnd(T['returns_amount'])})")
    print(html_path)


if __name__ == "__main__":
    main()
