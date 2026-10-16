"""
Agent dzienny GPW (backend/agent.py)

Zmiany względem poprzedniej wersji:
- historia cen z data/daily_prices.csv (działa lokalnie i w GitHub Actions), nie z bazy SQLite
- momentum liczone z ostatnich 20 sesji, a nie z całej dostępnej historii
- dziennik rekomendacji append-only (data/agent_recommendations.jsonl)
- powiązane wyniki po 5 i 10 sesjach (data/agent_outcomes.jsonl)
- migracja zachowawcza starego data/agent_journal.csv
- agent_daily_update(stocks) bierze fundamenty z listy spółek przekazanej przez raport
- progi i wzory scoringu bez zmian (BUY > 60, SELL < 20) - dziennik pokaże, czy mają sens
"""
import csv
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "daily_prices.csv"
JOURNAL = ROOT / "data" / "agent_journal.csv"
RECOMMENDATIONS = ROOT / "data" / "agent_recommendations.jsonl"
OUTCOMES = ROOT / "data" / "agent_outcomes.jsonl"
DB_NAME = str(ROOT / "gpw_data.db")

MOM_WINDOW = 20      # sesji do liczenia momentum
HORIZONS = (5, 10)   # po ilu sesjach oceniamy sygnał
BUY_THRESHOLD = 60
SELL_THRESHOLD = 20
RULES_VERSION = "gpw_agent_fixed_rules_v1"


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
    return sum(item["points"] for item in _fundamental_components(stock).values())


def _fundamental_components(stock):
    """Freeze input values and point contributions used by the existing rules."""
    pe = stock.get("pe")
    roe_raw = stock.get("roe")
    div_yield_raw = stock.get("div_yield")
    debt_raw = stock.get("debt_to_equity")
    roe = _as_fraction(roe_raw, 1.5)
    dy = _as_fraction(div_yield_raw, 1.5)
    debt = _as_fraction(debt_raw, 5)

    pe_points = 0
    if pe and pe > 0:
        if pe < 10: pe_points = 25
        elif pe < 15: pe_points = 15
        elif pe < 20: pe_points = 5

    roe_points = 0
    if roe:
        if roe > 0.15: roe_points = 25
        elif roe > 0.10: roe_points = 15
        elif roe > 0.05: roe_points = 5

    dividend_points = 0
    if dy:
        if dy > 0.05: dividend_points = 20
        elif dy > 0.03: dividend_points = 10

    debt_points = 0
    if debt:
        if debt < 0.5: debt_points = 15
        elif debt < 1.0: debt_points = 5

    return {
        "pe": {"raw_value": pe, "normalized_value": pe, "points": pe_points},
        "roe": {"raw_value": roe_raw, "normalized_value": roe, "points": roe_points},
        "div_yield": {"raw_value": div_yield_raw, "normalized_value": dy, "points": dividend_points},
        "debt_to_equity": {"raw_value": debt_raw, "normalized_value": debt, "points": debt_points},
    }


def score_stock(stock, close):
    ticker = stock["ticker"]
    momentum = 0.0
    if close is not None and ticker in close:
        prices = close[ticker].dropna().tail(MOM_WINDOW + 1).tolist()
        momentum = calc_momentum(prices)
    components = _fundamental_components(stock)
    fundamental = sum(item["points"] for item in components.values())
    return {
        "ticker": ticker,
        "momentum": momentum,
        "fundamental": fundamental,
        "fundamental_components": components,
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
            "fundamental": s["fundamental"],
            "fundamental_components": s["fundamental_components"],
            "signal_id": str(uuid.uuid4()),
            "signal_at": datetime.now(timezone.utc).isoformat(),
        })
    return signals


# --- Dziennik sygnałów i ocena ---
def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def _read_jsonl(path):
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                records.append(json.loads(line))
    return records


def _append_jsonl(path, records, id_key):
    """Append missing IDs only. Existing lines are never rewritten or replaced."""
    if not records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = {r.get(id_key) for r in _read_jsonl(path)}
    added = 0
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for record in records:
            record_id = record.get(id_key)
            if not record_id or record_id in existing_ids:
                continue
            stream.write(json.dumps(_json_safe(record), ensure_ascii=False, allow_nan=False) + "\n")
            existing_ids.add(record_id)
            added += 1
    return added


def _price_reference(ticker, stock, close):
    series = close[ticker].dropna() if close is not None and ticker in close else pd.Series(dtype=float)
    close_reference = None
    if not series.empty:
        price_date = pd.Timestamp(series.index[-1]).date().isoformat()
        close_reference = {
            "value": float(series.iloc[-1]), "currency": "PLN", "date": price_date,
            "source": "data/daily_prices.csv:close",
            "basis": "yfinance Close; daily_snapshot.fetch uses auto_adjust=False",
        }

    quote = stock.get("price")
    updated_at = stock.get("last_updated")
    quote_date = str(updated_at)[:10] if updated_at else None
    try:
        quote_value = float(quote)
    except (TypeError, ValueError):
        quote_value = None
    valid_quote = quote_value is not None and math.isfinite(quote_value) and quote_value > 0
    reference = ({
        "value": quote_value, "currency": "PLN", "date": quote_date,
        "source": "agent stock input:price", "observed_at": updated_at,
        "basis": "quote snapshot passed to the agent; source freshness follows observed_at",
    } if valid_quote else close_reference)
    return reference or {"value": None, "currency": "PLN", "date": None, "source": None}, series, close_reference


