from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from data_fetcher import (
    get_all_stocks, get_stock_history, predict_stock_price,
    get_all_arbitrage, compute_zscore, ARBITRAGE_PAIRS,
    start_scheduler, stop_scheduler,
)
from database import init_db, clear_price_history

# Tickery par arbitrażowych – ich price_history czyścimy przy starcie,
# bo mogą zawierać stare nieskorygowane ceny (przed Adj Close)
ARBITRAGE_TICKERS = list({
    t for pair in ARBITRAGE_PAIRS
    for t in (pair["ticker_a"], pair["ticker_b"])
})


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 GPW Analyst V4 – inicjalizacja...")
    init_db()
    print("✅ Baza danych gotowa.")

    # Jednorazowe czyszczenie starych nieskorygowanych cen
    clear_price_history(ARBITRAGE_TICKERS)
    print(f"✅ Cache price_history wyczyszczony dla: {ARBITRAGE_TICKERS}")

    start_scheduler()
    print("✅ Scheduler uruchomiony (odświeżanie co 60 min).")
    yield
    stop_scheduler()


app = FastAPI(title="GPW Analyst V4 – yFinance Adj Close + Arbitraż", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WIG20 ──────────────────────────────────────────────────────────

@app.get("/api/stocks")
def read_stocks():
    return get_all_stocks()


@app.get("/api/stock/{ticker}/history")
def read_stock_history(ticker: str, period: str = "1y"):
    data = get_stock_history(ticker, period)
    if not data:
        raise HTTPException(status_code=404, detail=f"No history for {ticker}")
    return data


@app.get("/api/stock/{ticker}/predict")
def predict_stock(ticker: str):
    prediction = predict_stock_price(ticker)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")
    return prediction


# ── Arbitraż ───────────────────────────────────────────────────────

@app.get("/api/arbitrage")
def read_arbitrage():
    """
    Z-Score dla wszystkich par – bulk download Adj Close.
    Zdefiniowane jako def (nie async def) – FastAPI uruchamia
    w osobnym wątku z threadpool, nie blokując pętli zdarzeń.
    """
    return get_all_arbitrage()


@app.get("/api/arbitrage/{pair_name}")
def read_arbitrage_pair(pair_name: str):
    pair = next((p for p in ARBITRAGE_PAIRS if p["name"] == pair_name), None)
    if not pair:
        raise HTTPException(status_code=404, detail=f"Para '{pair_name}' nie istnieje")
    result = compute_zscore(pair)
    if not result:
        raise HTTPException(status_code=503, detail="Nie można pobrać danych")
    return result