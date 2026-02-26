import yfinance as yf
import pandas as pd
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
    "ORL.WA", "PKO.WA", "PZU.WA", "SPL.WA", "PCO.WA"
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
            "ORL.WA": "Orlen",
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
        print(f"Parallel fetching {len(tickers_to_fetch)} tickers...")
        with ThreadPoolExecutor(max_workers=len(tickers_to_fetch)) as executor:
            fetched_data = list(executor.map(fetch_single_ticker, tickers_to_fetch))
            
        conn = get_db_connection()
        for data in fetched_data:
            if data:
                conn.execute("""INSERT OR REPLACE INTO stocks (ticker, name, price, pe, pbv, roe, div_yield, operating_margin, ebitda, total_debt, total_cash, recommendation, market_cap, beta, sector, last_updated) 
                                VALUES (:ticker, :name, :price, :pe, :pbv, :roe, :div_yield, :operating_margin, :ebitda, :total_debt, :total_cash, :recommendation, :market_cap, :beta, :sector, :last_updated)""", data)
                results.append(data)
        conn.commit()
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