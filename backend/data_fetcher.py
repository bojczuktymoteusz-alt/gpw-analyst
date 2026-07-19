import yfinance as yf
import pandas as pd
import time
import sqlite3
import numpy as np
from sklearn.linear_model import LinearRegression
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from database import get_db_connection, init_db

# Pełna lista WIG20
TICKERS = [
    "ALE.WA", "ALR.WA", "BDX.WA", "CDR.WA", "CPS.WA",
    "DNP.WA", "JSW.WA", "KGH.WA", "KRU.WA", "KTY.WA",
    "LPP.WA", "MBK.WA", "OPL.WA", "PEO.WA", "PGE.WA",
    "PKN.WA", "PKO.WA", "PZU.WA", "SPL.WA", "PCO.WA"
]

def fetch_single_ticker(ticker):
    """Helper to fetch data from yfinance without writing to DB."""
    try:
        print(f"Fetching {ticker} from yfinance...")
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info:
             print(f"No info returned for {ticker}")
             return None

        price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0
        name = info.get('shortName') or ticker.split('.')[0]
        
        # Mapping for cleaner names WIG20
        name_map = {
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
            "PKN.WA": "Orlen",
            "PKO.WA": "PKO BP",
            "PZU.WA": "PZU",
            "SPL.WA": "Santander",
            "PCO.WA": "Pepco"
        }
        name = name_map.get(ticker, name)
            
        recommendation = info.get('recommendationKey', 'none')
            
        div_yield = info.get('dividendYield', 0)
        # Handle decimal vs percentage
        if div_yield and div_yield > 0.5:
            div_yield = div_yield / 100.0
            
        roe = info.get('returnOnEquity')
        
        # Fallback for ROE if missing in info
        if roe is None or roe == 0:
            try:
                print(f"ROE missing for {ticker}, attempting manual calculation...")
                financials = stock.financials
                balance_sheet = stock.balance_sheet
                
                if not financials.empty and not balance_sheet.empty:
                    if 'Net Income' in financials.index and 'Stockholders Equity' in balance_sheet.index:
                        net_income = financials.loc['Net Income'].iloc[0]
                        equity = balance_sheet.loc['Stockholders Equity'].iloc[0]
                        
                        if equity and equity != 0:
                            roe = net_income / equity
                            print(f"Calculated ROE for {ticker}: {roe}")
            except Exception as e:
                print(f"Failed to calculate ROE for {ticker}: {e}")

        # Nowe wskaźniki do scoringu jakości
        payout_ratio = info.get('payoutRatio')
        debt_to_equity = info.get('debtToEquity')
        trailing_div_yield = info.get('trailingAnnualDividendYield')

        # Fallback dla payout_ratio - oblicz z dywidendy i EPS jesli brak
        if payout_ratio is None or payout_ratio == 0:
            try:
                div_per_share = info.get('dividendRate') or info.get('trailingAnnualDividendRate') or 0
                eps = info.get('trailingEps') or 0
                if div_per_share and eps and eps > 0:
                    payout_ratio = div_per_share / eps
            except Exception:
                pass

        # Fallback dla trailing_div_yield - uzyj dividendYield jesli brak
        if trailing_div_yield is None or trailing_div_yield == 0:
            trailing_div_yield = info.get('dividendYield') or 0
            if trailing_div_yield and trailing_div_yield > 0.5:
                trailing_div_yield = trailing_div_yield / 100.0

        return {
            'ticker': ticker,
            'name': name,
            'price': float(price) if price else 0.0,
            'pe': float(info.get('trailingPE', 0)) if info.get('trailingPE') else 0.0,
            'pbv': float(info.get('priceToBook', 0)) if info.get('priceToBook') else 0.0,
            'roe': float(roe) if roe else 0.0,
            'div_yield': float(div_yield) if div_yield else 0.0,
            'operating_margin': float(info.get('operatingMargins', 0)) if info.get('operatingMargins') else 0.0,
            'ebitda': float(info.get('ebitda', 0)) if info.get('ebitda') else 0.0,
            'total_debt': float(info.get('totalDebt', 0)) if info.get('totalDebt') else 0.0,
            'total_cash': float(info.get('totalCash', 0)) if info.get('totalCash') else 0.0,
            'recommendation': str(recommendation),
            'market_cap': float(info.get('marketCap', 0)) if info.get('marketCap') else 0.0,
            'beta': float(info.get('beta', 0)) if info.get('beta') else 0.0,
            'sector': info.get('sector', 'Unknown'),
            'payout_ratio': float(payout_ratio) if payout_ratio is not None else None,
            'debt_to_equity': float(debt_to_equity) if debt_to_equity is not None else None,
            'trailing_div_yield': float(trailing_div_yield) if trailing_div_yield is not None else None,
            'last_updated': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def get_all_stocks():
    results = []
    tickers_to_fetch = []
    
    init_db()
    
    conn = get_db_connection()
    for ticker in TICKERS:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        
        needs_update = True
        if row:
            try:
                if not row['name'] or not row['recommendation'] or row['recommendation'] == 'None' or row['market_cap'] is None or not row['sector'] or 'operating_margin' not in row.keys() or row['operating_margin'] is None or row['ebitda'] is None:
                    needs_update = True
                else:
                    last_updated = datetime.fromisoformat(row['last_updated'])
                    if datetime.now() - last_updated < timedelta(hours=1):
                        needs_update = False
                        results.append(dict(row))
            except (IndexError, KeyError):
                needs_update = True
        
        if needs_update:
            tickers_to_fetch.append(ticker)
    conn.close()

    if tickers_to_fetch:
        print(f"Sequential fetching {len(tickers_to_fetch)} tickers with 2s sleep...")
        
        conn = get_db_connection()
        for ticker in tickers_to_fetch:
            data = fetch_single_ticker(ticker)
            if data:
                conn.execute("""INSERT OR REPLACE INTO stocks (ticker, name, price, pe, pbv, roe, div_yield, operating_margin, ebitda, total_debt, total_cash, recommendation, market_cap, beta, sector, payout_ratio, debt_to_equity, trailing_div_yield, last_updated) 
                                VALUES (:ticker, :name, :price, :pe, :pbv, :roe, :div_yield, :operating_margin, :ebitda, :total_debt, :total_cash, :recommendation, :market_cap, :beta, :sector, :payout_ratio, :debt_to_equity, :trailing_div_yield, :last_updated)""", data)
                results.append(data)
                conn.commit()  # Commit after each ticker to ensure data is saved
                print(f"Waiting 2 seconds before next request...")
                import random
                time.sleep(random.uniform(3, 6))
        conn.close()

    sector_pe_map = {}
    sector_margin_map = {}
    for res in results:
        sector = res.get('sector', 'Unknown')
        try:
            pe = float(res.get('pe', 0))
        except (ValueError, TypeError):
            pe = 0.0
            
        try:
            margin = float(res.get('operating_margin', 0))
        except (ValueError, TypeError):
            margin = 0.0
        
        if pe > 0:
            if sector not in sector_pe_map:
                sector_pe_map[sector] = []
            sector_pe_map[sector].append(pe)
            
        if margin != 0:
            if sector not in sector_margin_map:
                sector_margin_map[sector] = []
            sector_margin_map[sector].append(margin)
    
    sector_pe_avgs = {s: sum(l)/len(l) for s, l in sector_pe_map.items() if l}
    sector_margin_avgs = {s: sum(l)/len(l) for s, l in sector_margin_map.items() if l}

    for res in results:
        res['sector_pe_avg'] = sector_pe_avgs.get(res.get('sector'), 0)
        res['sector_margin_avg'] = sector_margin_avgs.get(res.get('sector'), 0)

    results.sort(key=lambda x: x['ticker'])
    return results

def get_stock_history(ticker, period="1y"):
    interval_map = {
        "1d": "5m",
        "5d": "15m",
        "1mo": "1d",
        "6mo": "1d",
        "ytd": "1d",
        "1y": "1d",
        "5y": "1wk"
    }
    interval = interval_map.get(period, "1d")
    print(f"Fetching history for {ticker} with period={period}, interval={interval}")
    
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period, interval=interval)
        
        if hist.empty:
            print(f"Warning: No data found for {ticker}")
            return []
            
        hist.reset_index(inplace=True)
        date_col = 'Datetime' if 'Datetime' in hist.columns else 'Date'
        
        # FIX: Ensure dates are timezone-aware and formatted safely
        hist[date_col] = pd.to_datetime(hist[date_col], utc=True)
        
        if interval in ['5m', '15m', '1h']:
            hist['date'] = hist[date_col].dt.strftime('%Y-%m-%d %H:%M')
        else:
            hist['date'] = hist[date_col].dt.strftime('%Y-%m-%d')
             
        hist = hist.rename(columns={'Close': 'close'})
        result = hist[['date', 'close']].to_dict(orient='records')
        return result
    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}")
        return []

