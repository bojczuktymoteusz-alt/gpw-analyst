import os
import json
from datetime import datetime
import requests

from backend.database import init_db

from backend.database import save_daily_snapshot
from backend.data_fetcher import get_all_stocks, get_all_arbitrage
from backend.analytics import log_signals, build_context



def _calc_quality(stock: dict) -> float:
    """Prosty scoring jakości spółki (placeholder – użyj swojego algorytmu)."""
    pe = stock.get("pe") or 0
    roe = stock.get("roe") or 0
    div = stock.get("div_yield") or 0

    score = 0
    if 0 < pe < 15:
        score += 30
    if roe > 0.15:
        score += 40
    if div > 0.04:
        score += 30
    return score

def _build_table_image(stocks: list) -> bytes:
    """
    Generuje PNG z tabelą WIG20 — wersja gotowa do produkcji.
    """
    from PIL import Image, ImageDraw, ImageFont
    import io

    # Ustawienia
    width = 1400
    row_height = 48
    header_height = 60
    padding = 20

    rows = len(stocks)
    height = header_height + rows * row_height + padding * 2

    # Tło
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Fonty
    try:
        font_bold = ImageFont.truetype("arialbd.ttf", 24)
        font = ImageFont.truetype("arial.ttf", 22)
    except:
        font_bold = ImageFont.load_default()
        font = ImageFont.load_default()

    # Nagłówek
    header = "WIG20 — Tabela wskaźników"
    draw.text((padding, padding), header, font=font_bold, fill=(0, 0, 0))

    # Kolumny
    columns = [
        ("Ticker", 120),
        ("Nazwa", 300),
        ("Cena", 120),
        ("C/Z", 120),
        ("C/WK", 120),
        ("ROE", 120),
        ("Rek.", 120),
        ("Jakość", 120),
    ]

    y = padding + header_height

    # Rysowanie nagłówków kolumn
    x = padding
    for col_name, col_width in columns:
        draw.text((x, y), col_name, font=font_bold, fill=(0, 0, 0))
        x += col_width
    y += row_height

    # Rysowanie wierszy
    for s in stocks:
        x = padding

        row_values = [
            s.get("ticker"),
            s.get("name"),
            f"{s.get('price', 0):.2f}",
            f"{s.get('pe') or 0:.1f}",
            f"{s.get('pbv') or 0:.2f}",
            f"{(s.get('roe') or 0) * 100:.1f}%",
            s.get("recommendation") or "N/A",
            f"{_calc_quality(s):.0f}/100",
        ]

        for value, (_, col_width) in zip(row_values, columns):
            draw.text((x, y), str(value), font=font, fill=(0, 0, 0))
            x += col_width

        y += row_height

    # Zapis do pamięci
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()



def _build_embed(stocks: list) -> dict:
    """
    Główny embed z raportem WIG20 (fundamenty + jakość).
    Zakładam, że masz już tę funkcję – tu jest uproszczona wersja.
    """
    rows = []
    for s in stocks:
        rows.append(
            f"**{s.get('ticker')}** — {s.get('name')} @ {s.get('price', 0):.2f} zł\n"
            f"C/Z={s.get('pe') or 0:.1f} | C/WK={s.get('pbv') or 0:.2f} | "
            f"ROE={(s.get('roe') or 0) * 100:.1f}% | Rekomendacja: {s.get('recommendation') or 'N/A'} | "
            f"Jakość={_calc_quality(s):.0f}/100"
        )

    description = "\n\n".join(rows)

    return {
        "embeds": [
            {
                "title": f"📊 Raport WIG20 — {datetime.now().strftime('%d.%m.%Y')}",
                "description": description,
                "color": 0x3498db,
                "footer": {"text": "GPW Analyst v2.0 • Analiza fundamentalna + arbitraż"},
            }
        ]
    }


