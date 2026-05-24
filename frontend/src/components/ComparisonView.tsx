import React from 'react';
import { Stock } from '../types';
import { ArrowUpRight, ArrowDownRight, X, ArrowLeft } from 'lucide-react';

interface Props {
    stocks: Stock[];
    isDarkMode: boolean;
    onRemove: (ticker: string) => void;
    onBack: () => void;
}

function formatMarketCap(cap?: number): string {
    if (!cap) return '—';
    if (cap >= 1e9) return `${(cap / 1e9).toFixed(2)}B`;
    if (cap >= 1e6) return `${(cap / 1e6).toFixed(2)}M`;
    return cap.toLocaleString('pl-PL');
}

function calcScore(s: Stock): number {
    let score = 0;
    if (s.pe > 0 && s.pe < 15) score += 25;
    if (s.pbv > 0 && s.pbv < 2) score += 25;
    if (s.roe > 0.15) score += 25;
    if (s.div_yield > 0.04) score += 25;
    if (s.beta && s.beta < 1.0) score = Math.min(100, score + 5);
    return score;
}

function findBest(values: (number | null)[], higherIsBetter: boolean): number {
    let idx = -1;
    let best = higherIsBetter ? -Infinity : Infinity;
    values.forEach((v, i) => {
        if (v === null) return;
        if (higherIsBetter ? v > best : v < best) { best = v; idx = i; }
    });
    return idx;
}

type Row = {
    label: string;
    hint?: string;
    rawNums: (number | null)[];
    higherIsBetter: boolean;
    render: (s: Stock, i: number, isBest: boolean) => React.ReactNode;
};

