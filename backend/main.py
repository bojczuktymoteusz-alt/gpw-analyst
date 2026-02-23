from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from data_fetcher import get_all_stocks, get_stock_history, predict_stock_price
from database import init_db

app = FastAPI(title="GPW Analyst V2")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/api/stocks")
def read_stocks():
    return get_all_stocks()

@app.get("/api/stock/{ticker}/history")
def read_stock_history(ticker: str, period: str = "1y"):
    data = get_stock_history(ticker, period)
    if not data:
        raise HTTPException(status_code=404, detail="Stock history not found")
    return data
@app.get("/api/stock/{ticker}/predict")
def predict_stock(ticker: str):
    prediction = predict_stock_price(ticker)
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction failed or insufficient data")
    return prediction
