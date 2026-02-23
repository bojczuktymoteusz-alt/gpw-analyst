import React, { useState, useMemo } from 'react';
import { Stock } from '../types';
import { ArrowUpRight, ArrowDownRight, Activity, ChevronUp, ChevronDown, Search } from 'lucide-react';

interface StockTableProps {
    stocks: Stock[];
}

type SortKey = keyof Stock | 'quality_score' | 'trend_pct';
type SortDirection = 'asc' | 'desc';

const StockTable: React.FC<StockTableProps> = ({ stocks }) => {
    const [sortKey, setSortKey] = useState<SortKey | null>(null);
    const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
    // Nowy stan dla wyszukiwarki
    const [searchTerm, setSearchTerm] = useState('');

    const formatMarketCap = (cap?: number) => {
        if (!cap) return 'N/A';
        if (cap >= 1e9) return `${(cap / 1e9).toFixed(2)}B`;
        if (cap >= 1e6) return `${(cap / 1e6).toFixed(2)}M`;
        return cap.toString();
    };

    const calculateQualityScore = (stock: Stock) => {
        let score = 0;
        if (stock.pe > 0 && stock.pe < 15) score += 25;
        if (stock.pbv > 0 && stock.pbv < 2) score += 25;
        if (stock.roe > 0.15) score += 25;
        if (stock.div_yield > 0.04) score += 25;
        if (stock.beta && stock.beta < 1.0) score = Math.min(100, score + 5);
        return score;
    };

    const handleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
        } else {
            setSortKey(key);
            setSortDirection('desc');
        }
    };

    // Zmodyfikowany useMemo: najpierw filtruje (Search), potem sortuje
    const processedStocks = useMemo(() => {
        // 1. Filtrowanie po tekście
        let result = stocks;
        if (searchTerm.trim() !== '') {
            const lowerTerm = searchTerm.toLowerCase();
            result = result.filter(stock =>
                stock.name.toLowerCase().includes(lowerTerm) ||
                stock.ticker.toLowerCase().includes(lowerTerm) ||
                (stock.sector && stock.sector.toLowerCase().includes(lowerTerm))
            );
        }

        // 2. Sortowanie wyników
        if (sortKey) {
            result = [...result].sort((a, b) => {
                let aValue: any = a[sortKey as keyof Stock];
                let bValue: any = b[sortKey as keyof Stock];

                if (sortKey === 'quality_score') {
                    aValue = calculateQualityScore(a);
                    bValue = calculateQualityScore(b);
                } else if (sortKey === 'trend_pct') {
                    aValue = a.prediction?.trend_pct ?? -999;
                    bValue = b.prediction?.trend_pct ?? -999;
                }

                if (aValue === undefined || aValue === null) aValue = -999999;
                if (bValue === undefined || bValue === null) bValue = -999999;

                if (aValue < bValue) return sortDirection === 'asc' ? -1 : 1;
                if (aValue > bValue) return sortDirection === 'asc' ? 1 : -1;
                return 0;
            });
        }

        return result;
    }, [stocks, sortKey, sortDirection, searchTerm]);

    const SortIcon = ({ columnKey }: { columnKey: SortKey }) => {
        if (sortKey !== columnKey) return <div className="w-4 h-4 inline-block ml-1 opacity-0 group-hover/th:opacity-50 transition-opacity"><ChevronDown size={14} /></div>;
        return sortDirection === 'asc' ?
            <ChevronUp size={14} className="inline-block ml-1 text-indigo-500" /> :
            <ChevronDown size={14} className="inline-block ml-1 text-indigo-500" />;
    };

    return (
        <div className="relative group overflow-hidden rounded-3xl border border-white/10 shadow-2xl bg-white/5 backdrop-blur-sm">
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-purple-500/5 pointer-events-none"></div>

            {/* --- NOWA SEKCJA: Pasek Wyszukiwarki --- */}
            <div className="relative border-b border-white/10 p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="relative w-full sm:max-w-xs">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 opacity-40" size={16} />
                    <input
                        type="text"
                        placeholder="Szukaj spółki, symbolu lub branży..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full bg-black/5 dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-xl py-2.5 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all placeholder:opacity-50"
                    />
                </div>
                <div className="text-xs font-semibold opacity-50 px-2">
                    Znaleziono: {processedStocks.length}
                </div>
            </div>
            {/* --------------------------------------- */}

            <div className="overflow-x-auto">
                <table className="min-w-full text-left border-collapse tabular-nums">
                    <thead>
                        <tr className="border-b border-white/10 bg-black/5 dark:bg-white/5 select-none">
                            <th onClick={() => handleSort('ticker')} className="px-6 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors whitespace-nowrap">Symbol <SortIcon columnKey="ticker" /></th>
                            <th onClick={() => handleSort('price')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-right whitespace-nowrap">Cena <SortIcon columnKey="price" /></th>
                            <th onClick={() => handleSort('market_cap')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-right whitespace-nowrap hidden lg:table-cell">Kapit. <SortIcon columnKey="market_cap" /></th>
                            <th onClick={() => handleSort('pe')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-right whitespace-nowrap">C/Z <SortIcon columnKey="pe" /></th>
                            <th onClick={() => handleSort('pbv')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-right whitespace-nowrap hidden md:table-cell">C/WK <SortIcon columnKey="pbv" /></th>
                            <th onClick={() => handleSort('roe')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-right whitespace-nowrap hidden md:table-cell">ROE <SortIcon columnKey="roe" /></th>
                            <th onClick={() => handleSort('operating_margin')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-right whitespace-nowrap hidden lg:table-cell">Marża Op. <SortIcon columnKey="operating_margin" /></th>
                            <th className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-50 text-right whitespace-nowrap">Dług/EBITDA</th>
                            <th onClick={() => handleSort('recommendation')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-center whitespace-nowrap">Sygnał <SortIcon columnKey="recommendation" /></th>
                            <th onClick={() => handleSort('trend_pct')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-center whitespace-nowrap">Prognoza AI <SortIcon columnKey="trend_pct" /></th>
                            <th onClick={() => handleSort('quality_score')} className="px-4 py-4 text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 cursor-pointer group/th hover:text-indigo-500 transition-colors text-center whitespace-nowrap">Jakość <SortIcon columnKey="quality_score" /></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                        {processedStocks.map((stock) => {
                            const score = calculateQualityScore(stock);
                            return (
                                <tr key={stock.ticker} className="group/row hover:bg-indigo-500/5 transition-all duration-300">
                                    <td className="px-6 py-3">
                                        <div className="flex items-center gap-3">
                                            <div className="h-9 w-9 shrink-0 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-500 group-hover/row:scale-110 transition-transform">
                                                <Activity size={16} />
                                            </div>
                                            <div className="min-w-0">
                                                <div className="font-bold text-sm lg:text-base tracking-tight truncate">{stock.name}</div>
                                                <div className="text-[10px] font-semibold opacity-40 uppercase tracking-wider truncate">{stock.ticker} • {stock.sector}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <div className="font-mono font-bold text-sm lg:text-base">{stock.price?.toFixed(2) ?? '0.00'}</div>
                                        <div className="text-[9px] opacity-40 font-medium whitespace-nowrap">Akt.: {stock.last_updated ? new Date(stock.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</div>
                                    </td>
                                    <td className="px-4 py-3 text-right hidden lg:table-cell">
                                        <span className="font-mono font-bold text-sm text-slate-500 dark:text-slate-400">{formatMarketCap(stock.market_cap)}</span>
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <div className="flex flex-col items-end gap-1">
                                            <span className={`px-2 py-0.5 rounded-md font-mono font-bold text-xs ${stock.pe && stock.pe > 15 ? 'text-amber-500 bg-amber-500/10' : stock.pe && stock.pe > 0 ? 'text-emerald-500 bg-emerald-500/10' : 'text-slate-500'}`}>
                                                {stock.pe && stock.pe > 0 ? stock.pe?.toFixed(1) : '—'}
                                            </span>
                                            {stock.sector_pe_avg && stock.pe > 0 && (
                                                <div className={`text-[9px] font-bold flex items-center gap-0.5 ${stock.pe < stock.sector_pe_avg ? 'text-emerald-500' : 'text-amber-500'}`}>
                                                    {stock.pe < stock.sector_pe_avg ? <ArrowDownRight size={10} className="rotate-45" /> : <ArrowUpRight size={10} className="-rotate-45" />}
                                                    Sek: {stock.sector_pe_avg.toFixed(1)}
                                                </div>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-right font-mono font-bold text-sm text-slate-500 dark:text-slate-400 hidden md:table-cell">
                                        {stock.pbv?.toFixed(2) ?? '—'}
                                    </td>
                                    <td className="px-4 py-3 text-right hidden md:table-cell">
                                        <div className="flex flex-col items-end">
                                            <div className={`font-mono font-bold text-sm flex items-center gap-1 ${(stock.roe ?? 0) > 0.1 ? 'text-emerald-500' : 'text-slate-500'}`}>
                                                {stock.roe ? (stock.roe * 100).toFixed(1) : '—'}%
                                                {(stock.roe ?? 0) > 0.1 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-right hidden lg:table-cell">
                                        <div className="flex flex-col items-end gap-1">
                                            <span className={`px-2 py-0.5 rounded-md font-mono font-bold text-xs ${stock.operating_margin && stock.sector_margin_avg && stock.operating_margin > stock.sector_margin_avg ? 'text-emerald-500 bg-emerald-500/10' : stock.operating_margin ? 'text-slate-500 bg-slate-500/10' : 'text-slate-500'}`}>
                                                {stock.operating_margin ? (stock.operating_margin * 100).toFixed(1) : '—'}%
                                            </span>
                                            {stock.sector_margin_avg && (stock.operating_margin ?? 0) > 0 && (
                                                <div className={`text-[9px] font-bold flex items-center gap-0.5 ${(stock.operating_margin ?? 0) > stock.sector_margin_avg ? 'text-emerald-500' : 'text-amber-500'}`}>
                                                    {(stock.operating_margin ?? 0) > stock.sector_margin_avg ? <ArrowUpRight size={10} className="-rotate-45" /> : <ArrowDownRight size={10} className="rotate-45" />}
                                                    Sek: {(stock.sector_margin_avg * 100).toFixed(1)}%
                                                </div>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        {(() => {
                                            const netDebt = (stock.total_debt || 0) - (stock.total_cash || 0);
                                            const ratio = stock.ebitda && stock.ebitda > 0 ? netDebt / stock.ebitda : null;

                                            if (ratio === null) return <span className="text-[10px] font-bold opacity-20 uppercase">N/A</span>;

                                            let colorClass = 'text-emerald-500 bg-emerald-500/10';
                                            if (ratio > 4) colorClass = 'text-rose-500 bg-rose-500/10';
                                            else if (ratio > 2.5) colorClass = 'text-amber-500 bg-amber-500/10';

                                            return (
                                                <span className={`px-2 py-0.5 rounded-md font-mono font-bold text-xs ${colorClass}`}>
                                                    {ratio.toFixed(2)}x
                                                </span>
                                            );
                                        })()}
                                    </td>
                                    <td className="px-4 py-3 text-center">
                                        {stock.recommendation && stock.recommendation !== 'none' ? (
                                            <span className={`inline-flex items-center px-2 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter ${stock.recommendation.toLowerCase().includes('buy') ? 'bg-emerald-500/20 text-emerald-500' :
                                                stock.recommendation.toLowerCase().includes('sell') || stock.recommendation.toLowerCase().includes('underperform') ? 'bg-rose-500/20 text-rose-500' :
                                                    'bg-amber-500/20 text-amber-500'
                                                }`}>
                                                {stock.recommendation.split('_')[0]}
                                            </span>
                                        ) : (
                                            <span className="text-[10px] font-bold opacity-20 uppercase">N/A</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-center">
                                        {stock.prediction ? (
                                            <div className="flex flex-col items-center">
                                                <div className={`font-mono text-xs font-bold flex items-center gap-1 ${stock.prediction.trend === 'up' ? 'text-emerald-500' : stock.prediction.trend === 'down' ? 'text-rose-500' : 'text-slate-400'}`}>
                                                    {stock.prediction.predicted_price.toFixed(2)}
                                                    {stock.prediction.trend === 'up' ? <ArrowUpRight size={14} /> : stock.prediction.trend === 'down' ? <ArrowDownRight size={14} /> : null}
                                                </div>
                                                <div className={`text-[9px] font-bold opacity-60`}>
                                                    {stock.prediction.trend_pct > 0 ? '+' : ''}{stock.prediction.trend_pct}%
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="flex justify-center w-full">
                                                <div className="h-4 w-12 bg-slate-500/20 animate-pulse rounded"></div>
                                            </div>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-center">
                                        <div className="flex flex-col items-center gap-1.5">
                                            <div className={`text-[10px] font-black ${score >= 75 ? 'text-emerald-500' : score >= 50 ? 'text-amber-500' : 'text-slate-500'}`}>
                                                {score}/100
                                            </div>
                                            <div className="w-12 h-1 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                                <div
                                                    className={`h-full transition-all duration-500 ${score >= 75 ? 'bg-emerald-500' : score >= 50 ? 'bg-amber-500' : 'bg-slate-500'}`}
                                                    style={{ width: `${score}%` }}
                                                ></div>
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}

                        {/* Komunikat o braku wyników wyszukiwania */}
                        {processedStocks.length === 0 && stocks.length > 0 && (
                            <tr>
                                <td colSpan={11} className="py-12 text-center text-sm font-medium opacity-50">
                                    Nie znaleziono spółek pasujących do "{searchTerm}"
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>

                {stocks.length === 0 && (
                    <div className="py-24 flex flex-col items-center justify-center text-center">
                        <div className="animate-pulse text-indigo-500 mb-4">
                            <Activity size={48} />
                        </div>
                        <h3 className="text-xl font-bold mb-1">Przetwarzanie Danych Rynkowych</h3>
                        <p className="text-sm opacity-50">Proszę czekać, nasze algorytmy przetwarzają najnowsze informacje.</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default StockTable;