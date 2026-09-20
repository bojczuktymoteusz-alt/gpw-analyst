import sqlite3
import json
from datetime import datetime

DB_NAME = "gpw_data.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS stocks
                 (ticker TEXT PRIMARY KEY,
                  price REAL, pe REAL, pbv REAL, roe REAL, div_yield REAL,
                  last_updated TIMESTAMP, name TEXT, recommendation TEXT,
                  market_cap REAL, beta REAL, sector TEXT,
                  operating_margin REAL, ebitda REAL, total_debt REAL,
                  total_cash REAL, payout_ratio REAL, debt_to_equity REAL,
                  trailing_div_yield REAL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS price_history
                 (id      INTEGER PRIMARY KEY AUTOINCREMENT,
                  ticker  TEXT NOT NULL,
                  date    TEXT NOT NULL,
                  close   REAL NOT NULL,
                  volume  INTEGER DEFAULT 0,
                  UNIQUE(ticker, date))''')

    c.execute("CREATE INDEX IF NOT EXISTS idx_history_ticker_date ON price_history(ticker, date)")

    c.execute('''CREATE TABLE IF NOT EXISTS arbitrage_signals
                 (pair        TEXT PRIMARY KEY,
                  signal      TEXT NOT NULL,
                  zscore      REAL,
                  updated_at  TIMESTAMP)''')

    # ── NOWE: tabela snapshots ────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS snapshots
                 (id             INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp      TEXT NOT NULL,
                  snapshot_type  TEXT NOT NULL,
                  ticker         TEXT,
                  pair_name      TEXT,
                  data_json      TEXT NOT NULL)''')

    c.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_ticker ON snapshots(ticker)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_pair ON snapshots(pair_name)")
    # ─────────────────────────────────────────────────────────────────

    conn.commit()
    conn.close()


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def clear_price_history(tickers: list = None):
    conn = sqlite3.connect(DB_NAME)
    if tickers:
        placeholders = ",".join("?" * len(tickers))
        conn.execute(
            f"DELETE FROM price_history WHERE ticker IN ({placeholders})",
            tickers
        )
        print(f"[DB] Wyczyszczono price_history dla: {tickers}")
    else:
        conn.execute("DELETE FROM price_history")
        print("[DB] Wyczyszczono całą tabelę price_history (reset Adj Close)")
    conn.commit()
    conn.close()


# ── NOWE: archiwizacja snapshots ──────────────────────────────────────

def save_snapshot(snapshot_type: str, data: dict,
                  ticker: str = None, pair_name: str = None):
    """Zapisuje jeden snapshot do tabeli snapshots."""
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        """INSERT INTO snapshots (timestamp, snapshot_type, ticker, pair_name, data_json)
           VALUES (?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), snapshot_type, ticker, pair_name, json.dumps(data))
    )
    conn.commit()
    conn.close()


def get_latest_snapshots(snapshot_type: str, limit_per_key: int = 1) -> list:
    """Zwraca najnowsze snapshoty danego typu – dla endpointu agenta."""
    conn = get_db_connection()
    rows = conn.execute(
        """SELECT * FROM snapshots
           WHERE snapshot_type = ?
           AND timestamp = (
               SELECT MAX(timestamp) FROM snapshots
               WHERE snapshot_type = ?
           )""",
        (snapshot_type, snapshot_type)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]