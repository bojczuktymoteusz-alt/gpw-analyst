from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from data_fetcher import get_all_stocks, get_stock_history, predict_stock_price
from database import init_db


# BUG FIX: @app.on_event("startup") is deprecated since FastAPI 0.93.
# Use the lifespan context manager instead.
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 GPW Analyst V2 – initializing SQLite database...")
    try:
        init_db()
        print("✅ Database ready.")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
    yield  # application runs here


app = FastAPI(title="GPW Analyst V2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/stocks")
def read_stocks():
    print("📡 /api/stocks called")
    return get_all_stocks()


@app.get("/api/stock/{ticker}/history")
def read_stock_history(ticker: str, period: str = "1y"):
    print(f"📊 /api/stock/{ticker}/history called (period={period})")
    data = get_stock_history(ticker, period)
    if not data:
        raise HTTPException(status_code=404, detail=f"No history found for {ticker}")
    return data


@app.get("/api/stock/{ticker}/predict")
def predict_stock(ticker: str):
    # BUG FIX: original file was truncated – predict_stock_price was never called!
    print(f"🧠 /api/stock/{ticker}/predict called")
    prediction = predict_stock_price(ticker)
    if prediction is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not generate prediction for {ticker} (insufficient data)",
        )
    return prediction
