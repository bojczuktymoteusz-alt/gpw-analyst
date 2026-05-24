import yfinance as yf
import pandas as pd
import time
import random
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
from database import get_db_connection, init_db

# BUG FIX: Removed unused imports: sqlite3, ThreadPoolExecutor

# Pełna lista WIG20
TICKERS = [
    "ALE.WA", "ALR.WA", "BDX.WA", "CDR.WA", "CPS.WA",
    "DNP.WA", "JSW.WA", "KGH.WA", "KRU.WA", "KTY.WA",
    "LPP.WA", "MBK.WA", "OPL.WA", "PEO.WA", "PGE.WA",
    "ORL.WA", "PKO.WA", "PZU.WA", "SPL.WA", "PCO.WA"
]

# BUG FIX: Moved name_map to module level - no reason to rebuild it on every call
NAME_MAP = {
    "ALE.WA": "Allegro",
    "ALR.WA": "Alior Bank",
    "BDX.WA": "Budimex",
    "CDR.WA": "CD Projekt",
    "CPS.WA": "Cyfrowy Polsat",
    "DNP.WA": "Dino Polska",
    "JSW.WA": "JSW",
    "KGH.WA": "KGHM",
    "KRU.WA": "Kruk",
    "KTY.WA": "Grupa Kęty",
    "LPP.WA": "LPP",
    "MBK.WA": "mBank",
    "OPL.WA": "Orange Polska",
    "PEO.WA": "Bank Pekao",
    "PGE.WA": "PGE",
    "ORL.WA": "Orlen",
    "PKO.WA": "PKO BP",
    "PZU.WA": "PZU",
    "SPL.WA": "Santander",
    "PCO.WA": "Pepco",
}

# Cache TTL for live data (1 hour)
CACHE_TTL_HOURS = 1


def _safe_float(value, default=0.0):
    """Safely convert a value to float, returning default on failure."""
    try:
        if value is None:
            return default
        result = float(value)
        # Guard against NaN/Inf that would break JSON serialisation
        if not np.isfinite(result):
            return default
        return result
    except (ValueError, TypeError):
        return default


def fetch_single_ticker(ticker: str) -> dict | None:
    """Fetch a single ticker from yFinance. Returns a dict or None on failure."""
    try:
        print(f"Fetching {ticker} from yfinance...")
        stock = yf.Ticker(ticker)
        info = stock.info

        # BUG FIX: yfinance always returns a dict (never None/empty), but it may
        # contain only {'trailingPegRatio': None} when the symbol is invalid.
        # Check for a meaningful field instead of truthiness of the dict.
        if not info or 'regularMarketPrice' not in info and 'currentPrice' not in info and 'previousClose' not in info:
            print(f"No useful info returned for {ticker}")
            return None

        price = (
            info.get('currentPrice')
            or info.get('regularMarketPrice')
            or info.get('previousClose')
            or 0
        )
        name = NAME_MAP.get(ticker, info.get('shortName') or ticker.split('.')[0])
        recommendation = info.get('recommendationKey') or 'none'

        div_yield = _safe_float(info.get('dividendYield'))
        # yFinance sometimes returns e.g. 4.5 instead of 0.045
        if div_yield > 0.5:
            div_yield /= 100.0

        roe = _safe_float(info.get('returnOnEquity'))

        # Fallback: calculate ROE manually when yFinance doesn't provide it
        if roe == 0.0:
            try:
                print(f"ROE missing for {ticker}, attempting manual calculation...")
                financials = stock.financials
                balance_sheet = stock.balance_sheet
                if not financials.empty and not balance_sheet.empty:
                    if (
                        'Net Income' in financials.index
                        and 'Stockholders Equity' in balance_sheet.index
                    ):
                        net_income = financials.loc['Net Income'].iloc[0]
                        equity = balance_sheet.loc['Stockholders Equity'].iloc[0]
                        if equity and equity != 0:
                            roe = _safe_float(net_income / equity)
                            print(f"Calculated ROE for {ticker}: {roe:.4f}")
            except Exception as e:
                print(f"Failed to calculate ROE for {ticker}: {e}")

        return {
            'ticker':           ticker,
            'name':             name,
            'price':            _safe_float(price),
            'pe':               _safe_float(info.get('trailingPE')),
            'pbv':              _safe_float(info.get('priceToBook')),
            'roe':              roe,
            'div_yield':        div_yield,
            'operating_margin': _safe_float(info.get('operatingMargins')),
            'ebitda':           _safe_float(info.get('ebitda')),
            'total_debt':       _safe_float(info.get('totalDebt')),
            'total_cash':       _safe_float(info.get('totalCash')),
            'recommendation':   str(recommendation),
            'market_cap':       _safe_float(info.get('marketCap')),
            'beta':             _safe_float(info.get('beta')),
            'sector':           info.get('sector') or 'Unknown',
            'last_updated':     datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


def _needs_update(row) -> bool:
    """Return True if the cached DB row is stale or incomplete."""
    if row is None:
        return True
    keys = row.keys()
    # BUG FIX: check all required fields, not just a subset
    required = ('name', 'recommendation', 'market_cap', 'sector', 'operating_margin', 'ebitda')
    for field in required:
        if field not in keys:
            return True
        val = row[field]
        if val is None or val == '' or val == 'None':
            return True
    try:
        last_updated = datetime.fromisoformat(row['last_updated'])
        return datetime.now() - last_updated >= timedelta(hours=CACHE_TTL_HOURS)
    except (TypeError, ValueError):
        return True


def get_all_stocks() -> list[dict]:
    init_db()

    results = []
    tickers_to_fetch = []

    # --- Pass 1: read cache ---
    conn = get_db_connection()
    # BUG FIX: use a single query instead of 20 individual queries inside a loop
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stocks WHERE ticker IN (%s)"
                   % ','.join('?' * len(TICKERS)), TICKERS)
    cached = {row['ticker']: row for row in cursor.fetchall()}
    conn.close()

    for ticker in TICKERS:
        row = cached.get(ticker)
        if _needs_update(row):
            tickers_to_fetch.append(ticker)
        else:
            results.append(dict(row))

    # --- Pass 2: fetch stale / missing tickers ---
    if tickers_to_fetch:
        print(f"Fetching {len(tickers_to_fetch)} tickers from yFinance (rate-limited)...")
        conn = get_db_connection()
        for i, ticker in enumerate(tickers_to_fetch):
            data = fetch_single_ticker(ticker)
            if data:
                conn.execute(
                    """INSERT OR REPLACE INTO stocks
                       (ticker, name, price, pe, pbv, roe, div_yield,
                        operating_margin, ebitda, total_debt, total_cash,
                        recommendation, market_cap, beta, sector, last_updated)
                       VALUES
                       (:ticker, :name, :price, :pe, :pbv, :roe, :div_yield,
                        :operating_margin, :ebitda, :total_debt, :total_cash,
                        :recommendation, :market_cap, :beta, :sector, :last_updated)""",
                    data,
                )
                conn.commit()
                results.append(data)

            # BUG FIX: sleep only between requests, not after the last one
            if i < len(tickers_to_fetch) - 1:
                delay = random.uniform(3, 6)
                print(f"  Waiting {delay:.1f}s before next request...")
                time.sleep(delay)

        conn.close()

    # --- Pass 3: compute sector averages and attach to results ---
    sector_pe_map: dict[str, list[float]] = {}
    sector_margin_map: dict[str, list[float]] = {}

    for res in results:
        sector = res.get('sector') or 'Unknown'
        pe = _safe_float(res.get('pe'))
        margin = _safe_float(res.get('operating_margin'))

        if pe > 0:
            sector_pe_map.setdefault(sector, []).append(pe)
        if margin != 0:
            sector_margin_map.setdefault(sector, []).append(margin)

    sector_pe_avgs     = {s: sum(l) / len(l) for s, l in sector_pe_map.items() if l}
    sector_margin_avgs = {s: sum(l) / len(l) for s, l in sector_margin_map.items() if l}

    for res in results:
        sector = res.get('sector') or 'Unknown'
        res['sector_pe_avg']     = sector_pe_avgs.get(sector, 0)
        res['sector_margin_avg'] = sector_margin_avgs.get(sector, 0)

    results.sort(key=lambda x: x['ticker'])
    return results


