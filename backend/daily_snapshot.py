"""
Dzienny snapshot zamknięcia GPW -> data/daily_prices.csv

- pobiera ostatnie ~10 dni z yfinance i dopisuje brakujące (upsert po date+ticker),
  więc pominięty dzień sam się uzupełni przy następnym uruchomieniu
- bezpieczne do wielokrotnego uruchamiania (nie duplikuje wierszy)
- pomija dzisiejszą świecę, jeśli sesja jeszcze trwa
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

# Lista WIG20 skopiowana z backend/data_fetcher.py, plus MRB.WA (używany w parze BDX/MRB)
# i NVT.WA (portfel). Gdy zmienisz skład w data_fetcher.py, zmień go też tutaj.
TICKERS = [
    "ALE.WA", "ALR.WA", "BDX.WA", "CDR.WA", "CPS.WA",
    "DNP.WA", "JSW.WA", "KGH.WA", "KRU.WA", "KTY.WA",
    "LPP.WA", "MBK.WA", "OPL.WA", "PEO.WA", "PGE.WA",
    "PKN.WA", "PKO.WA", "PZU.WA", "BHW.WA", "PCO.WA",
    "MRB.WA", "NVT.WA",
]

# skrypt leży w backend/, a CSV ląduje w data/ w głównym folderze repo
OUT = Path(__file__).resolve().parent.parent / "data" / "daily_prices.csv"
COLS = ["date", "ticker", "open", "high", "low", "close", "volume"]


def _skip_unfinished(df: pd.DataFrame) -> pd.DataFrame:
    """Pomija dzisiejszą świecę, jeśli sesja jeszcze się nie skończyła (niepełny wolumen i kurs).
    GPW zamyka się ok. 17:05 czasu lokalnego, czyli najpóźniej 16:05 UTC - bierzemy zapas do 16:15."""
    df = df[df["Volume"].fillna(0) > 0]
    now = datetime.now(timezone.utc)
    if now.hour < 16 or (now.hour == 16 and now.minute < 15):
           return df[pd.to_datetime(df.index).strftime("%Y-%m-%d") != now.strftime("%Y-%m-%d")]
    return df


def fetch(period: str = "10d") -> pd.DataFrame:
    raw = yf.download(
        TICKERS, period=period, interval="1d",
        group_by="ticker", auto_adjust=False, progress=False, threads=True,
    )
    rows = []
    for t in TICKERS:
        try:
            df = _skip_unfinished(raw[t].dropna(subset=["Close"]))
        except KeyError:
            print(f"Brak danych: {t}")
            continue
        for idx, r in df.iterrows():
            rows.append({
                "date": idx.strftime("%Y-%m-%d"),
                "ticker": t,
                "open": round(float(r["Open"]), 4),
                "high": round(float(r["High"]), 4),
                "low": round(float(r["Low"]), 4),
                "close": round(float(r["Close"]), 4),
                "volume": int(r["Volume"]) if pd.notna(r["Volume"]) else 0,
            })
    return pd.DataFrame(rows, columns=COLS)


def main() -> int:
    # jednorazowo: python backend/daily_snapshot.py --backfill  (6 miesięcy historii)
    new = fetch("6mo" if "--backfill" in sys.argv else "10d")
    if new.empty:
        print("Nie pobrano żadnych danych - przerywam bez zmian.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        old = pd.read_csv(OUT)
        all_df = pd.concat([old, new], ignore_index=True)
    else:
        all_df = new

    # nowsze dane nadpisują starsze dla tej samej pary (date, ticker)
    all_df = (
        all_df.drop_duplicates(subset=["date", "ticker"], keep="last")
        .sort_values(["date", "ticker"])
        .reset_index(drop=True)
    )
    all_df.to_csv(OUT, index=False)

    n_days = all_df["date"].nunique()
    last = all_df["date"].max()
    print(f"OK: {len(all_df)} wierszy, {n_days} dni, ostatni dzień: {last}")
    return 0


if __name__ == "__main__":
    sys.exit(main())