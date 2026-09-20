"""
discord_report.py
-----------------
Funkcja wysyłająca codzienny raport WIG20 na kanał Discord przez Webhook.

UŻYCIE:
  1. Wklej ten plik do swojego projektu (w głównym folderze App GPW).
  2. Ustaw secret DISCORD_WEBHOOK_PL w GitHub Actions
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

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_PL")


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

def _build_opportunities_embed(stocks: list, arbitrage: list = None) -> dict:
    opportunities = []
    watch_list = []
    
    for s in stocks:
        name = s.get("name", s.get("ticker", "?"))
        price = s.get("price", 0) or 0
        pe = s.get("pe", 0) or 0
        pbv = s.get("pbv", 0) or 0
        roe = s.get("roe", 0) or 0
        div_yield = s.get("div_yield", 0) or 0
        rec = str(s.get("recommendation", "")).lower()
        quality = _calc_quality(s)
        
        reasons = []
        if 0 < pe < 10:
            reasons.append(f"C/Z={pe:.1f} (bardzo tanio)")
        if 0 < pbv < 1.2:
            reasons.append(f"C/WK={pbv:.2f} (poniżej wartości księgowej)")
        if roe and roe > 0.18:
            reasons.append(f"ROE={roe:.1%} (wysoka rentowność)")
        if div_yield and div_yield > 0.07:
            reasons.append(f"Dywidenda={div_yield:.1%} (wysoka stopa)")
        if rec in ("buy", "strong_buy"):
            reasons.append(f"Rekomendacja: {rec.upper()}")
        if quality >= 75:
            reasons.append(f"Jakość={quality}/100")
            
        if len(reasons) >= 3:
            opportunities.append((name, price, reasons, quality))
        elif len(reasons) >= 2:
            watch_list.append((name, price, reasons, quality))
    
    opportunities.sort(key=lambda x: x[3], reverse=True)
    watch_list.sort(key=lambda x: x[3], reverse=True)
    
    lines = []
    date_str = datetime.now().strftime("%d.%m.%Y")
    
    if opportunities:
        lines.append("🟢 **OKAZJE – rozważ zakup:**")
        for name, price, reasons, quality in opportunities[:5]:
            lines.append(f"**{name}** @ {price:.2f} zł")
            for r in reasons:
                lines.append(f"  • {r}")
            lines.append("")
    else:
        lines.append("🟢 **OKAZJE:** Brak wyraźnych sygnałów dziś.")
        lines.append("")
    
    if watch_list:
        lines.append("🟡 **OBSERWUJ:**")
        for name, price, reasons, quality in watch_list[:5]:
            reasons_str = " | ".join(reasons)
            lines.append(f"**{name}** @ {price:.2f} zł — {reasons_str}")
        lines.append("")
    
    if arbitrage:
        arb_alerts = [
            a for a in arbitrage
            if a.get("signal") in ("WATCH_HIGH", "WATCH_LOW",
                                    "TRADE_SMALL", "FULL_ENTRY")
        ]
        if arb_alerts:
            lines.append("📊 **ARBITRAŻ – pary do obserwacji:**")
            for a in arb_alerts:
                pair = a.get("pair", "?")
                zscore = a.get("zscore", 0)
                signal = a.get("signal", "?")
                entry_score = a.get("entry_score", 0)
                emoji = "🔴" if "TRADE" in signal else "🟡"
                lines.append(
                    f"{emoji} **{pair}** Z={zscore:+.2f} | "
                    f"{signal} | Score={entry_score}/100"
                )
    
    return {
        "embeds": [{
            "title": f"🎯 Okazje WIG20 — {date_str}",
            "description": "\n".join(lines) if lines else "Brak sygnałów.",
            "color": 0x2ecc71,
            "footer": {"text": "GPW Analyst v2.0 • Analiza fundamentalna + arbitraż"}
        }]
    }


def send_daily_report(stocks: list | None = None, image_path: str | None = None) -> bool:
    webhook_url = WEBHOOK_URL
    if not webhook_url:
        print("Blad: Zmienna srodowiskowa DISCORD_WEBHOOK_PL nie jest ustawiona.")
        return False

    # ── Inicjalizacja bazy danych ────────────────────────────────
    from database import init_db
    init_db()
    # ────────────────────────────────────────────────────────────

    if stocks is None:
        print("Pobieram dane WIG20...")
        from data_fetcher import get_all_stocks
        stocks = get_all_stocks()

    if not stocks:
        print("Brak danych do wyslania.")
        return False
    
    # ── NOWE: pobierz arbitraż ──────────────────────────────────
    try:
        from data_fetcher import get_all_arbitrage
        arbitrage = get_all_arbitrage()
    except Exception:
        arbitrage = []
    # ────────────────────────────────────────────────────────────

    if image_path:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        filename = os.path.basename(image_path)
    else:
        print("Generuje tabele wskaznikow (z prognozami AI)...")
        image_bytes = _build_table_image(stocks)
        filename = f"wig20_{datetime.now().strftime('%Y%m%d')}.png"

    payload = _build_embed(stocks)
    
    # ── NOWE: wyślij embed z okazjami ───────────────────────────
    opps_payload = _build_opportunities_embed(stocks, arbitrage)
    try:
        requests.post(webhook_url, json=opps_payload, timeout=30)
        print("Embed z okazjami wysłany.")
    except Exception as e:
        print(f"Błąd wysyłania okazji: {e}")
    # ────────────────────────────────────────────────────────────
        # ── GROQ: komentarz AI ──────────────────────────────────────
    print("Pytam Groq o komentarz...")
    insight = _get_claude_insight(stocks, arbitrage)
    insight_payload = {
        "embeds": [{
            "title": f"🤖 Komentarz AI — {datetime.now().strftime('%d.%m.%Y')}",
            "description": insight,
            "color": 0x9b59b6,
            "footer": {"text": "Groq • Llama 3.1 • GPW Analyst v2.0"}
        }]
    }
    try:
        requests.post(webhook_url, json=insight_payload, timeout=30)
        print("Komentarz AI wysłany.")
    except Exception as e:
        print(f"Błąd wysyłania komentarza AI: {e}")
    # ────────────────────────────────────────────────────────────

    print(f"Wysylam raport na Discord ({len(stocks)} spolek)...")
    try:
        response = requests.post(
            webhook_url,
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

def _get_claude_insight(stocks: list, arbitrage: list) -> str:
    """Pyta Groq (darmowe AI) o komentarz do dzisiejszej sytuacji."""
    try:
        from groq import Groq
        
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        portfolio = {
            "PKO.WA": {"ilosc": 74, "cena_zakupu": 95.50},
            "PEO.WA": {"ilosc": 87, "cena_zakupu": 228.00},
            "ALR.WA": {"ilosc": 55, "cena_zakupu": 133.00},
            "KRU.WA": {"ilosc": 20, "cena_zakupu": 394.50},
            "KTY.WA": {"ilosc": 10, "cena_zakupu": 1263.30},
            "KGH.WA": {"ilosc": 21, "cena_zakupu": 335.60},
            "PZU.WA": {"ilosc": 100, "cena_zakupu": 228.00},
        }
        
        top_stocks = sorted(
            stocks, key=lambda x: _calc_quality(x), reverse=True
        )[:8]
        
        arb_alerts = [
            a for a in arbitrage
            if a.get("signal") not in ("NEUTRAL",)
        ]
        
        portfel_status = []
        for ticker, info in portfolio.items():
            stock = next(
                (s for s in stocks if s.get("ticker") == ticker), None
            )
            if stock:
                kurs = stock.get("price", 0)
                zakup = info["cena_zakupu"]
                zmiana = ((kurs - zakup) / zakup * 100) if zakup else 0
                portfel_status.append({
                    "ticker": ticker,
                    "nazwa": stock.get("name", ticker),
                    "kurs": round(kurs, 2),
                    "cena_zakupu": zakup,
                    "zmiana_pct": round(zmiana, 2),
                    "ilosc": info["ilosc"]
                })

        prompt = f"""Jesteś ekspertem inwestycyjnym GPW. Dzisiaj jest {datetime.now().strftime('%d.%m.%Y')}.

