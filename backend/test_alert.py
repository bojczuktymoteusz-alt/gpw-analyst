from dotenv import load_dotenv
load_dotenv()
from data_fetcher import _send_arbitrage_alert
from datetime import datetime

test = {
    'pair': 'PKO/PEO',
    'ticker_a': 'PKO.WA', 'ticker_b': 'PEO.WA',
    'label_a': 'PKO BP', 'label_b': 'Bank Pekao',
    'price_a': 104.60, 'price_b': 228.00,
    'zscore': -2.15, 'z_threshold': 2.0,
    'signal': 'BUY_A_SELL_B',
    'is_extreme': False,
    'entry_score': 65, 'entry_label': 'TRADE_SMALL',
    'velocity_signal': 'DECELERATING',
    'velocity': -0.001, 'velocity_r2': 0.65,
    'half_life': 8.5,
    'regime_active': True,
    'r2_gate_blocked': False,
    'score_velocity': 38, 'score_zscore': 15,
    'score_r2': 7, 'score_regime': 20,
    'spread': -0.779, 'spread_sma': -0.777, 'spread_std': 0.015,
    'lookback_days': 30, 'data_points': 30,
    'timestamp': datetime.now().isoformat()
}

_send_arbitrage_alert(test)