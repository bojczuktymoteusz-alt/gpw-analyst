import { useEffect, useState } from 'react';
import { ArbitrageResult } from './types';
import { Activity, TrendingUp, TrendingDown, Minus, RefreshCw, AlertTriangle } from 'lucide-react';

interface Props {
    isDarkMode: boolean;
    apiUrl: string;
}

const SIGNAL_CONFIG = {
    BUY_A_SELL_B: {
        label: 'KUP A / SPRZEDAJ B',
        color: 'text-emerald-400',
        bg: 'bg-emerald-500/10 border-emerald-500/30',
        icon: <TrendingUp size={18} />,
        dot: 'bg-emerald-400',
    },
    SELL_A_BUY_B: {
        label: 'SPRZEDAJ A / KUP B',
        color: 'text-rose-400',
        bg: 'bg-rose-500/10 border-rose-500/30',
        icon: <TrendingDown size={18} />,
        dot: 'bg-rose-400',
    },
    WATCH_HIGH: {
        label: 'OBSERWUJ – wysoki spread',
        color: 'text-amber-400',
        bg: 'bg-amber-500/10 border-amber-500/30',
        icon: <AlertTriangle size={18} />,
        dot: 'bg-amber-400',
    },
    WATCH_LOW: {
        label: 'OBSERWUJ – niski spread',
        color: 'text-amber-400',
        bg: 'bg-amber-500/10 border-amber-500/30',
        icon: <AlertTriangle size={18} />,
        dot: 'bg-amber-400',
    },
    NEUTRAL: {
        label: 'NEUTRALNY',
        color: 'text-slate-400',
        bg: 'bg-slate-500/10 border-slate-500/30',
        icon: <Minus size={18} />,
        dot: 'bg-slate-400',
    },
};

