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
    payout_ratio?: number | null;
    debt_to_equity?: number | null;
    trailing_div_yield?: number | null;
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

export interface ArbitrageResult {
    pair: string;
    ticker_a: string;
    ticker_b: string;
    label_a: string;
    label_b: string;
    price_a: number;
    price_b: number;
    spread: number;
    spread_sma: number;
    spread_std: number;
    zscore: number;
    z_threshold: number;
    lookback_days: number;
    data_points: number;
    signal: 'BUY_A_SELL_B' | 'SELL_A_BUY_B' | 'WATCH_HIGH' | 'WATCH_LOW' | 'NEUTRAL';
    is_extreme: boolean;
    velocity: number;
    velocity_r2: number;
    velocity_signal: 'DECELERATING' | 'ACCELERATING' | 'FLAT';
    entry_score: number;
    entry_label: 'NO_TRADE' | 'WATCH' | 'TRADE_SMALL' | 'FULL_ENTRY';
    score_velocity: number;
    score_zscore: number;
    score_r2: number;
    score_regime: number;
    half_life: number;
    regime_active: boolean;
    r2_gate_blocked: boolean;
    timestamp: string;
}