def get_stock_history(ticker: str, period: str = "1y") -> list[dict]:
    interval_map = {
        "1d":  "5m",
        "5d":  "15m",
        "1mo": "1d",
        "6mo": "1d",
        "ytd": "1d",
        "1y":  "1d",
        "5y":  "1wk",
    }
    interval = interval_map.get(period, "1d")
    print(f"Fetching history for {ticker}: period={period}, interval={interval}")

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period, interval=interval)

        if hist.empty:
            print(f"Warning: No history data found for {ticker}")
            return []

        hist.reset_index(inplace=True)
        date_col = 'Datetime' if 'Datetime' in hist.columns else 'Date'
        hist[date_col] = pd.to_datetime(hist[date_col], utc=True)

        fmt = '%Y-%m-%d %H:%M' if interval in ('5m', '15m', '1h') else '%Y-%m-%d'
        hist['date'] = hist[date_col].dt.strftime(fmt)

        # BUG FIX: rename before selecting to avoid KeyError when 'close' doesn't exist yet
        hist.rename(columns={'Close': 'close'}, inplace=True)

        # BUG FIX: drop NaN close values that would corrupt the chart
        hist.dropna(subset=['close'], inplace=True)

        return hist[['date', 'close']].to_dict(orient='records')

    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}")
        return []


def predict_stock_price(ticker: str, forecast_days: int = 7) -> dict | None:
    """Simple linear regression price prediction."""
    print(f"Generating prediction for {ticker}...")
    try:
        history = get_stock_history(ticker, period="6mo")
        if not history or len(history) < 10:
            print(f"Not enough history for {ticker} to predict.")
            return None

        df = pd.DataFrame(history)
        df['date'] = pd.to_datetime(df['date'])
        df['day_index'] = range(len(df))

        X = df[['day_index']].values
        y = df['close'].values

        model = LinearRegression()
        model.fit(X, y)

        current_price = float(y[-1])
        future_index = len(df) + forecast_days
        predicted_price = float(model.predict([[future_index]])[0])

        trend_pct = ((predicted_price - current_price) / current_price) * 100
        trend = "up" if trend_pct > 0.5 else "down" if trend_pct < -0.5 else "neutral"

        return {
            "ticker":          ticker,
            "current_price":   round(current_price,   2),
            "predicted_price": round(predicted_price, 2),
            "trend_pct":       round(trend_pct,       2),
            "trend":           trend,
            "forecast_days":   forecast_days,
        }

    except Exception as e:
        print(f"Error in prediction for {ticker}: {e}")
        return None


if __name__ == "__main__":
    print("🚀 Pobieranie danych z GPW...")
    get_all_stocks()
    print("✅ Gotowe!")
