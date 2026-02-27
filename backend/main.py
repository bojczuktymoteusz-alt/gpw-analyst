from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from data_fetcher import get_all_stocks, get_stock_history, predict_stock_price
from database import init_db
import uvicorn

app = FastAPI(title="GPW Analyst V2 - Enterprise Edition")

# Pełne wsparcie CORS dla frontendu
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicjalizacja bazy Supabase przy starcie
@app.on_event("startup")
def on_startup():
    print("🚀 System start-up: Initializing Supabase connection...")
    try:
        init_db()
        print("✅ Database ready.")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

@app.get("/api/stocks")
def read_stocks():
    print("📡 Fetching all stocks...")
    return get_all_stocks()

@app.get("/api/stock/{ticker}/history")
def read_stock_history(ticker: str, period: str = "1y"):
    print(f"📊 Fetching history for {ticker}...")
    data = get_stock_history(ticker, period)
    if not data:
        raise HTTPException(status_code=404, detail="Stock history not found")
    return data

@app.get("/api/stock/{ticker}/predict")
def predict_stock(ticker: str):
    print(f"🧠 AI Engine: Calculating prediction for {ticker}...")
    prediction = predict_stock_price