def predict_stock_price(ticker, forecast_days=7):
    print(f"Generating AI Prediction for {ticker}...")
    try:
        history = get_stock_history(ticker, period="6mo")
        if not history or len(history) < 10:
            return None
        
        df = pd.DataFrame(history)
        df['date'] = pd.to_datetime(df['date'])
        df['day_index'] = range(len(df))
        
        X = df[['day_index']].values
        y = df['close'].values
        
        model = LinearRegression()
        model.fit(X, y)
        
        current_price = float(y[-1])
        future_day_index = len(df) + forecast_days
        
        # Zabezpieczenie przed warningami ze scikit-learn
        predicted_price = float(model.predict(np.array([[future_day_index]]))[0])
        
        trend_pct = ((predicted_price - current_price) / current_price) * 100
        trend = "up" if trend_pct > 0.5 else "down" if trend_pct < -0.5 else "neutral"
        
        return {
            "ticker": ticker,
            "current_price": float(f"{current_price:.2f}"),
            "predicted_price": float(f"{predicted_price:.2f}"),
            "trend_pct": float(f"{trend_pct:.2f}"),
            "trend": trend,
            "forecast_days": forecast_days
        }
    except Exception as e:
        print(f"Error in prediction for {ticker}: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Rozpoczynam pobieranie danych z GPW...")
    get_all_stocks()
    print("✅ Gotowe! Dane wysłane do bazy.")


# ══════════════════════════════════════════════════════════════════
# MODUŁ ARBITRAŻU STATYSTYCZNEGO (Z-Score)
# ══════════════════════════════════════════════════════════════════
#
# Aby dodać nową parę: dopisz słownik do listy ARBITRAGE_PAIRS.
# Reszta (Z-Score, alerty Discord, endpoint /api/arbitrage) działa
# automatycznie bez żadnych innych zmian w kodzie.