PORTFEL INWESTORA:
{json.dumps(portfel_status, ensure_ascii=False, indent=2)}

TOP SPÓŁKI WIG20:
{json.dumps([{{
    'nazwa': s.get('name'),
    'kurs': s.get('price'),
    'cz': round(s.get('pe') or 0, 1),
    'roe': f"{{(s.get('roe') or 0):.1%}}",
    'rekomendacja': s.get('recommendation'),
    'jakosc': _calc_quality(s)
}} for s in top_stocks], ensure_ascii=False, indent=2)}

SYGNAŁY ARBITRAŻU:
{json.dumps([{{
    'para': a.get('pair'),
    'zscore': round(a.get('zscore') or 0, 2),
    'sygnał': a.get('signal'),
    'score': a.get('entry_score')
}} for a in arb_alerts], ensure_ascii=False, indent=2)}

Napisz KONKRETNY komentarz (max 5 zdań):
1. Co jest najciekawsze w portfelu dziś?
2. Czy jest sygnał arbitrażu do działania?
3. Jedna konkretna sugestia przed otwarciem sesji.
Podawaj liczby. Bez ogólników."""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3
        )
        
        return response.choices[0].message.content
        
        except Exception as e:
        import traceback
        print(f"Błąd Groq API: {e}")
        print(traceback.format_exc())
        return "Analiza AI niedostępna dziś."
if __name__ == "__main__":
    success = send_daily_report()
    exit(0 if success else 1)