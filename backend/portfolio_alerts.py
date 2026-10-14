"""
Alerty portfela (backend/portfolio_alerts.py)

Dwa niezależne alerty na Discorda:
1. PRÓG ZYSKU      - zysk portfela przekroczył FIXED_THRESHOLD (np. 4000 zł)
2. SPADEK OD SZCZYTU - zysk spadł o DRAWDOWN_PCT % od najwyższego poziomu, jaki osiągnął

Każdy alert wysyła się raz; kolejny dopiero po "resecie" (zysk zszedł poniżej FIXED_RESET,
albo spadek od szczytu zmalał do DRAWDOWN_RESET_PCT). Stan trzyma data/portfolio_state.json.

Zysk liczony jest z listy PORTFOLIO poniżej i cen zamknięcia z data/daily_prices.csv.
To przybliżenie: bez prowizji, swapów i kursów walut, więc może się różnić od XTB.
Alert zawiera tylko dane (zysk na pozycjach + wskaźniki techniczne), bez poleceń kupna/sprzedaży.
"""
import json
from pathlib import Path

import pandas as pd

try:
    from analytics import _load_prices
except ModuleNotFoundError:
    from backend.analytics import _load_prices

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "portfolio_state.json"
HISTORY = ROOT / "data" / "portfolio_pnl.csv"

# ---------------------------------------------------------------- USTAWIENIA
FIXED_THRESHOLD = 4000.0       # zł: alert, gdy zysk portfela >= tej kwoty
FIXED_RESET = 3500.0           # zł: alert uzbraja się ponownie, gdy zysk spadnie poniżej
DRAWDOWN_PCT = 20.0            # %: alert, gdy zysk spadł o tyle % od szczytu
DRAWDOWN_RESET_PCT = 10.0      # %: alert uzbraja się ponownie, gdy spadek od szczytu <= tyle
MIN_PEAK_FOR_DRAWDOWN = 1000.0 # zł: alert spadku tylko, gdy szczyt zysku był co najmniej taki
INITIAL_PEAK = None            # np. 4000.0, jeśli znasz swój dotychczasowy szczyt zysku
TAX_RATE = 0.19                # szacunek podatku od zrealizowanego zysku

# Pozycje (aktualizuj po transakcjach na XTB). Ceny zakupu = średnia cena w PLN.
PORTFOLIO = {
    "ALR.WA": {"ilosc": 15, "cena_zakupu": 133.00},
    "BDX.WA": {"ilosc": 10, "cena_zakupu": 680.00},
    "KTY.WA": {"ilosc": 10, "cena_zakupu": 1263.30},
    "KGH.WA": {"ilosc": 21, "cena_zakupu": 335.60},
    "KRU.WA": {"ilosc": 20, "cena_zakupu": 394.50},
    "PEO.WA": {"ilosc": 44, "cena_zakupu": 228.00},
    "PKO.WA": {"ilosc": 68.4897, "cena_zakupu": 105.15},
    "PZU.WA": {"ilosc": 201.1101, "cena_zakupu": 73.82},
}

PORTFOLIO_CSV = ROOT / "data" / "portfolio.csv"


def load_portfolio():
    """Pozycje z data/portfolio.csv (edytowalny np. na GitHubie); awaryjnie lista PORTFOLIO z kodu."""
    try:
        if PORTFOLIO_CSV.exists():
            df = pd.read_csv(PORTFOLIO_CSV)
            out = {}
            for _, r in df.iterrows():
                t = str(r["ticker"]).strip().upper()
                if not t.endswith(".WA"):
                    t += ".WA"
                out[t] = {"ilosc": float(r["ilosc"]), "cena_zakupu": float(r["cena_zakupu"])}
            if out:
                return out
    except Exception as e:
        print(f"[portfolio] błąd wczytania portfolio.csv: {e}")
    return PORTFOLIO

# ---------------------------------------------------------------- wskaźniki
def _rsi(series, n=14):
    d = series.diff().dropna()
    if len(d) < n:
        return None
    up = d.clip(lower=0)
    down = -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    ad = down.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    if ad == 0:
        return 100.0
    return float(100 - 100 / (1 + au / ad))


def _technicals(s):
    last = float(s.iloc[-1])
    out = {"rsi": _rsi(s), "sma20": None, "hi20": None}
    if len(s) >= 20:
        out["sma20"] = (last / float(s.tail(20).mean()) - 1) * 100
        out["hi20"] = (last / float(s.tail(20).max()) - 1) * 100
    return out


# ---------------------------------------------------------------- status portfela
def _compute_status():
    close, _ = _load_prices()
    if close is None:
        print("[portfolio] brak data/daily_prices.csv")
        return None
    rows, pnl, value, cost = [], 0.0, 0.0, 0.0
    for t, h in load_portfolio().items():
        if t not in close:
            continue
        s = close[t].dropna()
        if s.empty:
            continue
        price = float(s.iloc[-1])
        qty, buy = h["ilosc"], h["cena_zakupu"]
        p = (price - buy) * qty
        rows.append({
            "ticker": t.replace(".WA", ""),
            "pnl": p,
            "pct": (price / buy - 1) * 100 if buy else 0.0,
            "tech": _technicals(s),
        })
        pnl += p
        value += price * qty
        cost += buy * qty
    if not rows:
        return None
    rows.sort(key=lambda r: r["pnl"], reverse=True)
    return {
        "date": close.index.max().strftime("%Y-%m-%d"),
        "pnl": pnl, "value": value, "cost": cost, "rows": rows,
    }


