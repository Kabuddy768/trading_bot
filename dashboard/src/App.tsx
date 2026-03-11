import { useState, useMemo } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import rawData from "./assets/results.json";

interface TradeData {
    id: number;
    dir: string;
    entry: number;
    exit: number;
    reason: string;
    pnl: number;
    score: number;
}

interface BacktestStats {
    startEquity: number;
    finalEquity: number;
    totalPnl: number;
    returnPct: number;
    totalTrades: number;
    wins: number;
    losses: number;
    openTrades: number;
    winRate: number;
    avgWin: number;
    avgLoss: number;
    profitFactor: number;
    maxDrawdown: number;
    sharpe: number;
    color: string;
    startTime: string;
    endTime: string;
    durationDays: number;
    equitySeries: { trade: number; equity: number; reason: string }[];
    trades: TradeData[];
}

const BACKTEST_DATA = rawData as unknown as Record<string, BacktestStats>;
const SYMBOLS = Object.keys(BACKTEST_DATA);

function formatDuration(days: number) {
    if (days < 7) return `${days} days`;
    if (days < 30) return `${Math.floor(days / 7)} weeks`;
    const m = Math.floor(days / 30);
    const rem = days % 30;
    if (m > 11) return `${Math.floor(days / 365)} years, ${m % 12} months`;
    if (rem > 7) return `${m} months, ${Math.floor(rem / 7)} weeks`;
    return `${m} months`;
}

// Generate actionable AI insights based on stats
function generateInsights(data: BacktestStats, symbol: string) {
    const insights = [];

    // Win rate vs Profit Factor
    if (data.winRate < 35 && data.profitFactor > 1.5) {
        insights.push({ type: 'warning', text: "Low win rate but profitable. The strategy relies entirely on big runners. Consider widening stops slightly to prevent premature outs." });
    } else if (data.winRate > 50 && data.profitFactor < 1.0) {
        insights.push({ type: 'danger', text: "High win rate but losing money overall. You are taking many small profits but suffering catastrophic losses. Implement a hard max drawdown limit per trade." });
    } else if (data.profitFactor > 2.0 && data.totalTrades > 10) {
        insights.push({ type: 'success', text: "Excellent expectancy. The reward-to-risk ratio is carrying this setup perfectly. Consider scaling up position sizing cautiously on this symbol." });
    }

    // Drawdown
    if (data.maxDrawdown > 20) {
        insights.push({ type: 'danger', text: "Severe drawdown detected (>20%). Capital preservation is failing. You must reduce risk limits per trade, or this symbol's volatility is incompatible with the confluences." });
    } else if (data.maxDrawdown < 5 && data.totalTrades > 10) {
        insights.push({ type: 'success', text: "Extremely stable equity curve. The strategy is highly defensive on this pair." });
    }

    // Trade frequency
    const tradesPerWeek = data.totalTrades / (data.durationDays / 7);
    if (tradesPerWeek > 15) {
        insights.push({ type: 'warning', text: "Over-trading detected. Averaging >15 trades per week. Increase MIN_CONFLUENCES_BY_SYMBOL to filter out noise." });
    } else if (tradesPerWeek < 1 && data.durationDays > 30) {
        insights.push({ type: 'neutral', text: "Very rare setups. Averaging <1 trade per week. This pair requires immense patience. Capital might be better deployed elsewhere." });
    }

    if (insights.length === 0) {
        insights.push({ type: 'neutral', text: "Metrics are balanced. Continue gathering out-of-sample data." });
    }

    return insights;
}

const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{
            background: "rgba(10, 10, 15, 0.85)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "8px",
            padding: "12px 16px",
            boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
            fontFamily: "var(--font-sans)"
        }}>
            <div style={{ color: "var(--text-muted)", fontSize: "12px", marginBottom: "6px", fontWeight: 500, letterSpacing: "0.5px" }}>
                Trade #{label}
            </div>
            {payload.map((p: any) => (
                <div key={p.dataKey} style={{ color: p.color, fontSize: "14px", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px" }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: p.color }} />
                    {p.name}: ${p.value?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
            ))}
            {payload[0]?.payload?.reason && (
                <div style={{ marginTop: "6px", fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                    Exit: {payload[0].payload.reason}
                </div>
            )}
        </div>
    );
};

export default function App() {
    const [activeSymbol, setActiveSymbol] = useState(SYMBOLS[0] || "");
    const [tab, setTab] = useState("overview");

    // Handle case where JSON is completely empty/loading
    if (!activeSymbol || !BACKTEST_DATA[activeSymbol]) {
        return (
            <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: '#050508', color: '#8a8a9e', fontFamily: 'Outfit' }}>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', color: '#fff', marginBottom: '8px' }}>Waiting for Data...</div>
                    <div>Run the `python backtest.py` script to generate results.json.</div>
                </div>
            </div>
        );
    }

    const data = BACKTEST_DATA[activeSymbol];
    // Ensure we have an equity curve
    const curve = data.equitySeries && data.equitySeries.length > 0
        ? data.equitySeries
        : [{ trade: 0, equity: data.startEquity }, { trade: 1, equity: data.finalEquity }];

    const comparisonData = SYMBOLS.map(s => ({
        symbol: s.replace("/USDT", ""),
        pnl: BACKTEST_DATA[s].totalPnl,
        winRate: BACKTEST_DATA[s].winRate,
        pf: BACKTEST_DATA[s].profitFactor,
        dd: BACKTEST_DATA[s].maxDrawdown,
        sharpe: BACKTEST_DATA[s].sharpe,
        color: BACKTEST_DATA[s].color,
    }));

    const waterfallData = SYMBOLS.flatMap(s => {
        const d = BACKTEST_DATA[s];
        return (d.trades || []).map((t, i) => ({
            label: t.pnl >= 0 ? 'W' : 'L',
            value: t.pnl,
            symbol: s,
            color: t.pnl >= 0 ? d.color : 'var(--loss)',
            id: i,
        }));
    });

    const pnlColor = (v: number) => v >= 0 ? "var(--win)" : "var(--loss)";
    const fmt = (v: number, prefix = "$") => `${v >= 0 ? "+" : ""}${prefix}${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    const insights = generateInsights(data, activeSymbol);

    return (
        <div style={{ padding: "32px 48px", maxWidth: "1600px", margin: "0 auto", animation: "fadeIn 0.5s ease" }}>

            {/* ── HEADER ── */}
            <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "40px" }}>
                <div>
                    <h1 style={{ fontSize: "32px", fontWeight: 700, color: "#fff", letterSpacing: "-0.5px", marginBottom: "8px" }}>
                        Algorithmic Backtest Report
                    </h1>
                    <div style={{ display: "flex", alignItems: "center", gap: "16px", fontSize: "13px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--win)", boxShadow: "0 0 8px var(--win)" }} />
                            Live Data Synced
                        </span>
                        <span>·</span>
                        <span>Duration: {formatDuration(data.durationDays)} ({data.durationDays}d)</span>
                        <span>·</span>
                        <span>From: {data.startTime.split(" ")[0]} To: {data.endTime.split(" ")[0]}</span>
                    </div>
                </div>

                <div style={{ textAlign: "right", background: "var(--bg-card)", border: "1px solid var(--border-light)", padding: "12px 20px", borderRadius: "12px", backdropFilter: "blur(10px)" }}>
                    <div style={{ fontSize: "11px", letterSpacing: "1px", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "4px", fontWeight: 600 }}>Net Portfolio Edge</div>
                    <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--win)", fontFamily: "var(--font-mono)" }}>
                        {fmt(Object.values(BACKTEST_DATA).reduce((sum, s) => sum + s.totalPnl, 0))}
                    </div>
                </div>
            </header>

            {/* ── NAVIGATION ── */}
            <div style={{ display: "flex", gap: "24px", marginBottom: "32px", borderBottom: "1px solid var(--border-light)" }}>
                {[
                    { id: "overview", label: "Overview" },
                    { id: "equity", label: "Equity Curves" },
                    { id: "trades", label: "Trade Analysis" },
                    { id: "compare", label: "Correlations" }
                ].map(t => (
                    <button
                        key={t.id}
                        onClick={() => setTab(t.id)}
                        style={{
                            padding: "0 4px 16px 4px",
                            background: "none", border: "none",
                            color: tab === t.id ? "#fff" : "var(--text-muted)",
                            fontSize: "14px", fontWeight: 500, cursor: "pointer",
                            borderBottom: `2px solid ${tab === t.id ? "var(--win)" : "transparent"}`,
                            transition: "all 0.2s ease",
                            letterSpacing: "0.5px"
                        }}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {/* ── SYMBOL SELECTOR ── */}
            {tab !== "compare" && (
                <div style={{ display: "flex", gap: "12px", marginBottom: "32px", flexWrap: "wrap" }}>
                    {SYMBOLS.map(sym => {
                        const isActive = activeSymbol === sym;
                        const symData = BACKTEST_DATA[sym];
                        return (
                            <button
                                key={sym}
                                onClick={() => setActiveSymbol(sym)}
                                style={{
                                    padding: "10px 20px",
                                    borderRadius: "8px",
                                    fontSize: "13px", fontWeight: 600,
                                    cursor: "pointer",
                                    fontFamily: "var(--font-mono)",
                                    background: isActive ? `${symData.color}15` : "var(--bg-card)",
                                    border: `1px solid ${isActive ? symData.color : "var(--border-light)"}`,
                                    color: isActive ? symData.color : "var(--text-main)",
                                    transition: "all 0.2s ease",
                                    boxShadow: isActive ? `0 4px 12px ${symData.color}15` : "none"
                                }}
                            >
                                {sym}
                            </button>
                        )
                    })}
                </div>
            )}

            {/* ── OVERVIEW TAB ── */}
            {tab === "overview" && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "24px" }}>

                    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                        {/* Main Stats Grid */}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
                            {[
                                { label: "Net Return", value: fmt(data.returnPct, "") + "%", color: pnlColor(data.returnPct), sub: `$${Math.abs(data.totalPnl).toFixed(2)} PnL` },
                                { label: "Win Rate", value: data.winRate.toFixed(1) + "%", color: data.winRate >= 40 ? "var(--win)" : data.winRate >= 30 ? "var(--warn)" : "var(--loss)", sub: `${data.wins}W / ${data.losses}L` },
                                { label: "Profit Factor", value: data.profitFactor === 99.9 ? "INF" : data.profitFactor.toFixed(2) + "×", color: data.profitFactor >= 2 ? "var(--win)" : data.profitFactor >= 1.5 ? "var(--warn)" : "var(--loss)", sub: "Reward/Risk ratio" },
                                { label: "Max Drawdown", value: data.maxDrawdown.toFixed(1) + "%", color: data.maxDrawdown > 20 ? "var(--loss)" : data.maxDrawdown > 10 ? "var(--warn)" : "var(--win)", sub: "Peak-to-trough" },
                            ].map(stat => (
                                <div key={stat.label} style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "20px", backdropFilter: "blur(10px)" }}>
                                    <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "1px", color: "var(--text-muted)", marginBottom: "8px", fontWeight: 600 }}>{stat.label}</div>
                                    <div style={{ fontSize: "28px", fontWeight: 700, color: stat.color, fontFamily: "var(--font-mono)", marginBottom: "4px" }}>{stat.value}</div>
                                    <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>{stat.sub}</div>
                                </div>
                            ))}
                        </div>

                        {/* Main Equity Chart */}
                        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "24px", backdropFilter: "blur(10px)", flexGrow: 1 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
                                <div style={{ fontSize: "14px", fontWeight: 600, letterSpacing: "0.5px", color: "#fff" }}>Primary Equity Curve — {activeSymbol}</div>
                                <div style={{ fontSize: "12px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>{data.totalTrades} Closed Trades</div>
                            </div>

                            <ResponsiveContainer width="100%" height={320}>
                                <LineChart data={curve} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id={`gradient-${activeSymbol}`} x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor={data.color} stopOpacity={0.3} />
                                            <stop offset="95%" stopColor={data.color} stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                    <XAxis dataKey="trade" tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                                    <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} tickFormatter={v => `$${(v / 1000).toFixed(1)}k`} domain={['auto', 'auto']} axisLine={false} tickLine={false} />
                                    <RechartsTooltip content={<CustomTooltip />} />
                                    <ReferenceLine y={data.startEquity} stroke="rgba(255,255,255,0.1)" strokeDasharray="3 3" />
                                    <Line type="monotone" dataKey="equity" stroke={data.color} strokeWidth={3} dot={{ r: 0 }} activeDot={{ r: 6, fill: data.color, stroke: "var(--bg)", strokeWidth: 2 }} name="Equity" animationDuration={1500} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Right Sidebar */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>

                        {/* Algorithmic Insights */}
                        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "24px", backdropFilter: "blur(10px)" }}>
                            <div style={{ fontSize: "14px", fontWeight: 600, letterSpacing: "0.5px", color: "#fff", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
                                ✨ Algorithmic Insights
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                                {insights.map((insight, idx) => {
                                    const colors = {
                                        danger: { bg: "rgba(255,51,102,0.1)", border: "rgba(255,51,102,0.3)", text: "#ff8da1" },
                                        warning: { bg: "rgba(255,204,0,0.1)", border: "rgba(255,204,0,0.3)", text: "#ffe066" },
                                        success: { bg: "rgba(0,255,157,0.1)", border: "rgba(0,255,157,0.3)", text: "#80ffce" },
                                        neutral: { bg: "rgba(255,255,255,0.05)", border: "rgba(255,255,255,0.1)", text: "var(--text-main)" }
                                    };
                                    const style = colors[insight.type as keyof typeof colors];

                                    return (
                                        <div key={idx} style={{
                                            background: style.bg, border: `1px solid ${style.border}`, color: style.text,
                                            padding: "12px 16px", borderRadius: "8px", fontSize: "13px", lineHeight: 1.5
                                        }}>
                                            {insight.text}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Secondary Stats */}
                        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "20px", backdropFilter: "blur(10px)" }}>
                            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                                {[
                                    { label: "Sharpe Ratio", value: data.sharpe.toFixed(2), good: data.sharpe >= 1 },
                                    { label: "Expectancy / Trade", value: fmt(data.totalPnl / data.totalTrades), good: data.totalPnl > 0 },
                                    { label: "Avg Winning Trade", value: fmt(data.avgWin), good: true },
                                    { label: "Avg Losing Trade", value: fmt(data.avgLoss), good: false },
                                ].map(m => (
                                    <div key={m.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                        <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>{m.label}</span>
                                        <span style={{ fontSize: "14px", fontWeight: 600, fontFamily: "var(--font-mono)", color: m.value.includes("-") || !m.good && m.label === "Sharpe Ratio" ? "var(--loss)" : "var(--text-main)" }}>
                                            {m.value}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>

                    </div>
                </div>
            )}

            {/* ── EQUITY TAB (Multi-chart) ── */}
            {tab === "equity" && (
                <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "32px", backdropFilter: "blur(10px)" }}>
                    <div style={{ fontSize: "16px", fontWeight: 600, color: "#fff", marginBottom: "24px" }}>Comparative Equity Curves</div>
                    <ResponsiveContainer width="100%" height={500}>
                        <LineChart margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                            <XAxis dataKey="trade" type="number" tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} domain={['dataMin', 'dataMax']} />
                            <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} tickFormatter={v => `$${(v / 1000).toFixed(1)}k`} domain={['auto', 'auto']} axisLine={false} tickLine={false} />
                            <RechartsTooltip content={<CustomTooltip />} />
                            <ReferenceLine y={10000} stroke="rgba(255,255,255,0.2)" strokeDasharray="3 3" />
                            {SYMBOLS.map(sym => (
                                <Line
                                    key={sym}
                                    data={BACKTEST_DATA[sym].equitySeries}
                                    type="monotone"
                                    dataKey="equity"
                                    stroke={BACKTEST_DATA[sym].color}
                                    strokeWidth={activeSymbol === sym ? 3 : 1.5}
                                    dot={false}
                                    name={sym}
                                    opacity={activeSymbol === sym ? 1 : 0.4}
                                    animationDuration={1500}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* ── TRADES TAB ── */}
            {tab === "trades" && (
                <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "32px", backdropFilter: "blur(10px)" }}>
                    <div style={{ fontSize: "16px", fontWeight: 600, color: "#fff", marginBottom: "24px" }}>Trade Distribution Waterfall — {activeSymbol}</div>
                    <ResponsiveContainer width="100%" height={400}>
                        <BarChart data={waterfallData.filter(d => d.symbol === activeSymbol)} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                            <XAxis dataKey="id" tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                            <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} tickFormatter={v => `$${v}`} axisLine={false} tickLine={false} />
                            <RechartsTooltip formatter={(v: number) => [`$${v.toFixed(2)}`, "Net PnL"]} contentStyle={{ background: "rgba(10,10,15,0.9)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px", fontFamily: "var(--font-mono)", fontSize: "12px" }} />
                            <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                            <Bar dataKey="value" radius={[4, 4, 4, 4]}>
                                {waterfallData.filter(d => d.symbol === activeSymbol).map((entry, i) => (
                                    <Cell key={i} fill={entry.color} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* ── COMPARE TAB ── */}
            {tab === "compare" && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginBottom: "24px" }}>
                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "24px", backdropFilter: "blur(10px)" }}>
                        <div style={{ fontSize: "14px", fontWeight: 600, color: "#fff", marginBottom: "24px" }}>Net Profit by Symbol</div>
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={comparisonData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                <XAxis dataKey="symbol" tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                                <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }} tickFormatter={v => `$${v}`} axisLine={false} tickLine={false} />
                                <RechartsTooltip formatter={(v: number) => [`$${v.toFixed(2)}`, "PnL"]} contentStyle={{ background: "rgba(10,10,15,0.9)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px", fontFamily: "var(--font-mono)", fontSize: "12px" }} />
                                <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                                <Bar dataKey="pnl" radius={[6, 6, 0, 0]}>
                                    {comparisonData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-light)", borderRadius: "12px", padding: "24px", backdropFilter: "blur(10px)" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                            <thead>
                                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                                    {["Pair", "Trades", "Win Rate", "Net PnL", "Prof. Factor", "Max DD"].map(h => (
                                        <th key={h} style={{ padding: "12px 8px", fontSize: "12px", color: "var(--text-muted)", fontWeight: 500 }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {comparisonData.map((row, i) => (
                                    <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                                        <td style={{ padding: "16px 8px", fontWeight: 600, color: row.color, fontFamily: "var(--font-mono)", fontSize: "13px" }}>{row.symbol}</td>
                                        <td style={{ padding: "16px 8px", color: "var(--text-main)", fontSize: "13px" }}>{BACKTEST_DATA[row.symbol + "/USDT"].totalTrades}</td>
                                        <td style={{ padding: "16px 8px", color: row.winRate > 40 ? "var(--win)" : "var(--warn)", fontSize: "13px" }}>{row.winRate.toFixed(1)}%</td>
                                        <td style={{ padding: "16px 8px", color: row.pnl >= 0 ? "var(--win)" : "var(--loss)", fontFamily: "var(--font-mono)", fontSize: "13px" }}>{fmt(row.pnl)}</td>
                                        <td style={{ padding: "16px 8px", color: "var(--text-main)", fontSize: "13px" }}>{row.pf === 99.9 ? "INF" : row.pf.toFixed(2)}x</td>
                                        <td style={{ padding: "16px 8px", color: row.dd < 15 ? "var(--win)" : "var(--loss)", fontSize: "13px" }}>{row.dd.toFixed(1)}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

        </div>
    );
}