import threading
import requests
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
DISCORD_ARBITRAGE_WEBHOOK = os.environ.get("DISCORD_ARBITRAGE_WEBHOOK", "")
GMAIL_FROM = os.environ.get("GMAIL_FROM", "")
GMAIL_TO = os.environ.get("GMAIL_TO", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

# ── Gmail alert ───────────────────────────────────────────────────
GMAIL_USER     = os.environ.get("GMAIL_USER", "bojczuktymoteusz@gmail.com")
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_TO       = os.environ.get("GMAIL_TO", "bojczuktymoteusz@gmail.com")

# ── Konfiguracja par ──────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════
# KONFIGURACJA PAR ARBITRAŻOWYCH
# Aby dodać parę: odkomentuj lub dopisz nowy słownik.
# Parametry:
#   name          – etykieta wyświetlana w UI i na Discordzie
#   ticker_a/b    – symbole yFinance (z sufiksem .WA dla GPW)
#   label_a/b     – czytelne nazwy spółek
#   lookback_days – okno historyczne do liczenia SMA i std (dni)
#   z_threshold   – próg Z-Score wyzwalający alert Discord (zwykle 2.0)
# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
# KONFIGURACJA PAR ARBITRAŻOWYCH
# Kryterium doboru: podobny makro driver + różna jakość/beta
# (nie "identyczny sektor" – to zabija spread opportunities)
# ══════════════════════════════════════════════════════════════════

ARBITRAGE_PAIRS = [

    # ── BANKI CORE (⭐⭐⭐⭐⭐) ──────────────────────────────────────
    {
        "name": "PKO/PEO", "ticker_a": "PKO.WA", "ticker_b": "PEO.WA",
        "label_a": "PKO BP", "label_b": "Bank Pekao",
        "lookback_days": 30, "z_threshold": 2.0,
    },
    {
        "name": "PKO/SPL", "ticker_a": "PKO.WA", "ticker_b": "SPL.WA",
        "label_a": "PKO BP", "label_b": "Santander PL",
        "lookback_days": 30, "z_threshold": 2.0,
    },

    # ── BANKI JAKOŚĆ vs RYZYKO (⭐⭐⭐⭐) ───────────────────────────
    {
        "name": "PKO/ALR", "ticker_a": "PKO.WA", "ticker_b": "ALR.WA",
        "label_a": "PKO BP", "label_b": "Alior Bank",
        "lookback_days": 30, "z_threshold": 2.0,
    },
    {
        "name": "PEO/MBK", "ticker_a": "PEO.WA", "ticker_b": "MBK.WA",
        "label_a": "Bank Pekao", "label_b": "mBank",
        "lookback_days": 30, "z_threshold": 2.0,
    },

    # ── SUROWCE GLOBALNE (⭐⭐⭐⭐) ─────────────────────────────────
    # Driver: ceny metali/surowców, eksport, Chiny
    {
        "name": "KGH/JSW", "ticker_a": "KGH.WA", "ticker_b": "JSW.WA",
        "label_a": "KGHM", "label_b": "JSW",
        "lookback_days": 30, "z_threshold": 2.0,
    },

    # ── ENERGIA + REGULACJE (⭐⭐⭐⭐) ──────────────────────────────
    # Driver: ceny energii, polityka energetyczna PL
    {
        "name": "PKN/PGE", "ticker_a": "PKN.WA", "ticker_b": "PGE.WA",
        "label_a": "Orlen", "label_b": "PGE",
        "lookback_days": 30, "z_threshold": 2.0,
    },

    # ── CONSUMER DEFENSYWNY (⭐⭐⭐⭐) ──────────────────────────────
    # Driver: konsumpcja PL, inflacja, siła nabywcza
    {
        "name": "DNP/CPS", "ticker_a": "DNP.WA", "ticker_b": "CPS.WA",
        "label_a": "Dino Polska", "label_b": "Cyfrowy Polsat",
        "lookback_days": 30, "z_threshold": 2.0,
    },

    # ── BUDOWNICTWO (⭐⭐⭐⭐) ──────────────────────────────────────
    # Driver: przetargi publiczne, ceny materiałów, fundusze UE
    {
        "name": "BDX/MRB", "ticker_a": "BDX.WA", "ticker_b": "MRB.WA",
        "label_a": "Budimex", "label_b": "Mirbud",
        "lookback_days": 30, "z_threshold": 2.0,
    },

    # ── FINANSE MIESZANE (neutralne) ──────────────────────────────
    {
        "name": "PZU/PEO", "ticker_a": "PZU.WA", "ticker_b": "PEO.WA",
        "label_a": "PZU", "label_b": "Bank Pekao",
        "lookback_days": 30, "z_threshold": 2.0,
    },

    # ── DO OBSERWACJI (słabsze, ale monitorujemy) ─────────────────
    # CDR/ALE – słaby spread historyczny, zostawiamy do obserwacji
    # {
    #     "name": "CDR/ALE", "ticker_a": "CDR.WA", "ticker_b": "ALE.WA",
    #     "label_a": "CD Projekt", "label_b": "Allegro",
    #     "lookback_days": 30, "z_threshold": 2.0,
    # },
    # LPP/ALE – lepiej LPP/CCC gdy CCC wróci do WIG20
    # {
    #     "name": "LPP/ALE", "ticker_a": "LPP.WA", "ticker_b": "ALE.WA",
    #     "label_a": "LPP", "label_b": "Allegro",
    #     "lookback_days": 30, "z_threshold": 2.0,
    # },

]

# Cooldown alertów: nie wysyłaj ponownie tej samej pary przez 60 min
_alert_cooldown = {}
ALERT_COOLDOWN_MIN = 60

# Pamięć ostatniego sygnału per para – persystowana w SQLite
_last_signal: dict = {}  # pair → ostatni signal (cache w pamięci)


def _load_signals_from_db():
    """Wczytuje ostatnie sygnały z SQLite przy starcie."""
    global _last_signal
    try:
        conn = get_db_connection()
        rows = conn.execute("SELECT pair, signal FROM arbitrage_signals").fetchall()
        conn.close()
        _last_signal = {r["pair"]: r["signal"] for r in rows}
        if _last_signal:
            print(f"[Arbitraż] Wczytano {len(_last_signal)} sygnałów z DB: {list(_last_signal.items())}")
    except Exception as e:
        print(f"[Arbitraż] Błąd wczytywania sygnałów: {e}")


def _save_signal_to_db(pair: str, signal: str, zscore: float):
    """Zapisuje sygnał do SQLite."""
    try:
        conn = get_db_connection()
        conn.execute(
            "INSERT OR REPLACE INTO arbitrage_signals (pair, signal, zscore, updated_at) VALUES (?, ?, ?, ?)",
            (pair, signal, zscore, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Arbitraż] Błąd zapisu sygnału {pair}: {e}")

# Cache danych – wypełniany jednym bulk download dla wszystkich tickerów
_bulk_cache: dict = {}   # ticker → pd.Series (Adj Close dzienny)


def _bulk_download_all(lookback_days: int = 35) -> None:
    """
    Pobiera dane dla WSZYSTKICH unikalnych tickerów ze wszystkich par
    jednym zapytaniem yf.download() – drastycznie szybsze niż pętla.
    Wynik trafia do _bulk_cache.
    """
    global _bulk_cache
    unique = list({
        t for pair in ARBITRAGE_PAIRS
        for t in (pair["ticker_a"], pair["ticker_b"])
    })
    tickers_str = " ".join(unique)
    print(f"[Arbitrage] Bulk download {len(unique)} tickerów: {unique}")

    try:
        raw = yf.download(
            tickers=tickers_str,
            period=f"{lookback_days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if raw.empty:
            print("[Arbitrage] Bulk download zwrócił pusty DataFrame")
            return

        # yf.download zwraca MultiIndex (metric, ticker) gdy >1 ticker
        # Dla pojedynczego tickera – flat columns
        new_cache = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in unique:
                try:
                    series = raw["Close"][ticker].copy()
                    series = series.ffill().bfill().dropna()
                    series = series[series > 0]
                    if not series.empty:
                        new_cache[ticker] = series
                        print(f"[Arbitrage] {ticker}: {len(series)} sesji (bulk)")
                except Exception as e:
                    print(f"[Arbitrage] {ticker}: błąd ekstrakcji – {e}")
        else:
            # Pojedynczy ticker (fallback)
            ticker = unique[0]
            series = raw["Close"].copy().ffill().bfill().dropna()
            series = series[series > 0]
            if not series.empty:
                new_cache[ticker] = series

        _bulk_cache = new_cache
        print(f"[Arbitrage] Bulk cache gotowy: {len(_bulk_cache)}/{len(unique)} tickerów")

    except Exception as e:
        print(f"[Arbitrage] Błąd bulk download: {e}")


def _get_closes(ticker: str) -> pd.Series:
    """Zwraca serię z cache. Jeśli brak – próbuje pobrać indywidualnie."""
    if ticker in _bulk_cache:
        return _bulk_cache[ticker]
    # Fallback: pojedynczy ticker
    print(f"[Arbitrage] {ticker} nie w cache – pobieranie indywidualne")
    try:
        df = yf.Ticker(ticker).history(period="35d", interval="1d", auto_adjust=True)
        if df.empty:
            return pd.Series(dtype=float)
        s = df["Close"].ffill().bfill().dropna()
        return s[s > 0]
    except Exception as e:
        print(f"[Arbitrage] Fallback błąd {ticker}: {e}")
        return pd.Series(dtype=float)


def compute_zscore(pair, preloaded: bool = False):
    """
    Oblicza Z-Score spreadu dla jednej pary.
    Jeśli preloaded=True, korzysta z _bulk_cache (szybko).
    Jeśli preloaded=False, pobiera dane indywidualnie (wolno).

    Wzory:
      spread  = ln(cena_A) - ln(cena_B)  [log-spread, normalizuje skalę cen]
      SMA     = srednia spreadu z lookback_days sesji
      std     = odchylenie std spreadu z lookback_days sesji
      Z-Score = (spread_biezacy - SMA) / std
    """
    ta = pair["ticker_a"]
    tb = pair["ticker_b"]
    lb = pair["lookback_days"]

    if preloaded:
        closes_a = _get_closes(ta)
        closes_b = _get_closes(tb)
    else:
        closes_a = _get_closes(ta)
        closes_b = _get_closes(tb)

    if closes_a.empty or closes_b.empty:
        print(f"[Arbitrage] Brak danych dla pary {pair['name']}")
        return None

    combined = pd.DataFrame({"a": closes_a, "b": closes_b}).dropna()
    if len(combined) < 20:
        print(f"[Arbitrage] Za mało punktów ({len(combined)}) dla {pair['name']}")
        return None

    combined["spread"] = np.log(combined["a"]) - np.log(combined["b"])

    window = lb  # lookback_days sesji dziennych
    recent = combined["spread"].iloc[-window:] if len(combined) >= window else combined["spread"]

    sma = float(recent.mean())
    std = float(recent.std())
    current_spread = float(combined["spread"].iloc[-1])

    if std == 0:
        return None

    zscore = (current_spread - sma) / std

    # ── VELOCITY (nachylenie spreadu z ostatnich 5 sesji) ─────────
    # Dodatnie = spread rośnie (rozjazd przyspiesza)
    # Ujemne  = spread maleje (rozjazd hamuje = okno wejścia 🔥)
    VELOCITY_WINDOW = 5
    vel_series = combined["spread"].iloc[-VELOCITY_WINDOW:]
    if len(vel_series) >= 2:
        x = np.arange(len(vel_series))
        slope, _, r_value, _, _ = __import__('scipy.stats', fromlist=['stats']).linregress(x, vel_series.values)
        velocity = round(float(slope), 8)       # zmiana spreadu na sesję
        velocity_r2 = round(float(r_value**2), 4)  # jakość trendu (0-1)
    else:
        velocity = 0.0
        velocity_r2 = 0.0

    # Interpretacja velocity względem kierunku Z-Score
    # Jeśli Z > 0 (spread wysoki) i velocity < 0 → spread wraca → DECELERATING 🔥
    # Jeśli Z > 0 i velocity > 0 → spread rośnie dalej → ACCELERATING ⚠️
    if abs(zscore) < 0.5:
        velocity_signal = "FLAT"
    elif zscore > 0 and velocity < 0:
        velocity_signal = "DECELERATING"   # spread wraca do średniej – dobre wejście
    elif zscore > 0 and velocity > 0:
        velocity_signal = "ACCELERATING"   # rozjazd rośnie – czekaj
    elif zscore < 0 and velocity > 0:
        velocity_signal = "DECELERATING"   # spread wraca do średniej – dobre wejście
    elif zscore < 0 and velocity < 0:
        velocity_signal = "ACCELERATING"   # rozjazd rośnie – czekaj
    else:
        velocity_signal = "FLAT"

    signal = "NEUTRAL"
    if zscore >= pair["z_threshold"]:
        signal = "SELL_A_BUY_B"
    elif zscore <= -pair["z_threshold"]:
        signal = "BUY_A_SELL_B"
    elif zscore >= pair["z_threshold"] * 0.75:
        signal = "WATCH_HIGH"
    elif zscore <= -pair["z_threshold"] * 0.75:
        signal = "WATCH_LOW"

    EXTREME_THRESHOLD = 4.5
    is_extreme = abs(zscore) >= EXTREME_THRESHOLD

    # ── ENTRY SCORE (0–100) ───────────────────────────────────────
    # Wagi: Velocity 38 | Z-Score nieliniowy 27 | R² gate+bonus 15 | Half-life regime 20

    # 1. VELOCITY (38 pkt) – najważniejszy: czy spread wraca?
    if velocity_signal == "DECELERATING":
        score_velocity = 38
    elif velocity_signal == "FLAT":
        score_velocity = 15
    else:  # ACCELERATING
        score_velocity = 0

    # 2. Z-SCORE NIELINIOWY (27 pkt)
    # |z| < 1.0 → 0 (za blisko średniej)
    # 1.0–2.0 → rośnie szybko (0→15)
    # 2.0–3.5 → plateau (15→27, peak usefulness)
    # 3.5–4.5 → spada (27→10, regime break risk)
    # > 4.5  → kara (ekstremum = potencjalny false signal)
    z_abs = abs(zscore)
    if z_abs < 1.0:
        score_zscore = 0
    elif z_abs < 2.0:
        score_zscore = int(15 * (z_abs - 1.0))          # 0→15
    elif z_abs < 3.5:
        score_zscore = int(15 + 12 * (z_abs - 2.0) / 1.5)  # 15→27
    elif z_abs < 4.5:
        score_zscore = int(27 - 17 * (z_abs - 3.5))     # 27→10
    else:
        score_zscore = 5  # kara za ekstremum

    # 3. R² VELOCITY – gate + bonus (15 pkt)
    # R² < 0.3 → blokada (sygnał velocity chaotyczny = 0)
    # 0.3–0.6 → normalny (7 pkt)
    # 0.6+   → bonus (15 pkt)
    if velocity_r2 < 0.3:
        score_r2 = 0
        r2_gate_blocked = True
    elif velocity_r2 < 0.6:
        score_r2 = 7
        r2_gate_blocked = False
    else:
        score_r2 = 15
        r2_gate_blocked = False

    # 4. HALF-LIFE REGIME FILTER (20 pkt)
    # Estymacja half-life mean reversion metodą AR(1):
    # spread[t] = rho * spread[t-1] + epsilon
    # half-life = -ln(2) / ln(rho)
    # Małe half-life (< lookback_days/2) = para w reżimie MR = pełne punkty
    # Duże half-life (> lookback_days) = para w trendzie/breakout = 0 pkt
    try:
        spread_vals = recent.values
        rho = np.corrcoef(spread_vals[:-1], spread_vals[1:])[0, 1]
        if rho > 0 and rho < 1:
            half_life = -np.log(2) / np.log(rho)
        else:
            half_life = float('inf')
    except Exception:
        half_life = float('inf')

    regime_active = half_life < lb  # para w reżimie MR jeśli HL < lookback
    if half_life < lb * 0.4:
        score_regime = 20   # szybkie mean reversion
    elif half_life < lb * 0.7:
        score_regime = 12
    elif half_life < lb:
        score_regime = 6
    else:
        score_regime = 0    # trend / breakout – brak reżimu MR

    # Całkowity score – R² gate blokuje velocity score jeśli velocity chaotyczny
    if r2_gate_blocked:
        entry_score = score_zscore + score_regime  # bez velocity i R²
    else:
        entry_score = score_velocity + score_zscore + score_r2 + score_regime

    entry_score = max(0, min(100, entry_score))

    # Etykieta decyzyjna
    if entry_score < 45:
        entry_label = "NO_TRADE"
    elif entry_score < 60:
        entry_label = "WATCH"
    elif entry_score < 75:
        entry_label = "TRADE_SMALL"
    else:
        entry_label = "FULL_ENTRY"

    return {
        "pair":             pair["name"],
        "ticker_a":         ta,
        "ticker_b":         tb,
        "label_a":          pair["label_a"],
        "label_b":          pair["label_b"],
        "price_a":          round(float(combined["a"].iloc[-1]), 2),
        "price_b":          round(float(combined["b"].iloc[-1]), 2),
        "spread":           round(current_spread, 6),
        "spread_sma":       round(sma, 6),
        "spread_std":       round(std, 6),
        "zscore":           round(zscore, 4),
        "z_threshold":      pair["z_threshold"],
        "lookback_days":    lb,
        "data_points":      len(recent),
        "signal":           signal,
        "is_extreme":       is_extreme,
        "velocity":         velocity,
        "velocity_r2":      velocity_r2,
        "velocity_signal":  velocity_signal,
        "entry_score":      entry_score,
        "entry_label":      entry_label,
        "score_velocity":   score_velocity,
        "score_zscore":     score_zscore,
        "score_r2":         score_r2,
        "score_regime":     score_regime,
        "half_life":        round(half_life, 1) if half_life != float("inf") else 999,
        "regime_active":    bool(regime_active),
        "r2_gate_blocked":  bool(r2_gate_blocked),
        "timestamp":        datetime.now().isoformat(),
    }


def get_all_arbitrage():
    """
    Pobiera dane HURTOWO jednym zapytaniem yf.download(),
    następnie liczy Z-Score dla wszystkich par z cache.
    Drastycznie szybsze niż pętla indywidualnych requestów.
    """
    max_lb = max(p["lookback_days"] for p in ARBITRAGE_PAIRS) + 5
    _bulk_download_all(lookback_days=max_lb)

    results = []
    for pair in ARBITRAGE_PAIRS:
        result = compute_zscore(pair, preloaded=True)
        if result:
            results.append(result)
            _maybe_send_discord_alert(result)

            # Sprawdź czy para wróciła do neutralnego po wcześniejszym sygnale
            pair_name = result["pair"]
            prev = _last_signal.get(pair_name)
            current = result["signal"]
            z_abs = abs(result["zscore"])

            if prev in ("BUY_A_SELL_B", "SELL_A_BUY_B") and z_abs < 1.0:
                print(f"[Arbitraż] 🏁 {pair_name} powrócił do neutralnego (Z={result['zscore']:+.4f})")
                _send_close_position_alert(result, prev)
                _last_signal[pair_name] = "NEUTRAL"
                _save_signal_to_db(pair_name, "NEUTRAL", result["zscore"])

            # Aktualizuj pamięć sygnału jeśli był aktywny
            if current in ("BUY_A_SELL_B", "SELL_A_BUY_B"):
                _last_signal[pair_name] = current
                _save_signal_to_db(pair_name, current, result["zscore"])

    return results


def _is_market_hours() -> bool:
    """
    Zwraca True tylko w godzinach aktywnej sesji GPW: 09:30-16:45.
    Alerty poza tym oknem są ignorowane (szum otwarcia/zamknięcia + noc).
    Weekendy zawsze odrzucone.
    """
    from datetime import time as dtime
    now = datetime.now()
    if now.weekday() >= 5:   # sobota=5, niedziela=6
        return False
    return dtime(9, 30) <= now.time() <= dtime(16, 45)


def _send_close_position_alert(result, previous_signal: str):
    """Wysyła alert o zamknięciu pozycji gdy Z-Score wraca do neutralnego."""
    webhook = DISCORD_ARBITRAGE_WEBHOOK if DISCORD_ARBITRAGE_WEBHOOK else DISCORD_WEBHOOK_URL
    if not webhook:
        return

    z = result["zscore"]
    ts = datetime.fromisoformat(result["timestamp"]).strftime("%d.%m.%Y %H:%M")

    if previous_signal == "BUY_A_SELL_B":
        pozycja = f"ZAMKNIJ: Sprzedaj **{result['label_a']}** / Odkup **{result['label_b']}**"
    else:
        pozycja = f"ZAMKNIJ: Odkup **{result['label_a']}** / Sprzedaj **{result['label_b']}**"

    payload = {"embeds": [{
        "title": f"🏁 ZAMKNIJ POZYCJĘ — Para {result['pair']}",
        "description": f"Z-Score powrócił do strefy neutralnej ({z:+.4f}).\n\n**{pozycja}**",
        "color": 0x5865F2,  # niebieski
        "fields": [
            {"name": f"💰 {result['label_a']}", "value": f"{result['price_a']:.2f} PLN", "inline": True},
            {"name": f"💰 {result['label_b']}", "value": f"{result['price_b']:.2f} PLN", "inline": True},
            {"name": "📊 Z-Score teraz", "value": f"**{z:+.4f}**", "inline": True},
            {"name": "🕒 Czas sygnału", "value": ts, "inline": True},
        ],
        "footer": {"text": "GPW Analyst  •  Sygnał zamknięcia pozycji  •  Mean Reversion"},
    }]}

    try:
        resp = requests.post(webhook, json=payload, timeout=15)
        if resp.status_code in (200, 204):
            print(f"[Discord] 🏁 Alert zamknięcia wysłany dla {result['pair']} (Z={z:+.4f})")
    except Exception as e:
        print(f"[Discord] ❌ Błąd alertu zamknięcia: {e}")


def _maybe_send_discord_alert(result):
    if result["signal"] not in ("SELL_A_BUY_B", "BUY_A_SELL_B"):
        return
    if not DISCORD_WEBHOOK_URL:
        print("[Discord] DISCORD_WEBHOOK_URL nie ustawiony - pomijam alert.")
        return

    if not _is_market_hours():
        print(f"[Discord] Poza sesjq GPW ({datetime.now():%H:%M}, 09:30-16:45) - pomijam alert dla {result['pair']}.")
        return

    # Filtr jakości: Entry Score musi być >= 45 (minimum WATCH)
    entry_score = result.get("entry_score", 0)
    if entry_score < 45:
        print(f"[Discord] Entry Score {entry_score}/100 < 45 dla {result['pair']} – sygnał zbyt słaby, pomijam.")
        return

    pair_name = result["pair"]
    last = _alert_cooldown.get(pair_name)
    if last and (datetime.now() - last).seconds < ALERT_COOLDOWN_MIN * 60:
        print(f"[Discord] Cooldown aktywny dla {pair_name} - pomijam.")
        return

    if _send_arbitrage_alert(result):
        _alert_cooldown[pair_name] = datetime.now()
    _send_email_alert(result)
    # Zapamiętaj sygnał dla tej pary (w pamięci i DB)
    _last_signal[pair_name] = result["signal"]
    _save_signal_to_db(pair_name, result["signal"], result["zscore"])


def _send_email_alert(r):
    """Wysyła alert o rozjeździe cen na Gmail."""
    if not all([GMAIL_FROM, GMAIL_TO, GMAIL_APP_PASSWORD]):
        print("[Email] Brak konfiguracji Gmail – pomijam.")
        return False

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    z = r["zscore"]
    signal = r["signal"]
    is_extreme = r.get("is_extreme", False)
    entry_score = r.get("entry_score", 0)
    entry_label = r.get("entry_label", "")
    ts = datetime.fromisoformat(r["timestamp"]).strftime("%d.%m.%Y %H:%M")

    if signal == "SELL_A_BUY_B":
        kierunek = f"SPRZEDAJ {r['label_a']} / KUP {r['label_b']}"
        emoji = "🔴"
    else:
        kierunek = f"KUP {r['label_a']} / SPRZEDAJ {r['label_b']}"
        emoji = "🟢"

    subject = f"{emoji} GPW Analyst – Sygnał arbitrażu: {r['pair']} (Z={z:+.2f})"
    if is_extreme:
        subject = f"⚠️ EKSTREMUM – {subject}"

    html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: {'#8B0000' if is_extreme else '#1a1a2e'}; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0">{emoji} Sygnał Arbitrażu – Para {r['pair']}</h2>
        {'<p style="color:#ff6b6b; font-weight:bold">⚠️ EKSTREMALNA ANOMALIA – potrójna weryfikacja przed wejściem!</p>' if is_extreme else ''}
    </div>
    <div style="background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; border: 1px solid #dee2e6;">
        <table style="width:100%; border-collapse: collapse;">
            <tr>
                <td style="padding:8px; border-bottom:1px solid #dee2e6"><strong>{r['label_a']} ({r['ticker_a']})</strong></td>
                <td style="padding:8px; border-bottom:1px solid #dee2e6; text-align:right"><strong>{r['price_a']:.2f} PLN</strong></td>
            </tr>
            <tr>
                <td style="padding:8px; border-bottom:1px solid #dee2e6"><strong>{r['label_b']} ({r['ticker_b']})</strong></td>
                <td style="padding:8px; border-bottom:1px solid #dee2e6; text-align:right"><strong>{r['price_b']:.2f} PLN</strong></td>
            </tr>
            <tr>
                <td style="padding:8px; border-bottom:1px solid #dee2e6">Z-Score</td>
                <td style="padding:8px; border-bottom:1px solid #dee2e6; text-align:right; color:{'#dc3545' if z > 0 else '#28a745'}"><strong>{z:+.4f}</strong> (próg ±{r['z_threshold']})</td>
            </tr>
            <tr>
                <td style="padding:8px; border-bottom:1px solid #dee2e6">Entry Score</td>
                <td style="padding:8px; border-bottom:1px solid #dee2e6; text-align:right"><strong>{entry_score}/100</strong> – {entry_label}</td>
            </tr>
            <tr>
                <td style="padding:8px; border-bottom:1px solid #dee2e6">Velocity</td>
                <td style="padding:8px; border-bottom:1px solid #dee2e6; text-align:right">{r.get('velocity_signal','')}</td>
            </tr>
            <tr>
                <td style="padding:8px; border-bottom:1px solid #dee2e6">Half-life</td>
                <td style="padding:8px; border-bottom:1px solid #dee2e6; text-align:right">{r.get('half_life', '?')}d</td>
            </tr>
        </table>
        <div style="background: {'#dc3545' if signal == 'SELL_A_BUY_B' else '#28a745'}; color:white; padding:12px; border-radius:6px; margin-top:16px; text-align:center;">
            <strong>{kierunek}</strong>
        </div>
        {'<p style="color:#dc3545; font-weight:bold; text-align:center">Zalecana potrójna weryfikacja kondycji spółek przed otwarciem pozycji manualnej.</p>' if is_extreme else ''}
        <p style="color:#6c757d; font-size:12px; margin-top:16px; text-align:center">
            Czas sygnału: {ts} · Dane: yFinance Adj Close · GPW Analyst V4
        </p>
    </div>
    </body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = GMAIL_FROM
        msg["To"] = GMAIL_TO
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_FROM, GMAIL_TO, msg.as_string())

        print(f"[Email] ✅ Alert wysłany na {GMAIL_TO} dla {r['pair']} (Z={z:+.4f})")
        return True
    except Exception as e:
        print(f"[Email] ❌ Błąd wysyłki: {e}")
        return False


def _send_arbitrage_alert(r):
    z = r["zscore"]
    signal = r["signal"]
    is_extreme = r.get("is_extreme", False)

    if signal == "SELL_A_BUY_B":
        emoji  = "🔴"
        action = f"SPRZEDAJ **{r['label_a']}** / KUP **{r['label_b']}**"
        desc   = f"{r['label_a']} jest *przewartościowany* względem {r['label_b']}"
    else:
        emoji  = "🟢"
        action = f"KUP **{r['label_a']}** / SPRZEDAJ **{r['label_b']}**"
        desc   = f"{r['label_a']} jest *niedowartościowany* względem {r['label_b']}"

    # Ostrzeżenie o ekstremalnym Z-Score
    if is_extreme:
        color  = 0x8B0000   # ciemnoczerwony / purpurowy
        title  = f"⚠️ UWAGA: EKSTREMALNA ANOMALIA — Para {r['pair']}"
        action += "\n\n🚨 **Zalecana potrójna weryfikacja kondycji spółek przed otwarciem pozycji manualnej.**"
        desc   = f"⚠️ **RYZYKO ZMIANY FUNDAMENTALNEJ LUB BŁĘDU DANYCH**\n{desc}"
    else:
        color  = 0xe74c3c if signal == "SELL_A_BUY_B" else 0x2ecc71
        title  = f"{emoji} SYGNAŁ ARBITRAŻU — Para {r['pair']}"

    ts = datetime.fromisoformat(r["timestamp"]).strftime("%d.%m.%Y %H:%M")

    payload = {"embeds": [{
        "title":       title,
        "description": f"{desc}\n\n**Rekomendacja:** {action}",
        "color":       color,
        "fields": [
            {"name": f"💰 {r['label_a']} ({r['ticker_a']})",
             "value": f"**{r['price_a']:.2f} PLN**\n*Cena skorygowana (Adj Close)*",
             "inline": True},
            {"name": f"💰 {r['label_b']} ({r['ticker_b']})",
             "value": f"**{r['price_b']:.2f} PLN**\n*Cena skorygowana (Adj Close)*",
             "inline": True},
            {"name": "📊 Z-Score",
             "value": f"**{z:+.4f}** (próg: ±{r['z_threshold']}{'  ⚠️ EKSTREMUM' if is_extreme else ''})",
             "inline": True},
            {"name": "📈 Spread bieżący",
             "value": str(r["spread"]), "inline": True},
            {"name": "📉 Spread SMA",
             "value": str(r["spread_sma"]), "inline": True},
            {"name": "📐 Spread Std",
             "value": str(r["spread_std"]), "inline": True},
            {"name": "🕐 Okno analizy",
             "value": f"{r['lookback_days']} dni ({r['data_points']} sesji dziennych, Adj Close)", "inline": True},
            {"name": "🕒 Czas sygnału",
             "value": ts, "inline": True},
        ],
        "footer": {"text": "GPW Analyst  •  Arbitraż statystyczny (mean reversion)  •  Dane: yFinance Adj Close (skorygowane o dywidendy i splity)"},
    }]}

    try:
        webhook = DISCORD_ARBITRAGE_WEBHOOK if DISCORD_ARBITRAGE_WEBHOOK else DISCORD_WEBHOOK_URL
        resp = requests.post(webhook, json=payload, timeout=15)
        if resp.status_code in (200, 204):
            tag = " [EKSTREMUM]" if is_extreme else ""
            print(f"[Discord] ✅ Alert{tag} wysłany dla {r['pair']} (Z={z:+.4f})")
            return True
        print(f"[Discord] ❌ Błąd {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Discord] ❌ Wyjątek: {e}")
    return False


# ── Scheduler (wątek tła, co 60 minut) ───────────────────────────

_scheduler_running = False
_scheduler_thread = None
REFRESH_INTERVAL_SEC = 3600


def _scheduler_loop():
    print(f"[Scheduler] Uruchomiony. Interwał: {REFRESH_INTERVAL_SEC // 60} min.")
    _load_signals_from_db()  # Wczytaj sygnały po restarcie
    while _scheduler_running:
        try:
            print(f"[Scheduler] {datetime.now():%H:%M} – odświeżam WIG20...")
            get_all_stocks()
            print(f"[Scheduler] {datetime.now():%H:%M} – liczę Z-Score...")
            for r in get_all_arbitrage():
                print(f"[Arbitraż] {r['pair']}  Z={r['zscore']:+.4f}  sygnał={r['signal']}")
        except Exception as e:
            print(f"[Scheduler] Błąd: {e}")
        elapsed = 0
        while _scheduler_running and elapsed < REFRESH_INTERVAL_SEC:
            time.sleep(5)
            elapsed += 5


def start_scheduler():
    global _scheduler_running, _scheduler_thread
    if _scheduler_running:
        return
    _scheduler_running = True
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, name="GPWScheduler", daemon=True
    )
    _scheduler_thread.start()


def stop_scheduler():
    global _scheduler_running
    _scheduler_running = False
    print("[Scheduler] Zatrzymany.")
