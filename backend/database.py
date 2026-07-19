import sqlite3

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

    # Tabela pamięci sygnałów arbitrażu – przetrwuje restart backendu
    c.execute('''CREATE TABLE IF NOT EXISTS arbitrage_signals
                 (pair        TEXT PRIMARY KEY,
                  signal      TEXT NOT NULL,
                  zscore      REAL,
                  updated_at  TIMESTAMP)''')

    conn.commit()
    conn.close()


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def clear_price_history(tickers: list = None):
    """
    Czyści price_history przy starcie – usuwa nieskorygowane ceny
    (np. po odcięciu dywidendy przed przejściem na Adj Close).
    tickers=None → czyści całą tabelę.
    tickers=['PKO.WA','PEO.WA'] → czyści tylko podane.
    """
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