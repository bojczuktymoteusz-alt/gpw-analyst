"""
Pomocnicze formatowanie raportu (backend/report_helpers.py)

Zmiany względem poprzedniego raportu:
- C/Z, C/WK i ROE: "n/m" zamiast 0.0 (strata / brak sensu) oraz gwiazdka przy wartościach skrajnych
- neutralne etykiety zamiast BUY/SELL (ranking agenta, konsensus analityków, relacja pary)
- opis pary jako relatywnej wyceny (akcje w XTB są long-only, więc to nie jest instrukcja dwóch pozycji)
- stopki z datą ostatniej sesji w historii i godziną pobrania danych
- ostrzeżenie o nietypowym ruchu (duża zmiana przy dużym wolumenie), bez zgadywania przyczyny
"""
from datetime import datetime, timezone

try:
    from analytics import _load_prices, ticker_features
except ModuleNotFoundError:
    from backend.analytics import _load_prices, ticker_features


# ---------------------------------------------------------------- formatowanie
def fmt_pe(pe):
    return "n/m" if pe is None or pe <= 0 else f"{pe:.1f}"


def fmt_pbv(pbv):
    if pbv is None or pbv <= 0:
        return "n/m"
    return f"{pbv:.2f}" + ("*" if pbv > 50 else "")


def fmt_roe(roe):
    if roe is None:
        return "n/m"
    return f"{roe * 100:.1f}%" + ("*" if abs(roe) > 0.6 else "")


def arb_label(pair, z, signal):
    """Opis relacji pary zamiast BUY_A_SELL_B."""
    sig = signal or "NEUTRAL"
    if sig == "NEUTRAL":
        return "neutralnie"
    try:
        x, y = [p.strip().replace(".WA", "") for p in (pair or "").split("/")]
    except ValueError:
        return sig
    prefix = "obserwacja: " if sig.startswith("WATCH") else ""
    if (z or 0) < 0:
        return f"{prefix}{x} relatywnie tańsza od {y}"
    return f"{prefix}{x} relatywnie droższa od {y}"


def session_footer():
    """Data ostatniej sesji w historii cen i godzina pobrania danych."""
    try:
        close, _ = _load_prices()
        last = close.index.max().strftime("%d.%m") if close is not None else "b/d"
    except Exception:
        last = "b/d"
    now = datetime.now(timezone.utc).strftime("%H:%M")
    return f"historia do sesji {last} • pobrano {now} UTC"


def calc_quality(stock):
    """Ta sama prosta punktacja jakości co w discord_report.py."""
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


# ---------------------------------------------------------------- nietypowe ruchy
def event_flags_text(min_move=5.0, min_vol=2.5):
    """Ostrzeżenie, gdy ostatnia sesja miała duży ruch przy dużym wolumenie. Nie zgaduje przyczyny."""
    try:
        close, volume = _load_prices()
        if close is None:
            return None
        items = []
        for t in close.columns:
            f = ticker_features(close, volume, t)
            if f and f["vol_ratio"] and abs(f["ret1"]) >= min_move and f["vol_ratio"] >= min_vol:
                items.append(f"{f['ticker']} ({f['ret1']:+.1f}%, wolumen x{f['vol_ratio']:.1f})")
        if not items:
            return None
        return (
            "⚠️ Nietypowy ruch w ostatniej sesji: " + ", ".join(items) + ". "
            "Sprawdź komunikaty ESPI/EBI tych spółek (np. gpw.pl/komunikaty). Agent nie zna przyczyny ruchu."
        )
    except Exception as e:
        print(f"[report_helpers] event_flags_text: {e}")
        return None


