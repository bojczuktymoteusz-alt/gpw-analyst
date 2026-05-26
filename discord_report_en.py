"""
discord_report_en.py
--------------------
Sends daily WIG20 report in English to Discord via Webhook.

USAGE:
  1. Place this file in your project root (next to discord_report.py).
  2. Make sure DISCORD_WEBHOOK_URL_EN is set in your .env file.
  3. Call send_daily_report_en() after market close, or run directly.

REQUIREMENTS:
  pip install requests matplotlib pandas python-dotenv
"""

import os
import sys
import io
import json
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL_EN", "YOUR_WEBHOOK_URL_HERE")


def _fmt(val, fmt=".2f", suffix="", zero_dash=True):
    if val is None or (zero_dash and val == 0):
        return "-"
    try:
        return f"{val:{fmt}}{suffix}"
    except Exception:
        return "-"


def _fmt_cap(val):
    if not val or val == 0:
        return "-"
    return f"{val / 1e9:.2f}B"


def _calc_debt_ebitda(s):
    debt = s.get("total_debt", 0) or 0
    ebitda = s.get("ebitda", 0) or 0
    if ebitda and ebitda != 0:
        return f"{debt / ebitda:.2f}x"
    return "-"


def _calc_quality(s):
    score = 0
    max_score = 0

    pe = s.get("pe", 0) or 0
    max_score += 20
    if 0 < pe <= 10:   score += 20
    elif pe <= 15:     score += 15
    elif pe <= 20:     score += 10
    elif pe <= 30:     score += 5

    pbv = s.get("pbv", 0) or 0
    max_score += 25
    if 0 < pbv < 15:   score += 25

    roe = s.get("roe", 0) or 0
    max_score += 25
    if roe > 0.15:     score += 25

    div_yield = s.get("div_yield", 0) or 0
    max_score += 25
    if div_yield > 0.04: score += 25

    beta = s.get("beta", 0) or 0
    if 0 < beta < 1.0:
        score = min(100, score + 5)

    return int((score / max_score) * 100) if max_score else 0


def _quality_color(score):
    if score >= 70: return "#2ecc71"
    if score >= 40: return "#f39c12"
    return "#e74c3c"


def _predict_arrow(s):
    try:
        from data_fetcher import predict_stock_price
        pred = predict_stock_price(s["ticker"], forecast_days=7)
        if pred:
            pct = pred.get("trend_pct", 0)
            arrow = "▲" if pct > 0.5 else ("▼" if pct < -0.5 else "►")
            return f"{arrow} {pred['predicted_price']:.2f} ({pct:+.1f}%)"
    except Exception:
        pass
    return "-"