def _build_opportunities_embed(stocks: list, arbitrage: list) -> dict:
    """
    Embed z okazjami (BUY / OBSERWUJ / ARBITRAŻ).
    Zakładam, że wcześniej już go miałeś – tu wersja uproszczona.
    """
    lines_buy = []
    lines_watch = []
    lines_arb = []

    # Fundamentalne okazje
    for s in stocks:
        rec = (s.get("recommendation") or "").upper()
        q = _calc_quality(s)
        line = (
            f"**{s.get('name')} ({s.get('ticker')}) @ {s.get('price', 0):.2f} zł** — "
            f"C/Z={s.get('pe') or 0:.1f} | C/WK={s.get('pbv') or 0:.2f} | "
            f"ROE={(s.get('roe') or 0) * 100:.1f}% | Jakość={q:.0f}/100"
        )
        if rec == "BUY":
            lines_buy.append(line)
        else:
            lines_watch.append(line)

    # Arbitraż
    for a in arbitrage or []:
        lines_arb.append(
            f"**{a.get('pair')}** Z={a.get('zscore') or 0:.2f} | "
            f"{a.get('signal') or 'NEUTRAL'} | Score={a.get('entry_score') or 0}/100"
        )

    desc_parts = []
    if lines_buy:
        desc_parts.append("🟢 **OKAZJE (BUY):**\n" + "\n".join(lines_buy))
    if lines_watch:
        desc_parts.append("🟡 **OBSERWUJ:**\n" + "\n".join(lines_watch))
    if lines_arb:
        desc_parts.append("🟠 **ARBITRAŻ — pary do obserwacji:**\n" + "\n".join(lines_arb))

    description = "\n\n".join(desc_parts) if desc_parts else "Brak wyraźnych okazji dziś."

    return {
        "embeds": [
            {
                "title": f"🎯 Okazje inwestycyjne — {datetime.now().strftime('%d.%m.%Y')}",
                "description": description,
                "color": 0xf1c40f,
                "footer": {"text": "GPW Analyst v2.0 • Okazje + arbitraż"},
            }
        ]
    }


def _build_agent_embed(signals: list) -> dict:
    """Embed sygnałów agenta: BUY malejąco wg score, potem SELL."""
    if not signals:
        description = "Brak nowych sygnałów tradingowych od agenta dziś."
        color = 0x95a5a6
    else:
        order = {"BUY": 0, "SELL": 1}
        ordered = sorted(
            signals,
            key=lambda s: (
                order.get((s.get("action") or "").upper(), 2),
                -(s.get("score") or 0),
            ),
        )
        buy_count = sum(1 for s in ordered if (s.get("action") or "").upper() == "BUY")
        sell_count = sum(1 for s in ordered if (s.get("action") or "").upper() == "SELL")

        lines = []
        for s in ordered:
            ticker = (s.get("ticker") or "N/A").replace(".WA", "")
            action = (s.get("action") or "").upper()
            reason = s.get("reason") or "Brak opisu."
            lines.append(f"**{ticker}** — **{action}**\n> {reason}")

        description = "\n\n".join(lines)
        if len(description) > 4000:
            description = description[:3990] + "\n…"

        if buy_count > sell_count:
            color = 0x2ecc71  # zielony
        elif sell_count > buy_count:
            color = 0xe74c3c  # czerwony
        else:
            color = 0x9b59b6  # neutralny/fiolet

    return {
        "embeds": [
            {
                "title": f"🤖 Sygnały agenta — {datetime.now().strftime('%d.%m.%Y')}",
                "description": description,
                "color": color,
                "footer": {
                    "text": "Ranking: fundamenty + momentum 20 sesji • nie jest rekomendacją inwestycyjną"
                },
            }
        ]
    }