def _fundamental_snapshot(stock, components):
    fields = ("pe", "pbv", "roe", "div_yield", "debt_to_equity", "payout_ratio",
              "operating_margin", "ebitda", "total_debt", "total_cash", "market_cap",
              "recommendation", "last_updated")
    return {
        "source": "stock payload passed to backend.agent.agent_daily_update",
        "observed_at": stock.get("last_updated"),
        "inputs": {field: stock.get(field) for field in fields},
        "score_components": components,
    }


def log_agent_signals(signals, close, stocks=None):
    """Append immutable recommendation snapshots to the repository-backed JSONL ledger."""
    if not signals:
        return 0
    stocks_by_ticker = {s.get("ticker"): s for s in (stocks or []) if s.get("ticker")}
    records = []
    for sig in signals:
        sig.setdefault("signal_id", str(uuid.uuid4()))
        sig.setdefault("signal_at", datetime.now(timezone.utc).isoformat())
        signal_at = sig["signal_at"]
        stock = stocks_by_ticker.get(sig["ticker"], {})
        reference, price_series, close_reference = _price_reference(sig["ticker"], stock, close)
        signal_date = (close_reference or reference).get("date")
        if signal_date is None and close is not None and not close.empty:
            signal_date = pd.Timestamp(close.index.max()).date().isoformat()
        window = price_series.tail(MOM_WINDOW + 1)
        components = sig.get("fundamental_components") or _fundamental_components(stock)
        sig["signal_date"] = signal_date
        sig["price_reference"] = reference
        sig["momentum_price_reference"] = close_reference
        sig["fundamental_snapshot"] = _fundamental_snapshot(stock, components)
        sig["rules_version"] = RULES_VERSION
        records.append({
            "schema_version": 1,
            "signal_id": sig["signal_id"],
            "signal_at": signal_at,
            "signal_date": signal_date,
            "ticker": sig["ticker"],
            "action": sig["action"],
            "score": sig["score"],
            "momentum": sig["momentum"],
            "fundamental_score": sig.get("fundamental"),
            "fundamental_components": components,
            "fundamental_snapshot": _fundamental_snapshot(stock, components),
            "price_reference": reference,
            "momentum_price_reference": close_reference,
            "market_quote": {"value": stock.get("price"), "observed_at": stock.get("last_updated")},
            "data_state": {
                "price_history_file": "data/daily_prices.csv",
                "price_history_as_of": (
                    pd.Timestamp(close.index.max()).date().isoformat()
                    if close is not None and not close.empty else None
                ),
                "ticker_price_observations": int(price_series.notna().sum()),
                "momentum_window_start": (
                    pd.Timestamp(window.index[0]).date().isoformat() if not window.empty else None
                ),
                "momentum_window_end": (
                    pd.Timestamp(window.index[-1]).date().isoformat() if not window.empty else None
                ),
                "fundamental_observed_at": stock.get("last_updated"),
            },
            "reason": sig.get("reason"),
            "rules_version": RULES_VERSION,
            "origin": "live_generation",
        })
    return _append_jsonl(RECOMMENDATIONS, records, "signal_id")


def _legacy_signal_id(row, ordinal):
    values = [str(row.get(k, "")) for k in ("date", "ticker", "action", "score", "momentum")]
    raw = "gpw-agent-legacy-v1|" + "|".join(values) + f"|{ordinal}"
    return "legacy-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _legacy_records():
    if not JOURNAL.exists():
        return []
    records = []
    with JOURNAL.open("r", encoding="utf-8", newline="") as stream:
        for ordinal, row in enumerate(csv.DictReader(stream)):
            signal_date = row.get("date") or None
            records.append({
                "schema_version": 1,
                "signal_id": _legacy_signal_id(row, ordinal),
                "signal_at": None,
                "signal_date": signal_date,
                "ticker": row.get("ticker"),
                "action": row.get("action"),
                "score": float(row["score"]) if row.get("score") else None,
                "momentum": float(row["momentum"]) if row.get("momentum") else None,
                "fundamental_score": None,
                "fundamental_components": None,
                "fundamental_snapshot": None,
                "price_reference": {"value": None, "currency": "PLN", "date": signal_date,
                                    "source": None, "basis": "not present in legacy CSV"},
                "reason": None,
                "rules_version": "unknown_legacy",
                "data_state": {
                    "source_journal": "data/agent_journal.csv",
                    "status": "legacy_incomplete",
                    "unavailable_fields": ["signal_at", "reference_price", "fundamentals", "reason", "rules_version"],
                },
                "origin": "legacy_migration",
            })
    return records