def _build_table_image(stocks: list) -> bytes:
    headers = [
        "Company", "Price", "Mkt Cap", "P/E", "P/BV",
        "ROE%", "Op. Margin", "Debt/EBITDA", "AI Forecast", "Quality", "Signal"
    ]

    REC_LABEL = {
        "buy":         ("BUY",        "#2ecc71"),
        "strong_buy":  ("STRONG BUY", "#27ae60"),
        "hold":        ("HOLD",       "#f39c12"),
        "sell":        ("SELL",       "#e74c3c"),
        "strong_sell": ("STRONG SELL","#c0392b"),
        "none":        ("N/A",        "#95a5a6"),
    }

    rows = []
    rec_colors = []
    quality_scores = []

    for s in sorted(stocks, key=lambda x: x.get("name", "")):
        rec_key = str(s.get("recommendation", "none")).lower().replace(" ", "_")
        rec_label, rec_color = REC_LABEL.get(rec_key, ("?", "#95a5a6"))
        quality = _calc_quality(s)

        rows.append([
            s.get("name", s.get("ticker", "?")),
            _fmt(s.get("price"), ".2f", " PLN"),
            _fmt_cap(s.get("market_cap")),
            _fmt(s.get("pe"), ".1f"),
            _fmt(s.get("pbv"), ".2f"),
            _fmt(s.get("roe"), ".1%") if s.get("roe") else "-",
            _fmt(s.get("operating_margin"), ".1%") if s.get("operating_margin") else "-",
            _calc_debt_ebitda(s),
            _predict_arrow(s),
            f"{quality}/100",
            rec_label,
        ])
        rec_colors.append(rec_color)
        quality_scores.append(quality)

    n_rows = len(rows)
    fig_height = max(5, 0.48 * n_rows + 2.8)
    fig, ax = plt.subplots(figsize=(20, fig_height))
    ax.axis("off")
    fig.patch.set_facecolor("#1e2130")

    table = ax.table(cellText=rows, colLabels=headers, cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.65)

    col_widths = [0.14, 0.09, 0.08, 0.06, 0.06, 0.07, 0.08, 0.10, 0.13, 0.08, 0.10]
    for col_idx, width in enumerate(col_widths):
        for row_idx in range(n_rows + 1):
            table[row_idx, col_idx].set_width(width)

    for col_idx in range(len(headers)):
        cell = table[0, col_idx]
        cell.set_facecolor("#2c3e7a")
        cell.set_text_props(color="white", fontweight="bold")
        cell.set_edgecolor("#3a4a9a")

    for row_idx, (rec_color, quality) in enumerate(zip(rec_colors, quality_scores), start=1):
        bg = "#252a40" if row_idx % 2 == 0 else "#1e2130"
        for col_idx in range(len(headers)):
            cell = table[row_idx, col_idx]
            cell.set_edgecolor("#2c3050")
            if col_idx == len(headers) - 1:
                cell.set_facecolor(rec_color)
                cell.set_text_props(color="white", fontweight="bold")
            elif col_idx == len(headers) - 2:
                cell.set_facecolor(_quality_color(quality))
                cell.set_text_props(color="white", fontweight="bold")
            elif col_idx == len(headers) - 3:
                text = rows[row_idx - 1][col_idx]
                color = "#2ecc71" if "▲" in text else ("#e74c3c" if "▼" in text else "#f39c12")
                cell.set_facecolor(bg)
                cell.set_text_props(color=color, fontweight="bold")
            else:
                cell.set_facecolor(bg)
                cell.set_text_props(color="#dde3f0")

    date_str = datetime.now().strftime("%d %b %Y")
    plt.title(f"WIG20 Premium AI Report — {date_str}", color="white",
              fontsize=14, fontweight="bold", pad=16)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), dpi=130)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _build_embed(stocks: list) -> dict:
    date_str = datetime.now().strftime("%d %b %Y")
    now_str  = datetime.now().strftime("%H:%M")

    low_pe      = min((s for s in stocks if (s.get("pe") or 0) > 0), key=lambda x: x["pe"], default=None)
    buy_list    = [s["name"] for s in stocks if str(s.get("recommendation", "")).lower() in ("buy", "strong_buy")]
    top_quality = max(stocks, key=lambda x: _calc_quality(x))

    lines = [f"**Session date:** {date_str}  •  **Generated:** {now_str} CET"]
    if low_pe:
        lines.append(f"Lowest P/E: **{low_pe['name']}** ({low_pe['pe']:.1f})")
    lines.append(f"Top quality stock: **{top_quality['name']}** ({_calc_quality(top_quality)}/100)")
    if buy_list:
        lines.append(f"BUY signals: **{', '.join(buy_list)}**")
    else:
        lines.append("No active BUY signals in WIG20 today.")
    lines.append("\n*Full indicator table attached below*")

    return {
        "embeds": [{
            "title": f"WIG20 Premium AI Report — {date_str}",
            "description": "\n".join(lines),
            "color": 0x2c3e7a,
            "footer": {"text": "GPW Analyst v2.0  •  Warsaw Stock Exchange  •  Data: yfinance"}
        }]
    }


def send_daily_report_en(stocks: list = None, image_path: str = None) -> bool:
    """
    Sends the English WIG20 report to Discord.

    Parameters
    ----------
    stocks     : list from get_all_stocks(). If None, fetches automatically.
    image_path : optional path to a custom PNG/JPG screenshot.
    """
    if WEBHOOK_URL == "YOUR_WEBHOOK_URL_HERE":
        print("Error: DISCORD_WEBHOOK_URL_EN not set in .env file.")
        return False

    if stocks is None:
        print("Fetching WIG20 data...")
        from data_fetcher import get_all_stocks
        stocks = get_all_stocks()

    if not stocks:
        print("No data to send.")
        return False

    if image_path:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        filename = os.path.basename(image_path)
    else:
        print("Generating report table (with AI forecasts)...")
        image_bytes = _build_table_image(stocks)
        filename = f"wig20_report_{datetime.now().strftime('%Y%m%d')}.png"

    payload = _build_embed(stocks)

    print(f"Sending report to Discord ({len(stocks)} stocks)...")
    try:
        response = requests.post(
            WEBHOOK_URL,
            data={"payload_json": json.dumps(payload)},
            files={"file": (filename, image_bytes, "image/png")},
            timeout=30,
        )
        if response.status_code in (200, 204):
            print(f"Report sent successfully! ({response.status_code})")
            return True
        else:
            print(f"Discord error: {response.status_code} — {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        return False


if __name__ == "__main__":
    success = send_daily_report_en()
    exit(0 if success else 1)
