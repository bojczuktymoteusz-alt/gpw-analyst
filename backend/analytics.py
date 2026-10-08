"""
Analityka dla raportu GPW (backend/analytics.py)

1. Cechy z historii cen (data/daily_prices.csv): zwroty, zmienność, wolumen, odległość od min/max.
2. Dziennik sygnałów arbitrażu (data/signal_journal.csv) + sprawdzanie, czy sygnały się sprawdziły.

Wszystkie liczby liczy Python. Model językowy dostaje gotowy tekst i tylko go interpretuje.
Żadna funkcja nie rzuca wyjątku na zewnątrz - raport ma się wysłać nawet przy braku danych.
"""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "daily_prices.csv"
JOURNAL = ROOT / "data" / "signal_journal.csv"
HORIZONS = (5, 10)  # po ilu sesjach oceniamy sygnał
JCOLS = ["date", "pair", "ticker_a", "ticker_b", "zscore", "signal", "entry_score"]


# ---------------------------------------------------------------- dane
def _load_prices():
    if not PRICES.exists():
        return None, None
    df = pd.read_csv(PRICES, parse_dates=["date"])
    if df.empty:
        return None, None
    close = df.pivot(index="date", columns="ticker", values="close").sort_index()
    volume = df.pivot(index="date", columns="ticker", values="volume").sort_index()
    return close, volume


def data_freshness_warning():
    """Tekst ostrzeżenia, gdy ostatnia sesja w danych jest wyraźnie nieaktualna; w przeciwnym razie None.
    Próg: co najmniej 2 dni robocze od ostatniej sesji (pojedyncza przerwa bywa świętem)."""
    try:
        close, _ = _load_prices()
        if close is None:
            return "Brak pliku z historią cen (data/daily_prices.csv)."
        last = close.index.max().date()
        today = datetime.now(timezone.utc).date()
        gap = int(np.busday_count(last, today))
        if gap >= 2:
            return (
                f"Ostatnia sesja w danych: {last} ({gap} dni roboczych temu). "
                f"Sprawdź, czy pobieranie cen działa (mogło też być święto)."
            )
        return None
    except Exception as e:
        print(f"[analytics] data_freshness_warning: {e}")
        return None


# ---------------------------------------------------------------- 2. cechy
def ticker_features(close, volume, t):
    if t not in close:
        return None
    s = close[t].dropna()
    if len(s) < 3:
        return None
    r = s.pct_change().dropna()
    n5 = min(5, len(s) - 1)
    n20 = min(20, len(s) - 1)
    last = s.iloc[-1]
    win = s.iloc[-(n20 + 1):]

    vol_ratio = None
    if t in volume:
        v = volume[t].dropna()
        base = v.iloc[:-1].tail(20).mean() if len(v) >= 5 else 0
        if base and base > 0 and v.iloc[-1] > 0:
            vol_ratio = float(v.iloc[-1] / base)

    return {
        "ticker": t.replace(".WA", ""),
        "ret1": float((last / s.iloc[-2] - 1) * 100),
        "ret5": float((last / s.iloc[-1 - n5] - 1) * 100),
        "n5": n5,
        "ret20": float((last / s.iloc[-1 - n20] - 1) * 100),
        "n20": n20,
        "vol": float(r.tail(n20).std() * 100),
        "vol_ratio": vol_ratio,
        "from_low": float((last / win.min() - 1) * 100),
        "from_high": float((last / win.max() - 1) * 100),
    }


# ---------------------------------------------------------------- 1. dziennik
def _split_pair(pair: str):
    a, b = [x.strip().replace(".WA", "") + ".WA" for x in pair.split("/")]
    return a, b


def log_signals(arb_alerts) -> int:
    """Dopisuje aktywne sygnały (bez NEUTRAL) do dziennika. Zwraca liczbę nowych wpisów."""
    try:
        close, _ = _load_prices()
        if close is None:
            return 0
        entry_date = close.index.max().strftime("%Y-%m-%d")  # ostatnia sesja w danych
        rows = []
        for a in arb_alerts or []:
            sig = a.get("signal")
            z = a.get("zscore")
            pair = a.get("pair_name") or a.get("pair") or a.get("name")
            if not pair or "/" not in pair or z is None or sig in (None, "NEUTRAL"):
                continue
            ta, tb = _split_pair(pair)
            rows.append({
                "date": entry_date, "pair": pair.replace(".WA", ""),
                "ticker_a": ta, "ticker_b": tb,
                "zscore": round(float(z), 4), "signal": sig,
                "entry_score": a.get("entry_score"),
            })
        if not rows:
            return 0

        new = pd.DataFrame(rows, columns=JCOLS)
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        if JOURNAL.exists():
            old = pd.read_csv(JOURNAL)
            before = len(old)
            allj = pd.concat([old, new], ignore_index=True)
        else:
            before = 0
            allj = new
        allj = allj.drop_duplicates(subset=["date", "pair"], keep="last")
        allj.to_csv(JOURNAL, index=False)
        return max(len(allj) - before, 0)
    except Exception as e:
        print(f"[analytics] log_signals: {e}")
        return 0