const ENTRY_CONFIG = {
    FULL_ENTRY:   { label: '✅ FULL ENTRY',    color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/30' },
    TRADE_SMALL:  { label: '🟠 TRADE – mała poz.', color: 'text-orange-400', bg: 'bg-orange-500/15 border-orange-500/30' },
    WATCH:        { label: '👁 WATCH',          color: 'text-amber-400',   bg: 'bg-amber-500/15 border-amber-500/30' },
    NO_TRADE:     { label: '❌ NO TRADE',       color: 'text-slate-400',   bg: 'bg-slate-500/10 border-slate-500/20' },
};

function EntryScoreBar({ score, isDarkMode }: { score: number; isDarkMode: boolean }) {
    const color = score >= 75 ? 'bg-emerald-500' : score >= 60 ? 'bg-orange-400' : score >= 45 ? 'bg-amber-400' : 'bg-slate-500';
    return (
        <div className="relative w-full">
            <div className={`w-full h-2 rounded-full ${isDarkMode ? 'bg-slate-700' : 'bg-slate-200'}`}>
                <div className={`h-2 rounded-full transition-all duration-700 ${color}`} style={{ width: `${score}%` }} />
            </div>
            {/* Progi */}
            {[45, 60, 75].map(p => (
                <div key={p} className="absolute top-0 h-2 w-px bg-white/20" style={{ left: `${p}%` }} />
            ))}
        </div>
    );
}

function ZScoreBar({ zscore, threshold }: { zscore: number; threshold: number }) {
    // Skaluj z -3*threshold do +3*threshold → 0–100%
    const max = threshold * 3;
    const pct = Math.min(Math.max(((zscore + max) / (max * 2)) * 100, 0), 100);
    const centerPct = ((0 + max) / (max * 2)) * 100;
    const lowPct = ((-threshold + max) / (max * 2)) * 100;
    const highPct = ((threshold + max) / (max * 2)) * 100;

    const barColor =
        Math.abs(zscore) >= threshold
            ? zscore > 0 ? 'bg-rose-500' : 'bg-emerald-500'
            : 'bg-indigo-500';

    return (
        <div className="relative w-full h-3 bg-slate-700/50 rounded-full mt-2 mb-1">
            {/* Strefy */}
            <div
                className="absolute top-0 h-full bg-emerald-500/20 rounded-l-full"
                style={{ left: '0%', width: `${lowPct}%` }}
            />
            <div
                className="absolute top-0 h-full bg-rose-500/20 rounded-r-full"
                style={{ left: `${highPct}%`, right: '0%' }}
            />
            {/* Linie progów */}
            <div className="absolute top-0 h-full w-px bg-emerald-400/60" style={{ left: `${lowPct}%` }} />
            <div className="absolute top-0 h-full w-px bg-slate-400/40" style={{ left: `${centerPct}%` }} />
            <div className="absolute top-0 h-full w-px bg-rose-400/60" style={{ left: `${highPct}%` }} />
            {/* Wskaźnik */}
            <div
                className={`absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 border-slate-900 shadow-lg ${barColor} transition-all duration-700`}
                style={{ left: `calc(${pct}% - 8px)` }}
            />
        </div>
    );
}

function PairCard({ data, isDarkMode }: { data: ArbitrageResult; isDarkMode: boolean }) {
    const sig = SIGNAL_CONFIG[data.signal];
    const zAbs = Math.abs(data.zscore);
    const isAlert = data.signal === 'BUY_A_SELL_B' || data.signal === 'SELL_A_BUY_B';
    const isExtreme = data.is_extreme;
    const ts = new Date(data.timestamp).toLocaleString('pl-PL', {
        hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'
    });

    return (
        <div className={`rounded-2xl border p-6 transition-all duration-300 ${
            isDarkMode ? 'bg-slate-900/60 border-white/8' : 'bg-white border-slate-200'
        } ${isExtreme
            ? 'ring-2 ring-red-600/70 shadow-lg shadow-red-900/30'
            : isAlert
                ? 'ring-1 ' + (data.signal === 'SELL_A_BUY_B' ? 'ring-rose-500/40' : 'ring-emerald-500/40')
                : ''
        }`}>

            {/* Banner ekstremalnej anomalii */}
            {isExtreme && (
                <div className="mb-5 rounded-xl px-4 py-3 bg-red-900/80 border border-red-500/60 flex items-start gap-3">
                    <span className="text-xl mt-0.5">⚠️</span>
                    <div>
                        <p className="text-red-300 font-extrabold text-sm tracking-wide uppercase">
                            Ekstremalna Anomalia — Ryzyko Zmiany Fundamentalnej lub Błędu Danych
                        </p>
                        <p className="text-red-400/80 text-xs mt-1">
                            Zalecana potrójna weryfikacja kondycji spółek przed otwarciem pozycji manualnej.
                        </p>
                    </div>
                </div>
            )}

            {/* Nagłówek */}
            <div className="flex items-center justify-between mb-5">
                <div>
                    <h3 className="text-lg font-bold tracking-tight">Para {data.pair}</h3>
                    <p className={`text-xs mt-0.5 ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                        {data.label_a} vs {data.label_b} · {data.lookback_days}d · {data.data_points} sesji (Adj Close 1d)
                    </p>
                    <p className={`text-[10px] mt-0.5 font-semibold ${isDarkMode ? 'text-indigo-400/60' : 'text-indigo-400'}`}>
                        Ceny skorygowane o dywidendy i splity (Adj Close)
                    </p>
                </div>
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-bold ${sig.bg} ${sig.color}`}>
                    {sig.icon}
                    {sig.label}
                </div>
            </div>

            {/* Ceny */}
            <div className="grid grid-cols-2 gap-3 mb-5">
                {[
                    { label: data.label_a, ticker: data.ticker_a, price: data.price_a },
                    { label: data.label_b, ticker: data.ticker_b, price: data.price_b },
                ].map(({ label, ticker, price }) => (
                    <div key={ticker} className={`rounded-xl p-3 ${isDarkMode ? 'bg-slate-800/60' : 'bg-slate-50'}`}>
                        <p className={`text-[11px] font-bold uppercase tracking-widest mb-1 ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                            {label}
                        </p>
                        <p className="text-xl font-extrabold tabular-nums">{price.toFixed(2)}</p>
                        <p className={`text-[10px] ${isDarkMode ? 'text-slate-600' : 'text-slate-400'}`}>{ticker}</p>
                    </div>
                ))}
            </div>

            {/* Z-Score */}
            <div className={`rounded-xl p-4 mb-4 ${
                isExtreme
                    ? 'bg-red-950/60 border border-red-700/40'
                    : isDarkMode ? 'bg-slate-800/60' : 'bg-slate-50'
            }`}>
                <div className="flex items-end justify-between mb-1">
                    <span className={`text-[11px] font-bold uppercase tracking-widest ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                        Z-Score {isExtreme && <span className="text-red-400 ml-1">⚠️ EKSTREMUM</span>}
                    </span>
                    <span className={`text-3xl font-extrabold tabular-nums ${
                        isExtreme
                            ? 'text-red-400'
                            : zAbs >= data.z_threshold
                                ? data.zscore > 0 ? 'text-rose-400' : 'text-emerald-400'
                                : zAbs >= data.z_threshold * 0.75 ? 'text-amber-400' : 'text-indigo-400'
                    }`}>
                        {data.zscore > 0 ? '+' : ''}{data.zscore.toFixed(4)}
                    </span>
                </div>
                <ZScoreBar zscore={data.zscore} threshold={data.z_threshold} />
                <div className="flex justify-between text-[10px] mt-1 opacity-40">
                    <span>−{data.z_threshold * 3}</span>
                    <span>−{data.z_threshold} | 0 | +{data.z_threshold}</span>
                    <span>+{data.z_threshold * 3}</span>
                </div>
            </div>

            {/* Spread stats */}
            <div className="grid grid-cols-3 gap-2">
                {[
                    { label: 'Spread', value: data.spread.toFixed(6) },
                    { label: 'SMA spreadu', value: data.spread_sma.toFixed(6) },
                    { label: 'Std spreadu', value: data.spread_std.toFixed(6) },
                ].map(({ label, value }) => (
                    <div key={label} className={`rounded-lg p-2.5 text-center ${isDarkMode ? 'bg-slate-800/40' : 'bg-slate-100'}`}>
                        <p className={`text-[10px] font-bold uppercase tracking-wider mb-1 ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>{label}</p>
                        <p className="text-xs font-mono font-bold tabular-nums">{value}</p>
                    </div>
                ))}
            </div>

            {/* Velocity */}
            <div className={`mt-3 rounded-xl p-3 border ${
                data.velocity_signal === 'DECELERATING'
                    ? 'bg-emerald-500/8 border-emerald-500/20'
                    : data.velocity_signal === 'ACCELERATING'
                        ? 'bg-rose-500/8 border-rose-500/20'
                        : isDarkMode ? 'bg-slate-800/30 border-white/5' : 'bg-slate-50 border-slate-200'
            }`}>
                <div className="flex items-center justify-between">
                    <div>
                        <p className={`text-[10px] font-bold uppercase tracking-widest mb-0.5 ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                            Velocity spreadu (5 sesji)
                        </p>
                        <p className={`text-xs font-mono tabular-nums ${
                            data.velocity > 0 ? 'text-rose-400' : data.velocity < 0 ? 'text-emerald-400' : 'text-slate-400'
                        }`}>
                            {data.velocity > 0 ? '+' : ''}{data.velocity.toFixed(8)} / sesję
                            <span className={`ml-2 text-[10px] opacity-60`}>R²={data.velocity_r2.toFixed(2)}</span>
                        </p>
                    </div>
                    <div className={`px-2.5 py-1 rounded-lg text-[11px] font-bold ${
                        data.velocity_signal === 'DECELERATING'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : data.velocity_signal === 'ACCELERATING'
                                ? 'bg-rose-500/20 text-rose-400'
                                : 'bg-slate-500/20 text-slate-400'
                    }`}>
                        {data.velocity_signal === 'DECELERATING' && '🔥 HAMUJE – okno wejścia'}
                        {data.velocity_signal === 'ACCELERATING' && '⚠️ PRZYSPIESZA – czekaj'}
                        {data.velocity_signal === 'FLAT' && '— PŁASKI'}
                    </div>
                </div>
            </div>

            {/* ENTRY SCORE */}
            {(() => {
                const ec = ENTRY_CONFIG[data.entry_label];
                return (
                    <div className={`mt-3 rounded-xl p-4 border ${isDarkMode ? 'bg-slate-800/60 border-white/5' : 'bg-slate-50 border-slate-200'}`}>
                        <div className="flex items-center justify-between mb-2">
                            <p className={`text-[10px] font-bold uppercase tracking-widest ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                                Entry Score
                            </p>
                            <div className={`flex items-center gap-2`}>
                                <span className={`text-2xl font-extrabold tabular-nums ${ec.color}`}>
                                    {data.entry_score}
                                </span>
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-lg border ${ec.bg} ${ec.color}`}>
                                    {ec.label}
                                </span>
                            </div>
                        </div>
                        <EntryScoreBar score={data.entry_score} isDarkMode={isDarkMode} />
                        {/* Breakdown */}
                        <div className="grid grid-cols-4 gap-1.5 mt-2.5">
                            {[
                                { label: 'Velocity', val: data.score_velocity, max: 38 },
                                { label: 'Z-Score', val: data.score_zscore, max: 27 },
                                { label: 'R²', val: data.score_r2, max: 15, blocked: data.r2_gate_blocked },
                                { label: 'Regime', val: data.score_regime, max: 20 },
                            ].map(({ label, val, max, blocked }) => (
                                <div key={label} className={`rounded-lg p-2 text-center ${isDarkMode ? 'bg-slate-700/40' : 'bg-slate-100'} ${blocked ? 'opacity-40' : ''}`}>
                                    <p className={`text-[9px] font-bold uppercase tracking-wider ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                                        {label}{blocked ? ' 🚫' : ''}
                                    </p>
                                    <p className="text-xs font-bold tabular-nums mt-0.5">
                                        {val}<span className="opacity-40">/{max}</span>
                                    </p>
                                </div>
                            ))}
                        </div>
                        {/* Regime info */}
                        <div className="flex items-center justify-between mt-2">
                            <p className={`text-[10px] ${isDarkMode ? 'text-slate-600' : 'text-slate-300'}`}>
                                Half-life: <span className={data.regime_active ? 'text-emerald-400' : 'text-rose-400'}>
                                    {data.half_life === 999 ? '∞' : `${data.half_life}d`}
                                </span>
                                {' '}· Regime MR: <span className={data.regime_active ? 'text-emerald-400' : 'text-rose-400'}>
                                    {data.regime_active ? '✅ ON' : '❌ OFF'}
                                </span>
                            </p>
                            {data.r2_gate_blocked && (
                                <p className="text-[10px] text-amber-400">R²&lt;0.3 – velocity zablokowany</p>
                            )}
                        </div>
                    </div>
                );
            })()}

            <p className={`text-[10px] mt-3 text-right ${isDarkMode ? 'text-slate-600' : 'text-slate-300'}`}>
                Obliczono: {ts}
            </p>
        </div>
    );
}

export default function ArbitrageView({ isDarkMode, apiUrl }: Props) {
    const [data, setData] = useState<ArbitrageResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchArbitrage = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`${apiUrl}/api/arbitrage`);
            if (!res.ok) throw new Error(`Błąd serwera: ${res.status}`);
            setData(await res.json());
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Nieznany błąd');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchArbitrage(); }, []);

    return (
        <div>
            {/* Nagłówek sekcji */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <p className={`text-xs font-bold uppercase tracking-widest mb-1 ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                        Mean Reversion · Arbitraż Statystyczny
                    </p>
                    <h3 className="text-xl font-extrabold">Monitorowane pary</h3>
                </div>
                <button
                    onClick={fetchArbitrage}
                    disabled={loading}
                    className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
                        isDarkMode ? 'bg-slate-800 text-slate-300 border border-white/5 hover:bg-slate-700' : 'bg-white text-slate-600 border border-slate-200 shadow-sm hover:bg-slate-50'
                    }`}
                >
                    <RefreshCw size={14} className={loading ? 'animate-spin text-indigo-500' : ''} />
                    Przelicz Z-Score
                </button>
            </div>

            {/* Legenda */}
            <div className={`rounded-xl p-4 mb-6 text-xs leading-relaxed ${isDarkMode ? 'bg-slate-800/40 text-slate-400' : 'bg-slate-50 text-slate-500'}`}>
                <span className="font-bold text-indigo-400">Jak czytać Z-Score?</span>
                {'  '}
                Z-Score mierzy odchylenie bieżącego spreadu od jego średniej historycznej w jednostkach odchyleń standardowych.
                {'  '}
                <span className="text-emerald-400 font-semibold">Z &lt; −{2.0}</span> → A tanie względem B (sygnał kupna A).
                {'  '}
                <span className="text-rose-400 font-semibold">Z &gt; +{2.0}</span> → A drogie względem B (sygnał sprzedaży A).
                {'  '}
                Alerty Discord wysyłane automatycznie przy przekroczeniu progu.
            </div>

            {error && (
                <div className="mb-6 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm font-semibold flex items-center gap-3">
                    <span>⚠️</span>
                    <span>{error}</span>
                    <button onClick={fetchArbitrage} className="ml-auto underline opacity-70 hover:opacity-100">Spróbuj ponownie</button>
                </div>
            )}

            {loading && data.length === 0 && (
                <div className="flex items-center justify-center py-24">
                    <div className="flex flex-col items-center gap-4">
                        <div className="relative w-12 h-12">
                            <div className="absolute inset-0 border-4 border-indigo-500/20 rounded-full" />
                            <div className="absolute inset-0 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                            <Activity className="absolute inset-0 m-auto text-indigo-500" size={18} />
                        </div>
                        <p className="text-sm font-semibold opacity-60">Pobieranie danych i obliczanie Z-Score...</p>
                        <p className="text-xs opacity-40">Może potrwać 10–15 sekund (yFinance)</p>
                    </div>
                </div>
            )}

            {!loading && data.length === 0 && !error && (
                <div className="text-center py-24 opacity-40">
                    <p className="text-lg font-bold">Brak danych</p>
                    <p className="text-sm mt-1">Kliknij "Przelicz Z-Score" aby pobrać dane</p>
                </div>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {data.map(pair => (
                    <PairCard key={pair.pair} data={pair} isDarkMode={isDarkMode} />
                ))}
            </div>
        </div>
    );
}
