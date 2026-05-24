import sqlite3

DB_NAME = "gpw_data.db"

def init_db():
    """Initialize the database with the full schema.
    Uses ADD COLUMN migrations for backward compatibility with existing DBs.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Create table with full schema (new installs)
    c.execute('''CREATE TABLE IF NOT EXISTS stocks (
                    ticker          TEXT PRIMARY KEY,
                    name            TEXT,
                    price           REAL,
                    pe              REAL,
                    pbv             REAL,
                    roe             REAL,
                    div_yield       REAL,
                    operating_margin REAL,
                    ebitda          REAL,
                    total_debt      REAL,
                    total_cash      REAL,
                    recommendation  TEXT,
                    market_cap      REAL,
                    beta            REAL,
                    sector          TEXT,
                    last_updated    TIMESTAMP
                 )''')

    # Migrations: add any columns missing from older DB files
    c.execute("PRAGMA table_info(stocks)")
    existing_columns = {col[1] for col in c.fetchall()}

    migrations = {
        'name':             'ALTER TABLE stocks ADD COLUMN name TEXT',
        'recommendation':   'ALTER TABLE stocks ADD COLUMN recommendation TEXT',
        'market_cap':       'ALTER TABLE stocks ADD COLUMN market_cap REAL',
        'beta':             'ALTER TABLE stocks ADD COLUMN beta REAL',
        'sector':           'ALTER TABLE stocks ADD COLUMN sector TEXT',
        'operating_margin': 'ALTER TABLE stocks ADD COLUMN operating_margin REAL',
        'ebitda':           'ALTER TABLE stocks ADD COLUMN ebitda REAL',
        'total_debt':       'ALTER TABLE stocks ADD COLUMN total_debt REAL',
        'total_cash':       'ALTER TABLE stocks ADD COLUMN total_cash REAL',
    }

    for col, sql in migrations.items():
        if col not in existing_columns:
            print(f"DB migration: adding column '{col}'...")
            c.execute(sql)

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn
