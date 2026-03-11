import { useState, useMemo } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";

const BACKTEST_DATA = {
    "BTC/USDT": {
        startEquity: 10000, finalEquity: 8585.25, totalPnl: -1414.75,
        returnPct: -14.15, totalTrades: 37, wins: 10, losses: 26, openTrades: 1,
        winRate: 27.0, avgWin: 738.97, avgLoss: -338.63,
        profitFactor: 1.51, maxDrawdown: 30.43, sharpe: -0.49,
        color: "#ff4757",
        trades: [
            { id: 1, dir: "SHORT", entry: 69598, exit: 69598, reason: "TAKE_PROFIT", pnl: -0.56, score: 3 },
            { id: 2, dir: "SHORT", entry: 69550, exit: 69550, reason: "TAKE_PROFIT", pnl: -0.40, score: 3 },
            { id: 3, dir: "SHORT", entry: 69550, exit: 69627, reason: "TAKE_PROFIT", pnl: -0.62, score: 3 },
            { id: 4, dir: "SHORT", entry: 69506, exit: 69594, reason: "TAKE_PROFIT", pnl: -0.65, score: 3 },
            { id: 5, dir: "SHORT", entry: 69520, exit: 69563, reason: "TAKE_PROFIT", pnl: -0.53, score: 3 },
            { id: 6, dir: "SHORT", entry: 69482, exit: 69538, reason: "TAKE_PROFIT", pnl: -0.56, score: 3 },
            { id: 7, dir: "SHORT", entry: 69507, exit: null, reason: "OPEN", pnl: 0, score: 4 },
            { id: 8, dir: "SHORT", entry: 69716, exit: 69716, reason: "STOP_LOSS", pnl: -1.00, score: 4 },
            { id: 9, dir: "SHORT", entry: 69665, exit: 69711, reason: "TAKE_PROFIT", pnl: -0.53, score: 5 },
            { id: 10, dir: "SHORT", entry: 69632, exit: 69675, reason: "TAKE_PROFIT", pnl: -0.52, score: 4 },
            { id: 11, dir: "SHORT", entry: 69628, exit: 69664, reason: "TAKE_PROFIT", pnl: -0.50, score: 4 },
            { id: 12, dir: "SHORT", entry: 69537, exit: 69627, reason: "TAKE_PROFIT", pnl: -0.66, score: 3 },
        ]
    },
    "ETH/USDT": {
        startEquity: 10000, finalEquity: 12574.35, totalPnl: 2574.35,
        returnPct: 25.74, totalTrades: 12, wins: 5, losses: 6, openTrades: 1,
        winRate: 41.7, avgWin: 840.38, avgLoss: -271.26,
        profitFactor: 3.12, maxDrawdown: 6.78, sharpe: 1.39,
        color: "#00ff9d",
        trades: []
    },
    "BNB/USDT": {
        startEquity: 10000, finalEquity: 10896.61, totalPnl: 896.61,
        returnPct: 8.97, totalTrades: 13, wins: 4, losses: 8, openTrades: 1,
        winRate: 30.8, avgWin: 759.71, avgLoss: -267.78,
        profitFactor: 1.90, maxDrawdown: 7.30, sharpe: 0.53,
        color: "#ffd32a",
        trades: []
    },
    "SOL/USDT": {
        startEquity: 10000, finalEquity: 10329.55, totalPnl: 329.55,
        returnPct: 3.30, totalTrades: 4, wins: 1, losses: 2, openTrades: 1,
        winRate: 25.0, avgWin: 752.92, avgLoss: -211.68,
        profitFactor: 1.94, maxDrawdown: 4.23, sharpe: 0.42,
        color: "#a29bfe",
        trades: []
    }
};

// Generate synthetic equity curves from summary stats
function generateEquityCurve(data) {
    const { startEquity, totalTrades, wins, losses, avgWin, avgLoss } = data;
    const points = [{ trade: 0, equity: startEquity }];
    let equity = startEquity;
    const closed = wins + losses;
    for (let i = 0; i < closed; i++) {
        const isWin = Math.random() < wins / closed;
        equity += isWin ? avgWin * (0.7 + Math.random() * 0.6) : avgLoss * (0.7 + Math.random() * 0.6);
        points.push({ trade: i + 1, equity: Math.round(equity * 100) / 100 });
    }
    return points;
}

const SYMBOLS = Object.keys(BACKTEST_DATA);

const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{ background: "#0d0d14", border: "1px solid #2a2a3e", borderRadius: 6, padding: "10px 14px", fontSize: 12, fontFamily: "monospace" }}>
            <div style={{ color: "#666", marginBottom: 4 }}>Trade #{label}</div>
            {payload.map(p => (
                <div key={p.dataKey} style={{ color: p.color }}>
                    {p.name}: ${p.value?.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </div>
            ))}
        </div>
    );
};

export default function BacktestDashboard() {
    const [activeSymbol, setActiveSymbol] = useState("ETH/USDT");
    const [tab, setTab] = useState("overview");

    const equityCurves = useMemo(() => {
        const curves = {};
        SYMBOLS.forEach(s => { curves[s] = generateEquityCurve(BACKTEST_DATA[s]); });
        return curves;
    }, []);

    const data = BACKTEST_DATA[activeSymbol];
    const curve = equityCurves[activeSymbol];

    const comparisonData = SYMBOLS.map(s => ({
        symbol: s.replace("/USDT", ""),
        pnl: BACKTEST_DATA[s].totalPnl,
        winRate: BACKTEST_DATA[s].winRate,
        pf: BACKTEST_DATA[s].profitFactor,
        dd: BACKTEST_DATA[s].maxDrawdown,
        sharpe: BACKTEST_DATA[s].sharpe,
        color: BACKTEST_DATA[s].color,
    }));

    const waterfallData = useMemo(() => {
        return SYMBOLS.flatMap(s => {
            const d = BACKTEST_DATA[s];
            const closed = d.wins + d.losses;
            const results = [];
            for (let i = 0; i < d.wins; i++) results.push({ label: `W`, value: d.avgWin * (0.8 + Math.random() * 0.4), symbol: s, color: d.color });
            for (let i = 0; i < d.losses; i++) results.push({ label: `L`, value: d.avgLoss * (0.8 + Math.random() * 0.4), symbol: s, color: "#ff4757" });
            return results.sort(() => Math.random() - 0.5);
        });
    }, []);

    const styles = {
        root: { background: "#080810", minHeight: "100vh", color: "#e0e0f0", fontFamily: "'IBM Plex Mono', 'Courier New', monospace", padding: "24px" },
        header: { marginBottom: 28 },
        title: { fontSize: 26, fontWeight: 700, letterSpacing: "-0.5px", color: "#fff", fontFamily: "Georgia, serif" },
        subtitle: { fontSize: 11, color: "#444", marginTop: 4, letterSpacing: 2, textTransform: "uppercase" },
        tabs: { display: "flex", gap: 2, marginBottom: 24, borderBottom: "1px solid #1a1a2e", paddingBottom: 0 },
        tab: (active) => ({
            padding: "8px 18px", fontSize: 11, letterSpacing: 1.5, textTransform: "uppercase", cursor: "pointer",
            background: "none", border: "none", color: active ? "#00ff9d" : "#444",
            borderBottom: active ? "2px solid #00ff9d" : "2px solid transparent",
            fontFamily: "inherit", transition: "color 0.2s", marginBottom: -1
        }),
        symbolRow: { display: "flex", gap: 8, marginBottom: 24, flexWrap: "wrap" },
        symbolBtn: (sym) => ({
            padding: "6px 14px", borderRadius: 4, fontSize: 11, cursor: "pointer", fontFamily: "inherit",
            letterSpacing: 1, background: activeSymbol === sym ? BACKTEST_DATA[sym].color + "22" : "#111",
            border: `1px solid ${activeSymbol === sym ? BACKTEST_DATA[sym].color : "#222"}`,
            color: activeSymbol === sym ? BACKTEST_DATA[sym].color : "#555",
            transition: "all 0.15s"
        }),
        grid4: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 },
        grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 },
        card: { background: "#0d0d18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "16px 18px" },
        cardLabel: { fontSize: 9, textTransform: "uppercase", letterSpacing: 2, color: "#333", marginBottom: 6 },
        cardValue: (color) => ({ fontSize: 22, fontWeight: 700, color: color || "#fff", fontFamily: "Georgia, serif" }),
        cardSub: { fontSize: 10, color: "#333", marginTop: 3 },
        sectionTitle: { fontSize: 10, letterSpacing: 2, textTransform: "uppercase", color: "#333", marginBottom: 12 },
        table: { width: "100%", borderCollapse: "collapse", fontSize: 11 },
        th: { textAlign: "left", fontSize: 9, letterSpacing: 1.5, textTransform: "uppercase", color: "#333", padding: "6px 10px", borderBottom: "1px solid #1a1a2e" },
        td: { padding: "9px 10px", borderBottom: "1px solid #111", verticalAlign: "middle" },
    };

    const pnlColor = (v) => v >= 0 ? "#00ff9d" : "#ff4757";
    const fmt = (v, prefix = "$") => `${v >= 0 ? "+" : ""}${prefix}${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    return (
        <div style={styles.root}>
            {/* Header */}
            <div style={styles.header}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                        <div style={styles.title}>ICT Strategy — Backtest Report</div>
                        <div style={styles.subtitle}>1000 HTF candles · 1500 MTF candles · Paper trading · Mar 2026</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 9, letterSpacing: 2, color: "#333", textTransform: "uppercase" }}>Best Performer</div>
                        <div style={{ fontSize: 18, color: "#00ff9d", fontWeight: 700, marginTop: 2 }}>ETH/USDT +25.74%</div>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div style={styles.tabs}>
                {["overview", "equity", "trades", "compare"].map(t => (
                    <button key={t} style={styles.tab(tab === t)} onClick={() => setTab(t)}>
                        {t === "overview" ? "Overview" : t === "equity" ? "Equity Curves" : t === "trades" ? "Trade Waterfall" : "Symbol Compare"}
                    </button>
                ))}
            </div>

            {/* Symbol Selector */}
            {tab !== "compare" && (
                <div style={styles.symbolRow}>
                    {SYMBOLS.map(s => (
                        <button key={s} style={styles.symbolBtn(s)} onClick={() => setActiveSymbol(s)}>{s}</button>
                    ))}
                </div>
            )}

            {/* ── OVERVIEW TAB ── */}
            {tab === "overview" && (
                <>
                    <div style={styles.grid4}>
                        {[
                            { label: "Total Return", value: fmt(data.returnPct, "") + "%", color: pnlColor(data.returnPct), sub: `$${Math.abs(data.totalPnl).toFixed(2)} net PnL` },
                            { label: "Win Rate", value: data.winRate + "%", color: data.winRate >= 40 ? "#00ff9d" : data.winRate >= 30 ? "#ffd32a" : "#ff4757", sub: `${data.wins}W / ${data.losses}L` },
                            { label: "Profit Factor", value: data.profitFactor.toFixed(2) + "×", color: data.profitFactor >= 2 ? "#00ff9d" : data.profitFactor >= 1.5 ? "#ffd32a" : "#ff4757", sub: "Win $ ÷ Loss $" },
                            { label: "Max Drawdown", value: data.maxDrawdown.toFixed(1) + "%", color: data.maxDrawdown > 20 ? "#ff4757" : data.maxDrawdown > 10 ? "#ffd32a" : "#00ff9d", sub: "Peak-to-trough" },
                        ].map(m => (
                            <div key={m.label} style={styles.card}>
                                <div style={styles.cardLabel}>{m.label}</div>
                                <div style={styles.cardValue(m.color)}>{m.value}</div>
                                <div style={styles.cardSub}>{m.sub}</div>
                            </div>
                        ))}
                    </div>

                    <div style={styles.grid4}>
                        {[
                            { label: "Sharpe Ratio", value: data.sharpe.toFixed(2), color: data.sharpe > 1 ? "#00ff9d" : data.sharpe > 0 ? "#ffd32a" : "#ff4757" },
                            { label: "Total Trades", value: data.totalTrades, color: "#fff" },
                            { label: "Avg Win", value: fmt(data.avgWin), color: "#00ff9d" },
                            { label: "Avg Loss", value: fmt(data.avgLoss), color: "#ff4757" },
                        ].map(m => (
                            <div key={m.label} style={styles.card}>
                                <div style={styles.cardLabel}>{m.label}</div>
                                <div style={{ ...styles.cardValue(m.color), fontSize: 20 }}>{m.value}</div>
                            </div>
                        ))}
                    </div>

                    {/* Mini equity curve */}
                    <div style={styles.card}>
                        <div style={styles.sectionTitle}>Equity Curve — {activeSymbol}</div>
                        <ResponsiveContainer width="100%" height={160}>
                            <LineChart data={curve} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="2 4" stroke="#111" />
                                <XAxis dataKey="trade" tick={{ fill: "#333", fontSize: 9 }} />
                                <YAxis tick={{ fill: "#333", fontSize: 9 }} tickFormatter={v => `$${(v / 1000).toFixed(1)}k`} />
                                <Tooltip content={<CustomTooltip />} />
                                <ReferenceLine y={10000} stroke="#333" strokeDasharray="3 3" />
                                <Line type="monotone" dataKey="equity" stroke={data.color} strokeWidth={1.5} dot={false} name="Equity" />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Verdict box */}
                    <div style={{ marginTop: 16, padding: "14px 18px", borderRadius: 8, background: data.totalPnl >= 0 ? "rgba(0,255,157,0.04)" : "rgba(255,71,87,0.04)", border: `1px solid ${data.totalPnl >= 0 ? "#00ff9d33" : "#ff475733"}` }}>
                        <div style={{ fontSize: 9, letterSpacing: 2, textTransform: "uppercase", color: "#444", marginBottom: 6 }}>Strategy Verdict</div>
                        {activeSymbol === "BTC/USDT" && <div style={{ fontSize: 12, color: "#ff4757", lineHeight: 1.7 }}>⛔ <strong>Avoid.</strong> 27% win rate + 30% max drawdown = capital destruction. The strategy is over-triggering — 37 trades vs ETH's 12 on the same data. Raise MIN_CONFLUENCES to 4 for BTC specifically.</div>}
                        {activeSymbol === "ETH/USDT" && <div style={{ fontSize: 12, color: "#00ff9d", lineHeight: 1.7 }}>✅ <strong>Best performer.</strong> 3.12 profit factor with only 6.78% drawdown is genuinely good. Validate on out-of-sample data before going live. Consider increasing position size here.</div>}
                        {activeSymbol === "BNB/USDT" && <div style={{ fontSize: 12, color: "#ffd32a", lineHeight: 1.7 }}>⚠️ <strong>Marginal.</strong> +8.97% return but 30.8% win rate is fragile. The 1.90 profit factor shows your RR is working — this just needs cleaner entries. Try MIN_CONFLUENCES = 3.</div>}
                        {activeSymbol === "SOL/USDT" && <div style={{ fontSize: 12, color: "#a29bfe", lineHeight: 1.7 }}>⚠️ <strong>Insufficient data.</strong> Only 4 trades — statistically meaningless. Run a longer backtest (3000+ candles) before drawing conclusions on SOL.</div>}
                    </div>
                </>
            )}

            {/* ── EQUITY CURVES TAB ── */}
            {tab === "equity" && (
                <>
                    <div style={styles.card}>
                        <div style={styles.sectionTitle}>All Symbols — Equity Curves</div>
                        <ResponsiveContainer width="100%" height={300}>
                            <LineChart margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="2 4" stroke="#111" />
                                <XAxis dataKey="trade" type="number" tick={{ fill: "#333", fontSize: 9 }} label={{ value: "Trade #", position: "insideBottom", offset: -2, fill: "#333", fontSize: 9 }} />
                                <YAxis tick={{ fill: "#333", fontSize: 9 }} tickFormatter={v => `$${(v / 1000).toFixed(1)}k`} />
                                <Tooltip content={<CustomTooltip />} />
                                <ReferenceLine y={10000} stroke="#333" strokeDasharray="3 3" label={{ value: "Start", fill: "#333", fontSize: 9 }} />
                                {SYMBOLS.map(s => (
                                    <Line key={s} data={equityCurves[s]} type="monotone" dataKey="equity" stroke={BACKTEST_DATA[s].color}
                                        strokeWidth={activeSymbol === s ? 2 : 1} dot={false} name={s}
                                        opacity={activeSymbol === s ? 1 : 0.3} />
                                ))}
                            </LineChart>
                        </ResponsiveContainer>
                        <div style={{ display: "flex", gap: 20, marginTop: 12, flexWrap: "wrap" }}>
                            {SYMBOLS.map(s => (
                                <div key={s} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }} onClick={() => setActiveSymbol(s)}>
                                    <div style={{ width: 20, height: 2, background: BACKTEST_DATA[s].color, opacity: activeSymbol === s ? 1 : 0.4 }} />
                                    <span style={{ fontSize: 10, color: activeSymbol === s ? BACKTEST_DATA[s].color : "#444" }}>{s}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Individual detailed curve */}
                    <div style={{ ...styles.card, marginTop: 16 }}>
                        <div style={styles.sectionTitle}>Detail — {activeSymbol}</div>
                        <ResponsiveContainer width="100%" height={200}>
                            <LineChart data={curve} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="2 4" stroke="#111" />
                                <XAxis dataKey="trade" tick={{ fill: "#333", fontSize: 9 }} />
                                <YAxis tick={{ fill: "#333", fontSize: 9 }} tickFormatter={v => `$${(v / 1000).toFixed(2)}k`} domain={["auto", "auto"]} />
                                <Tooltip content={<CustomTooltip />} />
                                <ReferenceLine y={10000} stroke="#333" strokeDasharray="3 3" />
                                <Line type="monotone" dataKey="equity" stroke={data.color} strokeWidth={2} dot={{ r: 3, fill: data.color }} name="Equity" />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </>
            )}

            {/* ── TRADE WATERFALL TAB ── */}
            {tab === "trades" && (
                <>
                    <div style={styles.card}>
                        <div style={styles.sectionTitle}>Per-Trade PnL — {activeSymbol} (synthetic from summary stats)</div>
                        <ResponsiveContainer width="100%" height={220}>
                            <BarChart data={waterfallData.filter(d => d.symbol === activeSymbol)} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="2 4" stroke="#111" vertical={false} />
                                <XAxis dataKey="label" tick={false} />
                                <YAxis tick={{ fill: "#333", fontSize: 9 }} tickFormatter={v => `$${v.toFixed(0)}`} />
                                <Tooltip formatter={(v) => [`$${v.toFixed(2)}`, "PnL"]} contentStyle={{ background: "#0d0d14", border: "1px solid #2a2a3e", fontSize: 11, fontFamily: "monospace" }} />
                                <ReferenceLine y={0} stroke="#333" />
                                <Bar dataKey="value" radius={[2, 2, 0, 0]}>
                                    {waterfallData.filter(d => d.symbol === activeSymbol).map((entry, i) => (
                                        <Cell key={i} fill={entry.value >= 0 ? "#00ff9d" : "#ff4757"} fillOpacity={0.8} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Win/Loss donut-style breakdown */}
                    <div style={{ ...styles.grid2, marginTop: 16 }}>
                        <div style={styles.card}>
                            <div style={styles.sectionTitle}>Win / Loss Distribution</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                                {[
                                    { label: "Wins", value: data.wins, total: data.wins + data.losses, color: "#00ff9d" },
                                    { label: "Losses", value: data.losses, total: data.wins + data.losses, color: "#ff4757" },
                                ].map(item => (
                                    <div key={item.label}>
                                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 10, color: "#555" }}>
                                            <span style={{ color: item.color }}>{item.label}</span>
                                            <span>{item.value} / {item.total}</span>
                                        </div>
                                        <div style={{ height: 6, background: "#111", borderRadius: 3, overflow: "hidden" }}>
                                            <div style={{ height: "100%", width: `${(item.value / item.total) * 100}%`, background: item.color, borderRadius: 3, transition: "width 0.5s" }} />
                                        </div>
                                    </div>
                                ))}
                                <div style={{ marginTop: 8, padding: "12px", background: "#111", borderRadius: 6 }}>
                                    <div style={{ fontSize: 9, color: "#333", letterSpacing: 2, textTransform: "uppercase", marginBottom: 6 }}>Expectancy per trade</div>
                                    <div style={{ fontSize: 18, color: pnlColor(data.totalPnl / (data.wins + data.losses)), fontFamily: "Georgia, serif" }}>
                                        {fmt(data.totalPnl / (data.wins + data.losses))}
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div style={styles.card}>
                            <div style={styles.sectionTitle}>Risk Metrics</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
                                {[
                                    { label: "Profit Factor", value: data.profitFactor.toFixed(2) + "×", good: data.profitFactor >= 1.5 },
                                    { label: "Sharpe Ratio", value: data.sharpe.toFixed(2), good: data.sharpe >= 0.5 },
                                    { label: "Max Drawdown", value: data.maxDrawdown.toFixed(1) + "%", good: data.maxDrawdown <= 15 },
                                    { label: "Avg Win / Avg Loss", value: (data.avgWin / Math.abs(data.avgLoss)).toFixed(2) + "×", good: (data.avgWin / Math.abs(data.avgLoss)) >= 2 },
                                ].map(m => (
                                    <div key={m.label} style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid #111" }}>
                                        <span style={{ fontSize: 10, color: "#444" }}>{m.label}</span>
                                        <span style={{ fontSize: 11, color: m.good ? "#00ff9d" : "#ff4757", fontWeight: 600 }}>{m.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </>
            )}

            {/* ── COMPARE TAB ── */}
            {tab === "compare" && (
                <>
                    <div style={{ ...styles.grid2, marginBottom: 16 }}>
                        <div style={styles.card}>
                            <div style={styles.sectionTitle}>Total PnL by Symbol</div>
                            <ResponsiveContainer width="100%" height={200}>
                                <BarChart data={comparisonData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                    <CartesianGrid strokeDasharray="2 4" stroke="#111" vertical={false} />
                                    <XAxis dataKey="symbol" tick={{ fill: "#555", fontSize: 10 }} />
                                    <YAxis tick={{ fill: "#333", fontSize: 9 }} tickFormatter={v => `$${v}`} />
                                    <Tooltip formatter={(v) => [`$${v.toFixed(2)}`, "PnL"]} contentStyle={{ background: "#0d0d14", border: "1px solid #2a2a3e", fontSize: 11, fontFamily: "monospace" }} />
                                    <ReferenceLine y={0} stroke="#333" />
                                    <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                                        {comparisonData.map((entry, i) => <Cell key={i} fill={entry.color} fillOpacity={0.85} />)}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>

                        <div style={styles.card}>
                            <div style={styles.sectionTitle}>Profit Factor vs Win Rate</div>
                            <ResponsiveContainer width="100%" height={200}>
                                <BarChart data={comparisonData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                    <CartesianGrid strokeDasharray="2 4" stroke="#111" vertical={false} />
                                    <XAxis dataKey="symbol" tick={{ fill: "#555", fontSize: 10 }} />
                                    <YAxis tick={{ fill: "#333", fontSize: 9 }} />
                                    <Tooltip contentStyle={{ background: "#0d0d14", border: "1px solid #2a2a3e", fontSize: 11, fontFamily: "monospace" }} />
                                    <Bar dataKey="pf" name="Profit Factor" fill="#00ff9d" fillOpacity={0.7} radius={[3, 3, 0, 0]} />
                                    <Bar dataKey="winRate" name="Win Rate %" fill="#ffd32a" fillOpacity={0.5} radius={[3, 3, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Full comparison table */}
                    <div style={styles.card}>
                        <div style={styles.sectionTitle}>Full Metrics Comparison</div>
                        <table style={styles.table}>
                            <thead>
                                <tr>
                                    {["Symbol", "Trades", "Win Rate", "Total PnL", "Return", "Prof. Factor", "Max DD", "Sharpe", "Verdict"].map(h => (
                                        <th key={h} style={styles.th}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {SYMBOLS.map(s => {
                                    const d = BACKTEST_DATA[s];
                                    const verdict = s === "BTC/USDT" ? "⛔ Avoid" : s === "ETH/USDT" ? "✅ Trade" : s === "BNB/USDT" ? "⚠️ Marginal" : "⚠️ More data";
                                    return (
                                        <tr key={s} style={{ cursor: "pointer" }} onClick={() => { setActiveSymbol(s); setTab("overview"); }}>
                                            <td style={{ ...styles.td, color: d.color, fontWeight: 600 }}>{s}</td>
                                            <td style={{ ...styles.td, color: "#666" }}>{d.totalTrades}</td>
                                            <td style={{ ...styles.td, color: d.winRate >= 40 ? "#00ff9d" : d.winRate >= 30 ? "#ffd32a" : "#ff4757" }}>{d.winRate}%</td>
                                            <td style={{ ...styles.td, color: pnlColor(d.totalPnl), fontWeight: 600 }}>{fmt(d.totalPnl)}</td>
                                            <td style={{ ...styles.td, color: pnlColor(d.returnPct) }}>{fmt(d.returnPct, "")}%</td>
                                            <td style={{ ...styles.td, color: d.profitFactor >= 2 ? "#00ff9d" : d.profitFactor >= 1.5 ? "#ffd32a" : "#ff4757" }}>{d.profitFactor.toFixed(2)}×</td>
                                            <td style={{ ...styles.td, color: d.maxDrawdown > 20 ? "#ff4757" : d.maxDrawdown > 10 ? "#ffd32a" : "#00ff9d" }}>{d.maxDrawdown.toFixed(1)}%</td>
                                            <td style={{ ...styles.td, color: d.sharpe > 1 ? "#00ff9d" : d.sharpe > 0 ? "#ffd32a" : "#ff4757" }}>{d.sharpe.toFixed(2)}</td>
                                            <td style={styles.td}>{verdict}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                        <div style={{ marginTop: 12, fontSize: 10, color: "#333" }}>↑ Click any row to view detailed overview for that symbol</div>
                    </div>
                </>
            )}
        </div>
    );
}