def _get_claude_insight(stocks: list, arbitrage: list) -> str:
    """Pyta Groq o komentarz do dzisiejszej sytuacji rynkowej."""
    try:
        from groq import Groq

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

        # 1. PORTFEL INWESTORA (statyczny przykład)
        portfolio = {
            "PKO.WA": {"ilosc": 74, "cena_zakupu": 195.15},
            "PEO.WA": {"ilosc": 87, "cena_zakupu": 228.00},
            "ALR.WA": {"ilosc": 55, "cena_zakupu": 133.00},
            "KRU.WA": {"ilosc": 20, "cena_zakupu": 394.50},
            "KTY.WA": {"ilosc": 10, "cena_zakupu": 1263.30},
            "KGH.WA": {"ilosc": 21, "cena_zakupu": 335.60},
            "PZU.WA": {"ilosc": 100, "cena_zakupu": 73.82},
        }

        portfel_status = []
        for ticker, info in portfolio.items():
            stock = next((s for s in stocks if s.get("ticker") == ticker), None)
            if stock:
                kurs = stock.get("price", 0)
                zakup = info["cena_zakupu"]
                zmiana = ((kurs - zakup) / zakup * 100) if zakup else 0
                portfel_status.append(
                    {
                        "ticker": ticker,
                        "nazwa": stock.get("name", ticker),
                        "kurs": round(kurs, 2),
                        "cena_zakupu": zakup,
                        "zmiana_pct": round(zmiana, 2),
                        "ilosc": info["ilosc"],
                    }
                )

        # 2. TOP SPÓŁKI WIG20
        top_stocks = sorted(stocks, key=lambda x: _calc_quality(x), reverse=True)[:8]

        top_json = json.dumps(
            [
                {
                    "nazwa": s.get("name"),
                    "kurs": s.get("price"),
                    "cz": round(s.get("pe") or 0, 1),
                    "roe": f"{(s.get('roe') or 0):.1%}",
                    "rekomendacja": s.get("recommendation"),
                    "jakosc": _calc_quality(s),
                }
                for s in top_stocks
            ],
            ensure_ascii=False,
            indent=2,
        )

        # 3. SYGNAŁY ARBITRAŻU
        arb_alerts = [
            a for a in arbitrage or [] if a.get("signal") not in ("NEUTRAL", None)
        ]

        arb_json = json.dumps(
            [
                {
                    "para": a.get("pair"),
                    "zscore": round(a.get("zscore") or 0, 2),
                    "sygnał": a.get("signal"),
                    "score": a.get("entry_score"),
                }
                for a in arb_alerts
            ],
            ensure_ascii=False,
            indent=2,
        )

        # 3b. DZIENNIK SYGNAŁÓW + DANE HISTORYCZNE (liczy Python)
        log_signals(arb_alerts)
        context = build_context(arb_alerts, extra_tickers=list(portfolio.keys()))

        # 4. PROMPT
        prompt = f"""
Jesteś ekspertem inwestycyjnym GPW. Dzisiaj jest {datetime.now().strftime('%d.%m.%Y')}.

PORTFEL INWESTORA:
{json.dumps(portfel_status, ensure_ascii=False, indent=2)}

TOP SPÓŁKI WIG20:
{top_json}

SYGNAŁY ARBITRAŻU:
{arb_json}

{context}

Opieraj się wyłącznie na liczbach z powyższych sekcji, nie wymyślaj własnych.

Zasady:
- Nie zalecaj kupna ani sprzedaży akcji z portfela. Opisz stan, ryzyka i co warto sprawdzić.
- Różnica względem ceny zakupu to informacja, a nie powód do działania.
- Brak historii skuteczności sygnału oznacza "nie wiadomo", a nie "sygnał jest zły".

Napisz KONKRETNY komentarz (max 5 zdań):
1. Co jest najciekawsze w portfelu dziś?
2. Czy jest sygnał arbitrażu do działania?
3. Jedna rzecz do sprawdzenia przed otwarciem sesji.
Podawaj liczby. Bez ogólników.
"""


        # 5. Zapytanie do Groq
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )

        return response.choices[0].message.content or "Analiza AI niedostępna dziś."
    
    except Exception as e:
        import traceback

        print(f"Błąd Groq API: {e}")
        print(traceback.format_exc())
        return "Analiza AI niedostępna dziś."