def migrate_legacy_agent_journal():
    """Copy old CSV entries once into the append-only ledger without changing the CSV."""
    records = _legacy_records()
    return _append_jsonl(RECOMMENDATIONS, records, "signal_id")


def _signal_records():
    records = _read_jsonl(RECOMMENDATIONS)
    known = {r.get("signal_id") for r in records}
    records.extend(r for r in _legacy_records() if r.get("signal_id") not in known)
    return records


def _calculate_outcome(signal, close, horizon):
    if close is None or not signal.get("ticker") or signal["ticker"] not in close:
        return None
    signal_date = signal.get("signal_date")
    if not signal_date:
        return None
    idx = close.index.get_indexer([pd.Timestamp(signal_date)])[0]
    if idx < 0 or idx + horizon >= len(close):
        return None
    series = close[signal["ticker"]]
    p0, p1 = series.iloc[idx], series.iloc[idx + horizon]
    p0_source = "data/daily_prices.csv:close"
    reference = signal.get("momentum_price_reference") or signal.get("price_reference") or {}
    reference_value = reference.get("value")
    if (signal.get("origin") == "live_generation"
            and reference.get("source") == "data/daily_prices.csv:close"
            and reference_value is not None):
        p0 = reference_value
        p0_source = reference["source"]
    if pd.isna(p0) or pd.isna(p1) or not p0:
        return None
    ret = (p1 / p0 - 1) * 100
    benchmark = _benchmark_return(close, idx, horizon)
    if benchmark is None:
        return None
    sign = 1 if signal.get("action") == "BUY" else -1
    return {
        "outcome_id": f"{signal['signal_id']}:{horizon}",
        "signal_id": signal["signal_id"],
        "ticker": signal["ticker"],
        "action": signal.get("action"),
        "horizon_sessions": horizon,
        "signal_date": signal_date,
        "outcome_date": pd.Timestamp(close.index[idx + horizon]).date().isoformat(),
        "entry_price_used": float(p0),
        "entry_price_source": p0_source,
        "end_price": float(p1),
        "raw_return_pct": float(ret),
        "position_return_pct": float(sign * ret),
        "benchmark_return_pct": float(benchmark),
        "excess_return_pct": float(sign * (ret - benchmark)),
        "price_source": "data/daily_prices.csv:close",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def persist_matured_agent_outcomes(close):
    """Append each matured horizon once, always keyed to its source signal_id."""
    existing = {r.get("outcome_id") for r in _read_jsonl(OUTCOMES)}
    records = []
    for signal in _read_jsonl(RECOMMENDATIONS):
        for horizon in HORIZONS:
            outcome = _calculate_outcome(signal, close, horizon)
            if outcome and outcome["outcome_id"] not in existing:
                records.append(outcome)
                existing.add(outcome["outcome_id"])
    return _append_jsonl(OUTCOMES, records, "outcome_id")


def _benchmark_return(close, idx, h):
    """Średni zwrot (%) wszystkich spółek w danych (równa waga) od sesji idx do idx+h.
    To przybliżenie rynku: WIG20 + kilka dodatkowych spółek z pliku cen."""
    a, b = close.iloc[idx], close.iloc[idx + h]
    r = (b / a - 1).replace([float("inf"), float("-inf")], float("nan")).dropna()
    return float(r.mean() * 100) if len(r) else None


def agent_track_record(close):
    """Zwraca {(akcja, horyzont): [wyniki pozycji w %]} dla dojrzałych sygnałów."""
    res = {}
    try:
        saved = {r.get("outcome_id"): r for r in _read_jsonl(OUTCOMES)}
        for signal in _signal_records():
            for h in HORIZONS:
                outcome_id = f"{signal['signal_id']}:{h}"
                outcome = saved.get(outcome_id) or _calculate_outcome(signal, close, h)
                if outcome:
                    res.setdefault((signal["action"], h), []).append(
                        (outcome["position_return_pct"], outcome["excess_return_pct"])
                    )
    except Exception as e:
        print(f"[agent] ocena sygnałów: {e}")
    return res


def _record_suffix(action, rec):
    parts = []
    for h in HORIZONS:
        v = rec.get((action, h))
        if v:
            n = len(v)
            beat = sum(1 for _, ex in v if ex > 0)
            mean_abs = sum(a for a, _ in v) / n
            mean_ex = sum(ex for _, ex in v) / n
            parts.append(
                f"{h} sesji: {beat}/{n} lepiej niż rynek, śr. {mean_ex:+.1f}% wobec rynku "
                f"({mean_abs:+.1f}% bezwzględnie)"
            )
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

    if not dry_run:
        migrate_legacy_agent_journal()
        persist_matured_agent_outcomes(close)
        log_agent_signals(signals, close, stocks)
        save_agent_signals(signals)

    rec = agent_track_record(close)  # liczone przed dopisaniem dzisiejszych sygnałów
    for s in signals:
        s["reason"] += _record_suffix(s["action"], rec)

    if not dry_run:
        if is_agent_report_day():
            send_agent_report(signals)

    return signals


if __name__ == "__main__":
    for s in agent_daily_update(dry_run=True):
        print(s)
