"""
discord_report.py
-----------------
Funkcja wysyłająca codzienny raport WIG20 na kanał Discord przez Webhook.

UŻYCIE:
  1. Wklej ten plik do swojego projektu (w głównym folderze App GPW).
  2. Uzupełnij DISCORD_WEBHOOK_URL w pliku .env
  3. Wywołaj send_daily_report() po zamknięciu sesji giełdowej.

WYMAGANIA:
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

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "TWOJ_WEBHOOK_URL_TUTAJ")


def _fmt(val, fmt=".2f", suffix="", zero_dash=True):
    if val is None or (zero_dash and val == 0):
        return "–"
    try:
        return f"{val:{fmt}}{suffix}"
    except Exception:
        return "–"


def _fmt_cap(val):
    if not val or val == 0:
        return "–"
    return f"{val / 1e9:.2f}B"


def _calc_debt_ebitda(s):
    debt = s.get("total_debt", 0) or 0
    ebitda = s.get("ebitda", 0) or 0
    if ebitda and ebitda != 0:
        return f"{debt / ebitda:.2f}x"
    return "–"


def _calc_quality(s):
    score = 0
    pe = s.get("pe", 0) or 0
    pbv = s.get("pbv", 0) or 0
    roe = s.get("roe", 0) or 0
    div_yield = s.get("div_yield", 0) or 0
    beta = s.get("beta", 0) or 0

    if 0 < pe < 15:       score += 25
    if 0 < pbv < 2:       score += 25
    if roe > 0.15:        score += 25
    if div_yield > 0.04:  score += 25
    if 0 < beta < 1.0:    score = min(100, score + 5)

    return score


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
    return "–"


def _build_table_image(stocks: list) -> bytes:
    headers = [
        "Spółka", "Kurs", "Kapit.", "C/Z", "C/WK",
        "ROE%", "Marza Op.", "Dlug/EBITDA", "Prognoza AI", "Jakosc", "Rekomen."
    ]

    REC_LABEL = {
        "buy":         ("KUP",       "#2ecc71"),
        "strong_buy":  ("MOC. KUP",  "#27ae60"),
        "hold":        ("TRZYMAJ",   "#f39c12"),
        "sell":        ("SPRZED.",   "#e74c3c"),
        "strong_sell": ("SPRZED.!",  "#c0392b"),
        "none":        ("BRAK",      "#95a5a6"),
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
            _fmt(s.get("price"), ".2f", " zl"),
            _fmt_cap(s.get("market_cap")),
            _fmt(s.get("pe"), ".1f"),
            _fmt(s.get("pbv"), ".2f"),
            _fmt(s.get("roe"), ".1%") if s.get("roe") else "–",
            _fmt(s.get("operating_margin"), ".1%") if s.get("operating_margin") else "–",
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

    col_widths = [0.14, 0.09, 0.08, 0.06, 0.06, 0.07, 0.07, 0.10, 0.13, 0.08, 0.09]
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

    date_str = datetime.now().strftime("%d.%m.%Y")
    plt.title(f"Raport WIG20 — {date_str}", color="white", fontsize=14, fontweight="bold", pad=16)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=130)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _build_embed(stocks: list) -> dict:
    date_str = datetime.now().strftime("%d.%m.%Y")
    now_str  = datetime.now().strftime("%H:%M")

    low_pe      = min((s for s in stocks if (s.get("pe") or 0) > 0), key=lambda x: x["pe"], default=None)
    buy_list    = [s["name"] for s in stocks if str(s.get("recommendation", "")).lower() in ("buy", "strong_buy")]
    top_quality = max(stocks, key=lambda x: _calc_quality(x))

    lines = [f"**Data sesji:** {date_str}  •  **Wygenerowano:** {now_str}"]
    if low_pe:
        lines.append(f"Najnizsze C/Z: **{low_pe['name']}** ({low_pe['pe']:.1f})")
    lines.append(f"Najlepsza jakosc: **{top_quality['name']}** ({_calc_quality(top_quality)}/100)")
    if buy_list:
        lines.append(f"Rekomendacja KUP: **{', '.join(buy_list)}**")
    else:
        lines.append("Brak aktualnych rekomendacji KUP w WIG20.")
    lines.append("\n*Szczegolowa tabela wskaznikow w załączniku ponizej*")

    return {
        "embeds": [{
            "title": f"Raport WIG20 — {date_str}",
            "description": "\n".join(lines),
            "color": 0x2c3e7a,
            "footer": {"text": "GPW Analyst v2.0  •  Dane: yfinance"}
        }]
    }


def send_daily_report(stocks: list = None, image_path: str = None) -> bool:
    if WEBHOOK_URL == "TWOJ_WEBHOOK_URL_TUTAJ":
        print("Blad: Nie ustawiono DISCORD_WEBHOOK_URL w pliku .env")
        return False

    if stocks is None:
        print("Pobieram dane WIG20...")
        from data_fetcher import get_all_stocks
        stocks = get_all_stocks()

    if not stocks:
        print("Brak danych do wyslania.")
        return False

    if image_path:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        filename = os.path.basename(image_path)
    else:
        print("Generuje tabele wskaznikow (z prognozami AI)...")
        image_bytes = _build_table_image(stocks)
        filename = f"wig20_{datetime.now().strftime('%Y%m%d')}.png"

    payload = _build_embed(stocks)

    print(f"Wysylam raport na Discord ({len(stocks)} spolek)...")
    try:
        response = requests.post(
            WEBHOOK_URL,
            data={"payload_json": json.dumps(payload)},
            files={"file": (filename, image_bytes, "image/png")},
            timeout=30,
        )
        if response.status_code in (200, 204):
            print(f"Raport wyslany! ({response.status_code})")
            return True
        else:
            print(f"Discord zwrocil blad: {response.status_code} — {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Blad polaczenia: {e}")
        return False


if __name__ == "__main__":
    success = send_daily_report()
    exit(0 if success else 1)