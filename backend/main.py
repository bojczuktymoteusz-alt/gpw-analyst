from fastapi import FastAPI, HTTPException
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
    prediction = predict_stock_price(ticker)
    if not prediction:
        # Zamiast błędu 404, zwracamy info o braku danych, żeby frontend nie padł
        return {"error": "Insufficient data for prediction"}
    return prediction

# NOWY ENDPOINT: Służy do ręcznego uruchamienia pobierania danych z poziomu przeglądarki
@app.get("/api/update")
def update_data():
    print("Uruchamiam pobieranie danych na serwerze...")
    get_all_stocks()
    return {"status": "Sukces", "message": "Dane GPW zostały pobrane i zapisane w bazie!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)