# ---------------------------------------------------------------- embedy
def _build_embed(stocks):
    rows = []
    for s in stocks:
        rows.append(
            f"**{s.get('ticker')}** — {s.get('name')} @ {s.get('price', 0):.2f} zł\n"
            f"C/Z={fmt_pe(s.get('pe'))} | C/WK={fmt_pbv(s.get('pbv'))} | "
            f"ROE={fmt_roe(s.get('roe'))} | Konsensus analityków: {s.get('recommendation') or 'N/A'} | "
            f"Jakość={calc_quality(s):.0f}/100"
        )
    return {
        "embeds": [{
            "title": f"📊 Raport WIG20 — {datetime.now().strftime('%d.%m.%Y')}",
            "description": "\n\n".join(rows)[:4000],
            "color": 0x3498DB,
            "footer": {
                "text": f"GPW Analyst v2.0 • ceny na żywo, {session_footer()} • "
                        f"* wartość skrajna (np. mały kapitał własny) • n/m = brak sensu (strata)"
            },
        }]
    }


def _build_opportunities_embed(stocks, arbitrage):
    lines_buy, lines_watch, lines_arb = [], [], []

    for s in stocks:
        rec = (s.get("recommendation") or "").upper()
        line = (
            f"**{s.get('name')} ({s.get('ticker')}) @ {s.get('price', 0):.2f} zł** — "
            f"C/Z={fmt_pe(s.get('pe'))} | C/WK={fmt_pbv(s.get('pbv'))} | "
            f"ROE={fmt_roe(s.get('roe'))} | Jakość={calc_quality(s):.0f}/100"
        )
        (lines_buy if rec == "BUY" else lines_watch).append(line)

    for a in arbitrage or []:
        z = a.get("zscore") or 0
        lines_arb.append(
            f"**{a.get('pair')}** Z={z:.2f} | {arb_label(a.get('pair'), z, a.get('signal'))} | "
            f"Score={a.get('entry_score') or 0}/100"
        )

    parts = []
    if lines_buy:
        parts.append("🟢 **Konsensus analityków: kupuj**\n" + "\n".join(lines_buy))
    if lines_watch:
        parts.append("🟡 **Pozostałe (trzymaj / brak rekomendacji)**\n" + "\n".join(lines_watch))
    if lines_arb:
        parts.append("🟠 **Pary: relatywna wycena**\n" + "\n".join(lines_arb))
    description = "\n\n".join(parts) if parts else "Brak danych dziś."

    return {
        "embeds": [{
            "title": f"📋 Przegląd spółek i par — {datetime.now().strftime('%d.%m.%Y')}",
            "description": description[:4000],
            "color": 0xF1C40F,
            "footer": {
                "text": f"Konsensus pochodzi z Yahoo Finance, to nie model agenta • Akcje w XTB są long-only: "
                        f"sygnał pary to informacja o relatywnej wycenie, nie instrukcja dwóch pozycji • "
                        f"{session_footer()}"
            },
        }]
    }


def _build_agent_embed(signals):
    labels = {"BUY": "wysoki ranking", "SELL": "niski ranking"}
    if not signals:
        description = "Brak nowych wyników rankingu agenta dziś."
        color = 0x95A5A6
    else:
        order = {"BUY": 0, "SELL": 1}
        ordered = sorted(
            signals,
            key=lambda s: (order.get((s.get("action") or "").upper(), 2), -(s.get("score") or 0)),
        )
        buy = sum(1 for s in ordered if (s.get("action") or "").upper() == "BUY")
        sell = sum(1 for s in ordered if (s.get("action") or "").upper() == "SELL")
        lines = []
        for s in ordered:
            ticker = (s.get("ticker") or "N/A").replace(".WA", "")
            action = (s.get("action") or "").upper()
            lines.append(f"**{ticker}** — **{labels.get(action, action)}**\n> {s.get('reason') or 'Brak opisu.'}")
        description = "\n\n".join(lines)[:4000]
        color = 0x2ECC71 if buy > sell else 0xE74C3C if sell > buy else 0x9B59B6

    return {
        "embeds": [{
            "title": f"🤖 Ranking agenta — {datetime.now().strftime('%d.%m.%Y')}",
            "description": description,
            "color": color,
            "footer": {
                "text": "Ranking = fundamenty + momentum 20 sesji (stałe reguły). "
                        "To nie jest sygnał wejścia ani rekomendacja inwestycyjna."
            },
        }]
    }