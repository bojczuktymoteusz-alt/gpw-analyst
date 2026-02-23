export interface Stock {
    ticker: string;
    name: string;
    price: number;
    pe: number;
    pbv: number;
    roe: number;
    div_yield: number;
    operating_margin?: number;
    ebitda?: number;
    total_debt?: number;
    total_cash?: number;
    recommendation?: string;
    market_cap?: number;
    beta?: number;
    sector?: string;
    sector_pe_avg?: number;
    sector_margin_avg?: number;
    last_updated?: string;
    prediction?: Prediction;
}

export interface StockHistory {
    date: string;
    close: number;
}

export interface Prediction {
    ticker: string;
    current_price: number;
    predicted_price: number;
    trend_pct: number;
    trend: 'up' | 'down' | 'neutral';
    forecast_days: number;
}