# ---------------------------------------------------------------- stan i historia
def _load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_history(status):
    row = pd.DataFrame([{
        "date": status["date"], "pnl": round(status["pnl"], 2),
        "value": round(status["value"], 2), "cost": round(status["cost"], 2),
    }])
    if HISTORY.exists():
        row = pd.concat([pd.read_csv(HISTORY), row], ignore_index=True)
    row = row.drop_duplicates(subset=["date"], keep="last")
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    row.to_csv(HISTORY, index=False)


# ---------------------------------------------------------------- formatowanie
def _zl(x):
    return f"{x:+,.0f}".replace(",", " ") + " zł"


def _zl_abs(x):
    return f"{x:,.0f}".replace(",", " ") + " zł"


def _cell(v, spec, width):
    return "n/d".rjust(width) if v is None else f"{v:{spec}}".rjust(width)


def _table(rows):
    lines = [f"{'Sp.':<4} {'Zysk zł':>7} {'Zysk %':>7} {'RSI':>4} {'SMA20':>7} {'Max20':>7}"]
    for r in rows:
        t = r["tech"]
        lines.append(
            f"{r['ticker']:<4} {_cell(r['pnl'], '+.0f', 7)} {_cell(r['pct'], '+.1f', 6)}% "
            f"{_cell(t['rsi'], '.0f', 4)} {_cell(t['sma20'], '+.1f', 6)}% {_cell(t['hi20'], '+.1f', 6)}%"
        )
    return "```\n" + "\n".join(lines) + "\n```"


def _build_payload(status, triggers, peak, peak_date, dd_pct):
    kinds = {k for k, _ in triggers}
    if "drawdown" in kinds:
        title, color = "📉 Alert portfela: spadek od szczytu", 0xE74C3C
    elif "fixed" in kinds:
        title, color = "📈 Alert portfela: próg zysku", 0x2ECC71
    else:
        title, color = "🧪 Podgląd alertu portfela", 0x95A5A6

    tax = TAX_RATE * sum(max(r["pnl"], 0) for r in status["rows"])
    description = (
        "\n".join(f"• {text}" for _, text in triggers)
        + f"\n\n**Zysk portfela:** {_zl(status['pnl'])} "
          f"(wartość {_zl_abs(status['value'])}, koszt {_zl_abs(status['cost'])}, stan na {status['date']}).\n"
          f"**Szczyt zysku:** {_zl(peak)} ({peak_date}), spadek od szczytu: {dd_pct:.1f}%.\n\n"
        + _table(status["rows"])
        + f"\nSzacunkowy podatek {int(TAX_RATE * 100)}% przy sprzedaży wszystkich pozycji z zyskiem: "
          f"~{_zl_abs(tax)} (bez odliczeń strat i prowizji)."
    )
    return {
        "embeds": [{
            "title": title,
            "description": description[:4000],
            "color": color,
            "footer": {
                "text": "Dane informacyjne, nie rekomendacja • zysk z listy pozycji w kodzie "
                        "(bez prowizji, swapów i kursów walut)"
            },
        }]
    }


# ---------------------------------------------------------------- główna funkcja
def portfolio_alert_payload(dry_run=False, force=False):
    """Zwraca payload embedu Discorda albo None.
    dry_run=True: nie zapisuje stanu ani historii. force=True: wymusza podgląd (test)."""
    try:
        status = _compute_status()
        if status is None:
            return None
        state = _load_state()
        pnl = status["pnl"]

        # szczyt zysku
        if state.get("peak_pnl") is None:
            peak = max(pnl, INITIAL_PEAK) if INITIAL_PEAK is not None else pnl
            peak_date = status["date"] if peak == pnl else "ustawiony ręcznie"
        elif pnl >= state["peak_pnl"]:
            peak, peak_date = pnl, status["date"]
        else:
            peak, peak_date = state["peak_pnl"], state.get("peak_date", "?")
        dd_pct = (peak - pnl) / peak * 100 if peak > 0 else 0.0

        fixed_active = state.get("fixed_active", False)
        dd_active = state.get("dd_active", False)
        triggers = []

        if pnl >= FIXED_THRESHOLD and not fixed_active:
            triggers.append(("fixed", f"Zysk portfela osiągnął próg {_zl_abs(FIXED_THRESHOLD)} (teraz {_zl(pnl)})."))
            fixed_active = True
        elif pnl < FIXED_RESET:
            fixed_active = False

        if peak >= MIN_PEAK_FOR_DRAWDOWN and dd_pct >= DRAWDOWN_PCT and not dd_active:
            triggers.append((
                "drawdown",
                f"Zysk spadł o {dd_pct:.1f}% od szczytu ({_zl(peak)} z {peak_date}, teraz {_zl(pnl)}).",
            ))
            dd_active = True
        elif dd_pct <= DRAWDOWN_RESET_PCT:
            dd_active = False

        print(f"[portfolio] zysk {pnl:.0f} zł, szczyt {peak:.0f} zł, spadek od szczytu {dd_pct:.1f}%")

        if not dry_run:
            _save_state({
                "peak_pnl": peak, "peak_date": peak_date,
                "fixed_active": fixed_active, "dd_active": dd_active,
                "last_pnl": pnl, "last_date": status["date"],
            })
            _append_history(status)

        if force and not triggers:
            triggers.append(("test", "Podgląd alertu (tryb testowy), bez zmiany stanu."))
        if not triggers:
            return None
        return _build_payload(status, triggers, peak, peak_date, dd_pct)
    except Exception as e:
        print(f"[portfolio] błąd: {e}")
        return None