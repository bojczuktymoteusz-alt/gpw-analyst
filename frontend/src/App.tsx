import { useEffect, useState } from 'react';
import StockTable from './components/StockTable';
import { Stock } from './types';
import { LayoutDashboard, Moon, Sun, RefreshCw, TrendingUp, Activity } from 'lucide-react';

function App() {
    const [stocks, setStocks] = useState<Stock[]>([]);
    const [isDarkMode, setIsDarkMode] = useState(false);
    const [loading, setLoading] = useState(false);
    const [isPredicting, setIsPredicting] = useState(false); // Nowy stan dla ładowania AI w tle

    useEffect(() => {
        fetchStocks();
    }, []);

    const fetchStocks = async () => {
        setLoading(true);
        try {
            // 1. Błyskawiczne pobranie głównych danych rynkowych
            const response = await fetch('/api/stocks');
            if (!response.ok) throw new Error('Failed to fetch stocks');
            const data: Stock[] = await response.json();

            // Ustawiamy podstawowe dane i natychmiast ZDEJMUJEMY loader ze szronionym szkłem
            setStocks(data);
            setLoading(false);

            // 2. Uruchamiamy proces przewidywania AI w tle (Progressive Loading)
            setIsPredicting(true);

            // Pobieramy prognozy SEKWENCYJNIE (jedna po drugiej), by nie zablokowało nas Yahoo
            for (const stock of data) {
                try {
                    const predRes = await fetch(`/api/stock/${stock.ticker}/predict`);
                    if (predRes.ok) {
                        const prediction = await predRes.json();
                        // Aktualizujemy tabelę na bieżąco, spółka po spółce!
                        setStocks(prevStocks => prevStocks.map(s =>
                            s.ticker === stock.ticker ? { ...s, prediction } : s
                        ));
                    }
                } catch (e) {
                    console.error(`Prediction error for ${stock.ticker}:`, e);
                }

                // Dodajemy sztuczne opóźnienie 300ms, aby oszukać limity zapytań Yahoo Finance
                await new Promise(resolve => setTimeout(resolve, 300));
            }

        } catch (error) {
            console.error("Error fetching stocks:", error);
            setLoading(false);
        } finally {
            setIsPredicting(false);
        }
    };

    return (
        <div className={`min-h-screen transition-colors duration-500 ${isDarkMode ? 'bg-[#0b0f1a] text-slate-100' : 'bg-[#f8fafc] text-slate-900'}`}>
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className={`absolute -top-[10%] -left-[10%] w-[40%] h-[40%] rounded-full blur-[120px] opacity-20 ${isDarkMode ? 'bg-indigo-500' : 'bg-indigo-300'}`}></div>
                <div className={`absolute top-[40%] -right-[10%] w-[30%] h-[30%] rounded-full blur-[120px] opacity-10 ${isDarkMode ? 'bg-purple-500' : 'bg-purple-300'}`}></div>
            </div>

            <header className={`sticky top-0 z-40 backdrop-blur-xl border-b transition-colors duration-300 ${isDarkMode ? 'bg-slate-900/50 border-white/5' : 'bg-white/50 border-slate-200'}`}>
                <div className="container mx-auto px-6 h-20 flex items-center justify-between">
                    <div className="flex items-center gap-3 group cursor-pointer">
                        <div className="relative">
                            <div className="absolute inset-0 bg-indigo-600 blur-lg opacity-40 group-hover:opacity-60 transition-opacity"></div>
                            <div className="relative bg-gradient-to-br from-indigo-500 to-purple-600 p-2.5 rounded-xl text-white shadow-xl shadow-indigo-500/20">
                                <TrendingUp size={24} />
                            </div>
                        </div>
                        <div>
                            <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 to-purple-500">
                                GPW Analyst
                            </h1>
                            <p className="text-[10px] font-bold tracking-[0.2em] uppercase opacity-50 -mt-1">Version 2.0</p>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        {/* Kręci się, gdy ładujemy dane ATAKŻE gdy w tle liczy się AI */}
                        <button
                            onClick={fetchStocks}
                            disabled={loading || isPredicting}
                            className={`relative p-2.5 rounded-xl hover:scale-105 transition-all active:scale-95 overflow-hidden ${isDarkMode ? 'bg-slate-800 text-slate-300 border border-white/5' : 'bg-white text-slate-600 border border-slate-200 shadow-sm'}`}
                        >
                            {(loading || isPredicting) && <div className="absolute inset-0 bg-indigo-500/10 animate-pulse"></div>}
                            <RefreshCw size={20} className={(loading || isPredicting) ? 'animate-spin text-indigo-500' : ''} />
                        </button>
                        <button
                            onClick={() => setIsDarkMode(!isDarkMode)}
                            className={`p-2.5 rounded-xl hover:scale-105 transition-all active:scale-95 ${isDarkMode ? 'bg-slate-800 text-amber-400 border border-white/5' : 'bg-white text-indigo-600 border border-slate-200 shadow-sm'}`}
                        >
                            {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
                        </button>
                    </div>
                </div>
            </header>

            <main className="container mx-auto px-6 py-12 relative z-10">
                <div className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <div className="h-1 w-12 bg-indigo-500 rounded-full"></div>
                            <span className="text-xs font-bold uppercase tracking-widest text-indigo-500">Rynek na Żywo</span>
                            {/* Subtelny wskaźnik pracy AI */}
                            {isPredicting && (
                                <span className="text-[10px] font-bold uppercase text-indigo-400 animate-pulse ml-2 flex items-center gap-1">
                                    <Activity size={12} /> Przeliczanie AI...
                                </span>
                            )}
                        </div>
                        <h2 className="text-4xl font-extrabold tracking-tight mb-2">Analiza Rynku</h2>
                        <p className={`${isDarkMode ? 'text-slate-400' : 'text-slate-500'} max-w-lg`}>
                            Zaawansowana analityka i dane w czasie rzeczywistym z Giełdy Papierów Wartościowych. Monitoruj wyniki i wskaźniki wyceny.
                        </p>
                    </div>

                    <div className={`p-1 rounded-2xl flex gap-1 ${isDarkMode ? 'bg-slate-800/50' : 'bg-slate-200/50'}`}>
                        <div className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all shadow-sm ${isDarkMode ? 'bg-indigo-600 text-white' : 'bg-white text-indigo-600'}`}>Widok Rynku</div>
                        <div className={`px-4 py-2 rounded-xl text-sm font-semibold opacity-50 cursor-not-allowed`}>Porównanie</div>
                    </div>
                </div>

                <div className="relative animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">

                    {/* Główny loader pojawia się tylko przy pobieraniu głównych danych rynkowych */}
                    {loading && (
                        <div className={`absolute inset-0 z-50 flex items-center justify-center backdrop-blur-sm rounded-3xl border transition-all duration-500 ${isDarkMode ? 'bg-[#0b0f1a]/60 border-white/10' : 'bg-white/40 border-slate-200/50'}`}>
                            <div className={`flex flex-col items-center p-8 rounded-3xl shadow-2xl border transform scale-100 animate-in zoom-in-95 duration-300 ${isDarkMode ? 'bg-slate-900 border-white/10 text-white' : 'bg-white border-slate-200 text-slate-800'}`}>
                                <div className="relative flex items-center justify-center w-16 h-16 mb-5">
                                    <div className="absolute inset-0 border-4 border-indigo-500/20 rounded-full"></div>
                                    <div className="absolute inset-0 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
                                    <Activity className="absolute text-indigo-500 animate-pulse" size={24} />
                                </div>
                                <h3 className="text-sm font-bold tracking-wide">Synchronizacja z rynkiem...</h3>
                                <p className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-50 mt-2 text-indigo-500">yFinance API / Podstawowe Dane</p>
                            </div>
                        </div>
                    )}

                    <StockTable stocks={stocks} />
                </div>
            </main>

            <footer className={`py-12 border-t transition-colors duration-300 ${isDarkMode ? 'border-white/5 text-slate-500' : 'border-slate-200 text-slate-400'}`}>
                <div className="container mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
                    <p className="text-sm font-medium">&copy; {new Date().getFullYear()} GPW Analyst V2. Inteligencja klasy terminalowej.</p>
                    <div className="flex gap-6 text-xs font-bold uppercase tracking-widest">
                        <a href="#" className="hover:text-indigo-500 transition-colors">Dokumentacja</a>
                        <a href="#" className="hover:text-indigo-500 transition-colors">Wsparcie</a>
                    </div>
                </div>
            </footer>
        </div>
    );
}

export default App;