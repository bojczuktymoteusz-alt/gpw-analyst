# GPW-Analyst-V2

Fullstack application for analyzing Warsaw Stock Exchange data.

## Structure
- `/backend`: FastAPI + SQLite + yfinance
- `/frontend`: React + Vite + Tailwind CSS v4

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Features
- Real-time stock data (cached for 24h)
- Historical charts (1 year)
- Key metrics dashboard (P/E, P/BV, ROE, Div Yield)