def evaluate():
    """Zwraca DataFrame: dla każdego sygnału zwrot spreadu (long/short) po 5 i 10 sesjach."""
    close, _ = _load_prices()
    if close is None or not JOURNAL.exists():
        return None
    j = pd.read_csv(JOURNAL, parse_dates=["date"])
    out = []
    for _, e in j.iterrows():
        if e["ticker_a"] not in close or e["ticker_b"] not in close:
            continue
        idx = close.index.get_indexer([e["date"]])[0]
        if idx < 0:
            continue
        # z < 0: A tania względem B -> long A / short B; z > 0: odwrotnie
        direction = 1 if e["zscore"] < 0 else -1
        rec = {"pair": e["pair"], "signal": e["signal"]}
        ca, cb = close[e["ticker_a"]], close[e["ticker_b"]]
        for h in HORIZONS:
            if idx + h < len(close):
                a0, a1 = ca.iloc[idx], ca.iloc[idx + h]
                b0, b1 = cb.iloc[idx], cb.iloc[idx + h]
                if pd.notna(a0) and pd.notna(a1) and pd.notna(b0) and pd.notna(b1):
                    rec[f"pnl{h}"] = direction * ((a1 / a0 - 1) - (b1 / b0 - 1)) * 100
        out.append(rec)
    return pd.DataFrame(out)


def _stats_line(df, h):
    col = f"pnl{h}"
    if col not in df:
        return None
    s = df[col].dropna()
    if s.empty:
        return None
    return f"{h} sesji: trafione {int((s > 0).sum())}/{len(s)}, średni wynik spreadu {s.mean():+.2f}%"


def track_record_text(active_pairs=()) -> str:
    j_total = len(pd.read_csv(JOURNAL)) if JOURNAL.exists() else 0
    ev = evaluate()
    if ev is None or ev.empty or not any(f"pnl{h}" in ev for h in HORIZONS):
        return (f"Dziennik sygnałów: {j_total} zapisanych, żaden nie dojrzał jeszcze do oceny "
                f"(potrzeba min. {HORIZONS[0]} sesji od sygnału).")

    lines = ["Skuteczność dotychczasowych sygnałów (wynik = zwrot long/short na parze):"]
    for sig, grp in ev.groupby("signal"):
        parts = [p for p in (_stats_line(grp, h) for h in HORIZONS) if p]
        if parts:
            lines.append(f"- {sig}: " + "; ".join(parts))
    for pair in active_pairs:
        grp = ev[ev["pair"] == pair]
        parts = [p for p in (_stats_line(grp, h) for h in HORIZONS) if p]
        if parts:
            lines.append(f"- {pair} (ta para wcześniej): " + "; ".join(parts))
    return "\n".join(lines)


# ---------------------------------------------------------------- kontekst do promptu
def build_context(arb_alerts, extra_tickers=()) -> str:
    try:
        close, volume = _load_prices()
        if close is None:
            return "Brak historii cen (data/daily_prices.csv) - komentarz bez danych historycznych."

        last_day = close.index.max().strftime("%Y-%m-%d")
        n_days = len(close)

        active_pairs, tickers = [], []
        for a in arb_alerts or []:
            pair = a.get("pair_name") or a.get("pair") or a.get("name")
            if pair and "/" in pair and a.get("signal") not in (None, "NEUTRAL"):
                active_pairs.append(pair.replace(".WA", ""))
                tickers += list(_split_pair(pair))
        tickers += list(extra_tickers)

        feats = {t: ticker_features(close, volume, t) for t in close.columns}
        feats = {t: f for t, f in feats.items() if f}

        # dokładamy największe ruchy 5-sesyjne i skoki wolumenu
        by_move1 = sorted(feats, key=lambda t: abs(feats[t]["ret1"]), reverse=True)[:3]
        by_move = sorted(feats, key=lambda t: abs(feats[t]["ret5"]), reverse=True)[:5]
        by_vol = [t for t in sorted(feats, key=lambda t: feats[t]["vol_ratio"] or 0, reverse=True)[:3]
                  if (feats[t]["vol_ratio"] or 0) >= 1.5]
        chosen = list(dict.fromkeys([t for t in tickers if t in feats] + by_move1 + by_move + by_vol))

        lines = [
            "DANE POLICZONE PRZEZ PYTHON (nie zmieniaj liczb, tylko je interpretuj):",
            f"Ostatnia sesja w danych: {last_day}, historia: {n_days} sesji.",
        ]
        for t in chosen:
            f = feats[t]
            if f["vol_ratio"]:
                vr = f"wolumen x{f['vol_ratio']:.1f} średniej"
                if f["vol_ratio"] < 0.3:
                    vr += " (ruch mało wiarygodny)"
            else:
                vr = "wolumen b/d"
            lines.append(
                f"- {f['ticker']}: ostatnia sesja {f['ret1']:+.1f}%, {f['n5']} sesji {f['ret5']:+.1f}%, {f['n20']} sesji {f['ret20']:+.1f}%, "
                f"zmienność dzienna {f['vol']:.1f}%, {vr}, "
                f"{f['from_low']:+.1f}% od minimum, {f['from_high']:+.1f}% od maksimum okna"
            )
        if n_days < 21:
            lines.append(f"(Uwaga: okno 20-sesyjne skrócone do dostępnych {n_days - 1} sesji.)")

        with_vol = {t: f for t, f in feats.items() if f["vol_ratio"]}
        if with_vol:
            hi = max(with_vol, key=lambda t: with_vol[t]["vol_ratio"])
            lo = min(with_vol, key=lambda t: with_vol[t]["vol_ratio"])
            lines.append(
                f"Skrajne wolumeny w ostatniej sesji (cały WIG20 + portfel): "
                f"najwyższy {with_vol[hi]['ticker']} x{with_vol[hi]['vol_ratio']:.1f} średniej, "
                f"najniższy {with_vol[lo]['ticker']} x{with_vol[lo]['vol_ratio']:.1f} średniej."
            )

        lines.append(track_record_text(active_pairs))
        return "\n".join(lines)
    except Exception as e:
        print(f"[analytics] build_context: {e}")
        return ""