export default function ComparisonView({ stocks, isDarkMode, onRemove, onBack }: Props) {
    if (stocks.length === 0) {
        return (
            <div className={`rounded-3xl border py-24 text-center ${isDarkMode ? 'bg-slate-900/50 border-white/10 text-slate-400' : 'bg-white border-slate-200 text-slate-500'}`}>
                <p className="text-lg font-bold">Nie wybrano spółek</p>
                <p className="text-sm mt-1 opacity-60">Wróć do Widoku Rynku i zaznacz spółki checkboxami</p>
            </div>
        );
    }

    const scores = stocks.map(calcScore);
    const debtRatios = stocks.map(s => {
        const netDebt = (s.total_debt ?? 0) - (s.total_cash ?? 0);
        return s.ebitda && s.ebitda > 0 ? netDebt / s.ebitda : null;
    });

    const textCls = (isBest: boolean) =>
        `font-mono font-bold text-sm ${isBest ? 'text-emerald-500' : (isDarkMode ? 'text-slate-300' : 'text-slate-700')}`;

    const rows: Row[] = [
        {
            label: 'Cena (PLN)', rawNums: stocks.map(() => null), higherIsBetter: false,
            render: (s) => (
                <span className={textCls(false)}>
                    {s.price?.toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '—'}
                </span>
            ),
        },
        {
            label: 'Kapitalizacja', rawNums: stocks.map(() => null), higherIsBetter: false,
            render: (s) => (
                <span className={textCls(false)}>{formatMarketCap(s.market_cap)}</span>
            ),
        },
        {
            label: 'C/Z (PE)', hint: 'niższe = lepsze',
            rawNums: stocks.map(s => (s.pe && s.pe > 0) ? s.pe : null),
            higherIsBetter: false,
            render: (s, _, isBest) => (
                <span className={textCls(isBest)}>
                    {(s.pe && s.pe > 0) ? s.pe.toFixed(1) : '—'}
                    {isBest && <span className="ml-1 text-[10px]">★</span>}
                </span>
            ),
        },
        {
            label: 'C/WK (PBV)', hint: 'niższe = lepsze',
            rawNums: stocks.map(s => (s.pbv && s.pbv > 0) ? s.pbv : null),
            higherIsBetter: false,
            render: (s, _, isBest) => (
                <span className={textCls(isBest)}>
                    {(s.pbv && s.pbv > 0) ? s.pbv.toFixed(2) : '—'}
                    {isBest && <span className="ml-1 text-[10px]">★</span>}
                </span>
            ),
        },
        {
            label: 'ROE', hint: 'wyższe = lepsze',
            rawNums: stocks.map(s => s.roe ?? null),
            higherIsBetter: true,
            render: (s, _, isBest) => (
                <span className={`font-mono font-bold text-sm ${isBest ? 'text-emerald-500' : (isDarkMode ? 'text-slate-300' : 'text-slate-700')}`}>
                    {s.roe ? `${(s.roe * 100).toFixed(1)}%` : '—'}
                    {isBest && <span className="ml-1 text-[10px]">★</span>}
                </span>
            ),
        },
        {
            label: 'Marża op.', hint: 'wyższe = lepsze',
            rawNums: stocks.map(s => s.operating_margin ?? null),
            higherIsBetter: true,
            render: (s, _, isBest) => (
                <span className={`font-mono font-bold text-sm ${isBest ? 'text-emerald-500' : (isDarkMode ? 'text-slate-300' : 'text-slate-700')}`}>
                    {s.operating_margin ? `${(s.operating_margin * 100).toFixed(1)}%` : '—'}
                    {isBest && <span className="ml-1 text-[10px]">★</span>}
                </span>
            ),
        },
        {
            label: 'Dług/EBITDA', hint: 'niższe = lepsze',
            rawNums: debtRatios,
            higherIsBetter: false,
            render: (_, i, isBest) => {
                const ratio = debtRatios[i];
                if (ratio === null) return <span className="text-[10px] font-bold opacity-20 uppercase">N/A</span>;
                return (
                    <span className={`font-mono font-bold text-sm ${isBest ? 'text-emerald-500' : (isDarkMode ? 'text-slate-300' : 'text-slate-700')}`}>
                        {ratio.toFixed(2)}x{isBest && <span className="ml-1 text-[10px]">★</span>}
                    </span>
                );
            },
        },
        {
            label: 'Sygnał', rawNums: stocks.map(() => null), higherIsBetter: false,
            render: (s) => {
                if (!s.recommendation || s.recommendation === 'none') {
                    return <span className="text-[10px] font-bold opacity-20 uppercase">N/A</span>;
                }
                const rec = s.recommendation.toLowerCase();
                const cls = rec.includes('buy')
                    ? 'bg-emerald-500/20 text-emerald-500'
                    : rec.includes('sell') || rec.includes('underperform')
                        ? 'bg-rose-500/20 text-rose-500'
                        : 'bg-amber-500/20 text-amber-500';
                return (
                    <span className={`inline-flex px-2 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter ${cls}`}>
                        {s.recommendation.replace(/_/g, ' ').toUpperCase()}
                    </span>
                );
            },
        },
        {
            label: 'Prognoza AI', hint: 'zmiana ceny',
            rawNums: stocks.map(s => s.prediction?.trend_pct ?? null),
            higherIsBetter: true,
            render: (s, _, isBest) => {
                if (!s.prediction) {
                    return <div className="h-4 w-12 mx-auto bg-slate-500/20 animate-pulse rounded"></div>;
                }
                const { predicted_price, trend, trend_pct } = s.prediction;
                const colorClass = isBest ? 'text-emerald-500'
                    : trend === 'up' ? 'text-emerald-500'
                    : trend === 'down' ? 'text-rose-500'
                    : 'text-slate-400';
                return (
                    <div className="flex flex-col items-center">
                        <div className={`font-mono text-sm font-bold flex items-center gap-1 ${colorClass}`}>
                            {predicted_price.toFixed(2)}
                            {trend === 'up' ? <ArrowUpRight size={14} /> : trend === 'down' ? <ArrowDownRight size={14} /> : null}
                        </div>
                        <div className="text-[9px] font-bold opacity-60">
                            {trend_pct > 0 ? '+' : ''}{trend_pct}%
                            {isBest && <span className="ml-1">★</span>}
                        </div>
                    </div>
                );
            },
        },
        {
            label: 'Jakość', hint: 'wyższe = lepsze',
            rawNums: scores,
            higherIsBetter: true,
            render: (_, i, isBest) => {
                const score = scores[i];
                const cls = score >= 75 ? 'text-emerald-500' : score >= 50 ? 'text-amber-500' : 'text-slate-500';
                return (
                    <div className="flex flex-col items-center gap-1">
                        <span className={`text-sm font-black ${isBest ? 'text-emerald-500' : cls}`}>
                            {score}/100{isBest && <span className="ml-1 text-[10px]">★</span>}
                        </span>
                        <div className={`w-16 h-1 rounded-full overflow-hidden ${isDarkMode ? 'bg-slate-700' : 'bg-slate-200'}`}>
                            <div
                                className={`h-full ${score >= 75 ? 'bg-emerald-500' : score >= 50 ? 'bg-amber-500' : 'bg-slate-500'}`}
                                style={{ width: `${score}%` }}
                            />
                        </div>
                    </div>
                );
            },
        },
    ];

    return (
        <div>
        <button
            onClick={onBack}
            className={`mb-4 flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-xl transition-all hover:scale-105 active:scale-95 ${isDarkMode ? 'bg-slate-800 text-slate-300 border border-white/5 hover:text-white' : 'bg-white text-slate-600 border border-slate-200 shadow-sm hover:text-slate-900'}`}
        >
            <ArrowLeft size={16} />
            Widok Rynku
        </button>
        <div className={`rounded-3xl overflow-hidden border ${isDarkMode ? 'bg-slate-900/50 border-white/10' : 'bg-white border-slate-200'}`}>
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead>
                        <tr className={`border-b ${isDarkMode ? 'border-white/5' : 'border-slate-100'}`}>
                            <th className={`px-6 py-5 text-left w-40 text-[10px] font-bold uppercase tracking-[0.2em] sticky left-0 z-10 ${isDarkMode ? 'text-slate-500 bg-slate-900' : 'text-slate-400 bg-white'}`}>
                                Wskaźnik
                            </th>
                            {stocks.map(s => (
                                <th key={s.ticker} className="px-6 py-5 text-center min-w-[170px]">
                                    <div className="flex flex-col items-center gap-1.5">
                                        <div className="flex items-center gap-1.5">
                                            <span className="font-bold text-sm">{s.name}</span>
                                            <button
                                                onClick={() => onRemove(s.ticker)}
                                                className={`rounded-full p-0.5 opacity-30 hover:opacity-80 transition-opacity ${isDarkMode ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}
                                            >
                                                <X size={12} />
                                            </button>
                                        </div>
                                        <span className={`text-[10px] font-bold uppercase tracking-wider ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                                            {s.ticker}{s.sector && s.sector !== 'UNKNOWN' ? ` · ${s.sector}` : ''}
                                        </span>
                                    </div>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map(row => {
                            const best = findBest(row.rawNums, row.higherIsBetter);
                            return (
                                <tr key={row.label} className={`border-b last:border-0 ${isDarkMode ? 'border-white/5' : 'border-slate-50'}`}>
                                    <td className={`px-6 py-4 sticky left-0 z-10 ${isDarkMode ? 'text-slate-400 bg-slate-900' : 'text-slate-500 bg-white'}`}>
                                        <div className="text-xs font-bold uppercase tracking-wider">{row.label}</div>
                                        {row.hint && <div className="text-[10px] opacity-40 mt-0.5">{row.hint}</div>}
                                    </td>
                                    {stocks.map((s, si) => {
                                        const isBest = best === si;
                                        return (
                                            <td
                                                key={s.ticker}
                                                className={`px-6 py-4 text-center ${isBest ? (isDarkMode ? 'bg-emerald-500/5' : 'bg-emerald-50/50') : ''}`}
                                            >
                                                {row.render(s, si, isBest)}
                                            </td>
                                        );
                                    })}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
        </div>
    );
}