def send_daily_report(
    webhook_url: str,
    stocks: list | None = None,
    image_path: str | None = None,
) -> bool:
    """Główny workflow: pobiera dane, buduje raport, wysyła na Discord, zapisuje snapshot, odpala agenta."""
    # Inicjalizacja bazy
    init_db()

    # Dane WIG20
    if stocks is None:
        print("Pobieram dane WIG20...")
        stocks = get_all_stocks()

    if not stocks:
        print("Brak danych do wysłania.")
        return False

    # Arbitraż
    try:
        arbitrage = get_all_arbitrage()
    except Exception as e:
        print(f"Błąd pobierania arbitrażu: {e}")
        arbitrage = []

    # Obraz tabeli
    if image_path:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        filename = os.path.basename(image_path)
    else:
        print("Generuję tabelę wskaźników (z prognozami AI)...")
        image_bytes = _build_table_image(stocks)
        filename = f"wig20_{datetime.now().strftime('%Y%m%d')}.png"

    # Główny embed
    payload = _build_embed(stocks)

    # Embed okazji
    opps_payload = _build_opportunities_embed(stocks, arbitrage)
    try:
        requests.post(webhook_url, json=opps_payload, timeout=30)
        print("Embed z okazjami wysłany.")
    except Exception as e:
        print(f"Błąd wysyłania embedu okazji: {e}")

    # Komentarz AI (Groq)
    print("Pytam Groq o komentarz...")
    insight = _get_claude_insight(stocks, arbitrage)
    insight_payload = {
        "embeds": [
            {
                "title": f"🤖 Komentarz AI — {datetime.now().strftime('%d.%m.%Y')}",
                "description": insight,
                "color": 0x9b59b6,
                "footer": {"text": "Groq • GPT-OSS 20B • GPW Analyst v2.0"},            }
        ]
    }
    try:
        requests.post(webhook_url, json=insight_payload, timeout=30)
        print("Komentarz AI wysłany.")
    except Exception as e:
        print(f"Błąd wysyłania komentarza AI: {e}")

    # Główny raport z obrazem
    print(f"Wysyłam raport na Discord ({len(stocks)} spółek)...")
    try:
        response = requests.post(
            webhook_url,
            data={"payload_json": json.dumps(payload)},
            files={"file": (filename, image_bytes, "image/png")},
            timeout=30,
        )
        if response.status_code in (200, 204):
            print(f"Raport wysłany! ({response.status_code})")

            # Agent dzienny
            try:
                from backend.agent import agent_daily_update

                signals = agent_daily_update(stocks)
                print("Agent wygenerował sygnały:", signals)

                agent_payload = _build_agent_embed(signals)
                requests.post(webhook_url, json=agent_payload, timeout=30)
                print("Embed sygnałów agenta wysłany.")
            except Exception as e:
                print(f"Błąd działania agenta lub wysyłania jego embedu: {e}")
                signals = []

            # Snapshot dnia
            try:
                # opportunities_json – na razie uproszczone: z arbitrażu
                opportunities = arbitrage or []
                save_daily_snapshot(
                    date=datetime.now().strftime("%Y-%m-%d"),
                    stocks_json=json.dumps(stocks, ensure_ascii=False),
                    arbitrage_json=json.dumps(arbitrage, ensure_ascii=False),
                    ai_comment=insight,
                    opportunities_json=json.dumps(opportunities, ensure_ascii=False),
                )
                print("Snapshot dnia zapisany.")
            except Exception as e:
                print(f"Błąd zapisu snapshotu dnia: {e}")

            return True
        else:
            print(
                f"Discord zwrócił błąd: {response.status_code} — {response.text}"
            )
            return False
    except requests.exceptions.RequestException as e:
        print(f"Błąd połączenia z Discord: {e}")
        return False


if __name__ == "__main__":
    # Użyj swojego webhooka tutaj
    WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
    ok = send_daily_report(webhook_url=WEBHOOK_URL)
    raise SystemExit(0 if ok else 1)
