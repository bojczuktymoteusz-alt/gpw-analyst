"""
Agent dzienny GPW (backend/agent.py)

Zmiany względem poprzedniej wersji:
- historia cen z data/daily_prices.csv (działa lokalnie i w GitHub Actions), nie z bazy SQLite
- momentum liczone z ostatnich 20 sesji, a nie z całej dostępnej historii
- dziennik sygnałów agenta (data/agent_journal.csv) + ocena po 5 i 10 sesjach
- agent_daily_update(stocks) bierze fundamenty z listy spółek przekazanej przez raport
- progi i wzory scoringu bez zmian (BUY > 60, SELL < 20) - dziennik pokaże, czy mają sens
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "daily_prices.csv"
JOURNAL = ROOT / "data" / "agent_journal.csv"
DB_NAME = str(ROOT / "gpw_data.db")

MOM_WINDOW = 20      # sesji do liczenia momentum
HORIZONS = (5, 10)   # po ilu sesjach oceniamy sygnał
BUY_THRESHOLD = 60
SELL_THRESHOLD = 20


# --- Dane ---
def _load_close():
    if not PRICES.exists():
        print("[agent] brak data/daily_prices.csv - momentum będzie zerowe")
        return None
    df = pd.read_csv(PRICES, parse_dates=["date"])
    if df.empty:
        return None
    return df.pivot(index="date", columns="ticker", values="close").sort_index()


def _stocks_from_db():
    """Awaryjnie: fundamenty z ostatniego dziennego snapshotu w bazie (tylko lokalnie)."""
    try:
        conn = sqlite3.connect(DB_NAME)
        row = conn.execute(
            "SELECT stocks_json FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return json.loads(row[0]) if row else []
    except Exception as e:
        print(f"[agent] brak fundamentów z bazy: {e}")
        return []


# --- Momentum ---
def calc_momentum(prices: list):
    """Procentowa zmiana między początkiem a końcem podanej listy cen."""
    if len(prices) < 2:
        return 0.0
    start, end = prices[0], prices[-1]
    if not start:
        return 0.0
    return (end - start) / start


# --- Fundamental Score ---
def _as_fraction(x, limit):
    """Część źródeł (np. yfinance) podaje wartości w procentach (4.5 zamiast 0.045).
    Jeśli wartość przekracza limit, uznajemy ją za procent i dzielimy przez 100."""
    if x is None:
        return None
    return x / 100 if abs(x) > limit else x


def calc_fundamental_score(stock):
    """Ocena fundamentalna spółki (0-85)."""
    score = 0

    pe = stock.get("pe")
    if pe and pe > 0:
        if pe < 10: score += 25
        elif pe < 15: score += 15
        elif pe < 20: score += 5

    roe = _as_fraction(stock.get("roe"), 1.5)
    if roe:
        if roe > 0.15: score += 25
        elif roe > 0.10: score += 15
        elif roe > 0.05: score += 5

    dy = _as_fraction(stock.get("div_yield"), 1.5)
    if dy:
        if dy > 0.05: score += 20
        elif dy > 0.03: score += 10

    debt = _as_fraction(stock.get("debt_to_equity"), 5)
    if debt:
        if debt < 0.5: score += 15
        elif debt < 1.0: score += 5

    return score


def score_stock(stock, close):
    ticker = stock["ticker"]
    momentum = 0.0
    if close is not None and ticker in close:
        prices = close[ticker].dropna().tail(MOM_WINDOW + 1).tolist()
        momentum = calc_momentum(prices)
    fundamental = calc_fundamental_score(stock)
    return {
        "ticker": ticker,
        "momentum": momentum,
        "fundamental": fundamental,
        "score": fundamental + momentum * 100,
    }


def generate_signals(stocks, close):
    signals = []
    for stock in stocks or []:
        if not stock.get("ticker"):
            continue
        s = score_stock(stock, close)
        detail = f"Score {s['score']:.1f}, momentum {s['momentum']:.2%}, fundamental {s['fundamental']}"
        if s["score"] > BUY_THRESHOLD:
            action = "BUY"
        elif s["score"] < SELL_THRESHOLD:
            action = "SELL"
        else:
            continue
        signals.append({
            "ticker": s["ticker"], "action": action, "reason": detail,
            "score": s["score"], "momentum": s["momentum"],
        })
    return signals


# --- Dziennik sygnałów i ocena ---
def log_agent_signals(signals, close):
    """Dopisuje sygnały do data/agent_journal.csv (data = ostatnia sesja w danych)."""
    try:
        if close is None or not signals:
            return
        entry = close.index.max().strftime("%Y-%m-%d")
        new = pd.DataFrame([{
            "date": entry, "ticker": s["ticker"], "action": s["action"],
            "score": round(s["score"], 1), "momentum": round(s["momentum"], 4),
        } for s in signals])
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        if JOURNAL.exists():
            new = pd.concat([pd.read_csv(JOURNAL), new], ignore_index=True)
        new = new.drop_duplicates(subset=["date", "ticker"], keep="last")
        new.to_csv(JOURNAL, index=False)
    except Exception as e:
        print(f"[agent] dziennik: {e}")


def agent_track_record(close):
    """Zwraca {(akcja, horyzont): [wyniki pozycji w %]} dla dojrzałych sygnałów."""
    res = {}
    try:
        if close is None or not JOURNAL.exists():
            return res
        j = pd.read_csv(JOURNAL, parse_dates=["date"])
        for _, e in j.iterrows():
            if e["ticker"] not in close:
                continue
            idx = close.index.get_indexer([e["date"]])[0]
            if idx < 0:
                continue
            s = close[e["ticker"]]
            sign = 1 if e["action"] == "BUY" else -1  # SELL zarabia na spadku
            for h in HORIZONS:
                if idx + h < len(close):
                    p0, p1 = s.iloc[idx], s.iloc[idx + h]
                    if pd.notna(p0) and pd.notna(p1) and p0:
                        res.setdefault((e["action"], h), []).append(sign * (p1 / p0 - 1) * 100)
    except Exception as e:
        print(f"[agent] ocena sygnałów: {e}")
    return res


def _record_suffix(action, rec):
    parts = []
    for h in HORIZONS:
        v = rec.get((action, h))
        if v:
            parts.append(f"{h}s: {sum(x > 0 for x in v)}/{len(v)} trafionych, śr. {sum(v) / len(v):+.1f}%")
    return f" | dotychczas {action} - " + "; ".join(parts) if parts else ""


# --- Zapis do SQLite (tylko lokalnie; w Actions baza nie istnieje, więc pomijamy) ---
def save_agent_signals(signals):
    try:
        conn = sqlite3.connect(DB_NAME)
        for sig in signals:
            conn.execute(
                """
                INSERT INTO snapshots(timestamp, snapshot_type, ticker, pair_name, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (datetime.now().isoformat(), "agent_signal", sig["ticker"], None, json.dumps(sig)),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[agent] zapis do bazy pominięty: {e}")


def is_agent_report_day():
    """Zwraca True co 4 dni."""
    today = datetime.now().date()
    anchor_date = datetime(2024, 1, 1).date()
    return (today - anchor_date).days % 4 == 0


def send_agent_report(signals):
    """Tu wstawiasz wysyłkę na Discord lub maila."""
    print("Raport agenta (co 4 dni):")
    for s in signals:
        print(f"{s['ticker']} -> {s['action']} ({s['reason']})")


# --- Główna funkcja agenta ---
def agent_daily_update(stocks=None, dry_run=False):
    """stocks: lista spółek z raportu (z fundamentami). dry_run=True: bez zapisu dziennika i bazy."""
    close = _load_close()
    if stocks is None:
        stocks = _stocks_from_db()

    signals = generate_signals(stocks, close)

    rec = agent_track_record(close)  # liczone przed dopisaniem dzisiejszych sygnałów
    for s in signals:
        s["reason"] += _record_suffix(s["action"], rec)

    if not dry_run:
        log_agent_signals(signals, close)
        save_agent_signals(signals)
        if is_agent_report_day():
            send_agent_report(signals)

    return signals


if __name__ == "__main__":
    for s in agent_daily_update(dry_run=True):
        print(s)