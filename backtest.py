import json
import os
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from data.fetcher import fetch_historical_data
from strategy.bias import get_bias
from strategy.fvg import detect_fvgs, get_active_fvgs
from strategy.orderblock import detect_order_blocks, detect_breaker_blocks, get_active_ob_near_price
from strategy.supply_demand import detect_zones, get_zones_near_price
from strategy.confluence import score_setup
from utils.config import settings

# Gracefully handle missing settings and progress bars
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

PAPER_FEE_RATE = getattr(settings, 'PAPER_FEE_RATE', 0.001)
MAX_RISK_PER_TRADE = getattr(settings, 'MAX_RISK_PER_TRADE', 0.02)

@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry_price: float
    sl_price: float
    tp_price: float
    entry_idx: int
    exit_price: float = 0.0
    exit_reason: str = "OPEN"
    exit_idx: int = 0
    confluence_score: int = 0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0

@dataclass  
class BacktestResult:
    trades: List[BacktestTrade] = field(default_factory=list)
    starting_equity: float = 10000.0
    final_equity: float = 10000.0
    equity_series: list = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    duration_days: int = 0
    
    @property
    def total_trades(self): return len(self.trades)
    
    @property
    def closed_trades(self): return [t for t in self.trades if t.exit_reason != "OPEN"]
    
    @property
    def wins(self): return [t for t in self.closed_trades if t.exit_reason == "TAKE_PROFIT"]
    
    @property
    def losses(self): return [t for t in self.closed_trades if t.exit_reason == "STOP_LOSS"]
    
    @property
    def win_rate(self): 
        c = self.closed_trades
        return len(self.wins) / len(c) * 100 if c else 0
    
    @property
    def total_pnl(self): return sum(t.net_pnl for t in self.closed_trades)
    
    @property
    def profit_factor(self):
        gross_wins = sum(t.gross_pnl for t in self.wins)
        gross_losses = abs(sum(t.gross_pnl for t in self.losses))
        return gross_wins / gross_losses if gross_losses > 0 else float('inf')
    
    @property
    def max_drawdown(self):
        equity = self.starting_equity
        peak = equity
        max_dd = 0.0
        for t in self.closed_trades:
            equity += t.net_pnl
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)
        return max_dd
    
    @property
    def sharpe_ratio(self):
        if not self.closed_trades:
            return 0.0
        pnls = [t.net_pnl for t in self.closed_trades]
        mean = np.mean(pnls)
        std = np.std(pnls)
        return (mean / std * np.sqrt(len(pnls))) if std > 0 else 0.0

    def print_summary(self):
        c = self.closed_trades
        avg_win = np.mean([t.net_pnl for t in self.wins]) if self.wins else 0
        avg_loss = np.mean([t.net_pnl for t in self.losses]) if self.losses else 0
        
        print("\n" + "="*50)
        print("         BACKTEST RESULTS SUMMARY")
        print("="*50)
        print(f"  Starting Equity:   ${self.starting_equity:>10,.2f}")
        print(f"  Final Equity:      ${self.final_equity:>10,.2f}")
        print(f"  Total PnL:         ${self.total_pnl:>+10,.2f}")
        print(f"  Return:            {self.total_pnl/self.starting_equity*100:>+9.2f}%")
        print("-"*50)
        print(f"  Total Trades:      {self.total_trades:>10}")
        print(f"  Closed Trades:     {len(c):>10}")
        print(f"  Wins:              {len(self.wins):>10}")
        print(f"  Losses:            {len(self.losses):>10}")
        print(f"  Win Rate:          {self.win_rate:>9.1f}%")
        print("-"*50)
        print(f"  Avg Win:           ${avg_win:>+10,.2f}")
        print(f"  Avg Loss:          ${avg_loss:>+10,.2f}")
        print(f"  Profit Factor:     {self.profit_factor:>10.2f}")
        print(f"  Max Drawdown:      {self.max_drawdown:>9.2f}%")
        print(f"  Sharpe Ratio:      {self.sharpe_ratio:>10.2f}")
        print("="*50 + "\n")


class ICTBacktester:
    def __init__(self, symbol: str, starting_equity: float = 10000.0):
        self.symbol = symbol
        self.starting_equity = starting_equity
        self.fee_rate = PAPER_FEE_RATE
        self.risk_per_trade = MAX_RISK_PER_TRADE

    def fetch_data(self, htf_limit: int = 500, mtf_limit: int = 500) -> tuple:
        """Fetch a large historical dataset for backtesting."""
        print(f"Fetching historical data for {self.symbol}...")
        df_htf = fetch_historical_data("binance", self.symbol, settings.BIAS_TIMEFRAME, htf_limit)
        df_mtf = fetch_historical_data("binance", self.symbol, settings.SETUP_TIMEFRAME, mtf_limit)
        return df_htf, df_mtf

    def run(self, htf_limit: int = 500, mtf_limit: int = 500) -> BacktestResult:
        df_htf, df_mtf = self.fetch_data(htf_limit, mtf_limit)
        
        if df_htf.empty or df_mtf.empty:
            print("ERROR: Could not fetch data.")
            return BacktestResult(starting_equity=self.starting_equity, 
                                  final_equity=self.starting_equity)

        result = BacktestResult(
            starting_equity=self.starting_equity,
            final_equity=self.starting_equity
        )
        equity = self.starting_equity

        # Start at candle 50 so bias/structure detectors have enough context
        WARMUP = 50
        active_trade: Optional[BacktestTrade] = None
        
        print(f"Running backtest on {len(df_mtf)} MTF candles...")
        
        iterator = range(WARMUP, len(df_mtf))
        if HAS_TQDM:
            iterator = tqdm(iterator, desc=self.symbol)

        for i in iterator:
            current_price = df_mtf['close'].iloc[i]

            # --- Monitor open position ---
            if active_trade and active_trade.exit_reason == "OPEN":
                candle = df_mtf.iloc[i]
                direction = active_trade.direction
                
                hit_sl = (direction == "LONG" and candle['low'] <= active_trade.sl_price) or \
                         (direction == "SHORT" and candle['high'] >= active_trade.sl_price)
                hit_tp = (direction == "LONG" and candle['high'] >= active_trade.tp_price) or \
                         (direction == "SHORT" and candle['low'] <= active_trade.tp_price)

                if hit_sl:
                    active_trade.exit_price = active_trade.sl_price
                    active_trade.exit_reason = "STOP_LOSS"
                    active_trade.exit_idx = i
                elif hit_tp:
                    active_trade.exit_price = active_trade.tp_price
                    active_trade.exit_reason = "TAKE_PROFIT"
                    active_trade.exit_idx = i

                if active_trade.exit_reason != "OPEN":
                    # Correct Risk/Position Sizing
                    # If we hit SL, we want to lose exactly (equity * risk_per_trade)
                    risk_usd = equity * self.risk_per_trade
                    sl_dist = abs(active_trade.entry_price - active_trade.sl_price)
                    
                    if sl_dist > 0:
                        amount_base = risk_usd / sl_dist
                    else:
                        amount_base = 0 # Invalid trade setup

                    if direction == "LONG":
                        gross = (active_trade.exit_price - active_trade.entry_price) * amount_base
                    else:
                        gross = (active_trade.entry_price - active_trade.exit_price) * amount_base
                    
                    vol_usd = (active_trade.entry_price + active_trade.exit_price) * amount_base
                    fees = vol_usd * self.fee_rate
                    net = gross - fees
                    
                    active_trade.gross_pnl = gross
                    active_trade.net_pnl = net
                    equity += net
                    
                    result.equity_series.append({
                        "trade": len(result.closed_trades),
                        "equity": round(equity, 2),
                        "reason": active_trade.exit_reason
                    })
                    
                    active_trade = None
                    
                continue  # Don't look for new entries while in a trade

            # --- Look for new entry ---
            # Use a slice of data up to current candle (prevent lookahead bias)
            df_htf_slice = df_htf[df_htf.index <= df_mtf.index[i]].tail(200)
            df_mtf_slice = df_mtf.iloc[max(0, i-99):i+1]

            if len(df_htf_slice) < 20 or len(df_mtf_slice) < 20:
                continue

            try:
                bias = get_bias(self.symbol, df_htf_slice)
                if not bias["tradeable"]:
                    continue

                direction = bias["direction"]
                fvgs = get_active_fvgs(df_mtf_slice, self.symbol, current_price, direction)
                obs = detect_order_blocks(df_mtf_slice, self.symbol)
                breakers = detect_breaker_blocks(df_mtf_slice, self.symbol)
                active_obs = get_active_ob_near_price(obs, breakers, self.symbol, current_price, direction)
                zones = detect_zones(df_mtf_slice, self.symbol)
                active_zones = get_zones_near_price(zones, self.symbol, current_price, direction)

                setup = score_setup(self.symbol, current_price, bias, fvgs, active_obs, breakers, active_zones)

                if setup:
                    active_trade = BacktestTrade(
                        symbol=self.symbol,
                        direction=setup.direction,
                        entry_price=setup.entry_price,
                        sl_price=setup.sl_price,
                        tp_price=setup.tp_price,
                        entry_idx=i,
                        confluence_score=setup.confluence_score
                    )
                    result.trades.append(active_trade)

            except Exception:
                continue

        # Close any open trade at last price
        if active_trade and active_trade.exit_reason == "OPEN":
            active_trade.exit_price = df_mtf['close'].iloc[-1]
            active_trade.exit_reason = "END_OF_DATA"
            active_trade.exit_idx = len(df_mtf) - 1

        result.final_equity = equity
        
        # Capture the time bounds of this simulation
        if len(df_mtf) > WARMUP:
            result.start_time = str(df_mtf.index[WARMUP])
            result.end_time = str(df_mtf.index[-1])
            result.duration_days = (df_mtf.index[-1] - df_mtf.index[WARMUP]).days
            
        return result


def run_multi_symbol_backtest():
    """Backtest all ICT symbols and compare."""
    symbols = settings.ICT_SYMBOLS
    all_results = {}
    
    print("\n🔍 Running ICT Strategy Backtest")
    print("="*50)
    
    # We fetch a larger chunk of data to simulate more trades
    HTF_LIMIT = 1000
    MTF_LIMIT = 1500

    for symbol in symbols:
        print(f"\n--- {symbol} ---")
        backtester = ICTBacktester(symbol)
        result = backtester.run(htf_limit=HTF_LIMIT, mtf_limit=MTF_LIMIT)
        result.print_summary()
        all_results[symbol] = result
    
    # Comparative summary
    print("\n📊 COMPARATIVE SUMMARY")
    print(f"{'Symbol':<15} {'Trades':>8} {'WinRate':>9} {'PnL':>10} {'PF':>8} {'MaxDD':>8}")
    print("-"*60)
    
    export_data = {}
    
    for sym, r in all_results.items():
        if r.closed_trades:
            print(f"{sym:<15} {len(r.closed_trades):>8} {r.win_rate:>8.1f}% "
                  f"${r.total_pnl:>+9,.2f} {r.profit_factor:>8.2f} {r.max_drawdown:>7.1f}%")
                  
        # Format for React Dashboard
        avg_win = np.mean([t.net_pnl for t in r.wins]) if r.wins else 0.0
        avg_loss = np.mean([t.net_pnl for t in r.losses]) if r.losses else 0.0
        pf = r.profit_factor
        if pf == float('inf'):
            pf = 99.9  # Cap for JSON serialization
            
        colors = {
            "BTC/USDT": "#ff4757",
            "ETH/USDT": "#00ff9d",
            "BNB/USDT": "#ffd32a",
            "SOL/USDT": "#a29bfe",
        }
            
        export_data[sym] = {
            "startEquity": r.starting_equity,
            "finalEquity": r.final_equity,
            "totalPnl": r.total_pnl,
            "returnPct": (r.total_pnl / r.starting_equity) * 100,
            "totalTrades": r.total_trades,
            "wins": len(r.wins),
            "losses": len(r.losses),
            "openTrades": len(r.trades) - len(r.closed_trades),
            "winRate": r.win_rate,
            "avgWin": avg_win,
            "avgLoss": avg_loss,
            "profitFactor": pf,
            "maxDrawdown": r.max_drawdown,
            "sharpe": r.sharpe_ratio,
            "color": colors.get(sym, "#ffffff"),
            "startTime": r.start_time,
            "endTime": r.end_time,
            "durationDays": r.duration_days,
            "equitySeries": r.equity_series,
            "trades": [
                {
                    "id": t.entry_idx,
                    "dir": t.direction,
                    "entry": t.entry_price,
                    "exit": t.exit_price,
                    "reason": t.exit_reason,
                    "pnl": t.net_pnl,
                    "score": t.confluence_score
                }
                for t in r.closed_trades
            ]
        }
        
    # Write to dashboard assets
    os.makedirs("dashboard/src/assets", exist_ok=True)
    with open("dashboard/src/assets/results.json", "w") as f:
        json.dump(export_data, f, indent=2)
    print("\n✅ Results exported to dashboard/src/assets/results.json")


def optimize_confluence_threshold(symbol: str, thresholds: list[int] = [2, 3, 4, 5]):
    """Find the optimal MIN_CONFLUENCES for a given symbol."""
    print(f"\n🔧 Optimizing confluence threshold for {symbol}")
    print(f"{'Threshold':>12} {'Trades':>8} {'WinRate':>9} {'PnL':>10} {'PF':>8} {'MaxDD':>8} {'Sharpe':>8}")
    print("-" * 70)
    
    for threshold in thresholds:
        # Temporarily override the setting
        settings.MIN_CONFLUENCES_BY_SYMBOL[symbol] = threshold
        
        backtester = ICTBacktester(symbol)
        # Reuse already-fetched data implicitly or just call run
        result = backtester.run(htf_limit=500, mtf_limit=1500)
        
        c = result.closed_trades
        if c:
            print(f"{threshold:>12} {len(c):>8} {result.win_rate:>8.1f}% "
                  f"${result.total_pnl:>+9,.2f} {result.profit_factor:>8.2f} "
                  f"{result.max_drawdown:>7.1f}% {result.sharpe_ratio:>8.2f}")
        else:
            print(f"{threshold:>12} {'0':>8} {'N/A':>9} {'$0':>10} {'N/A':>8} {'N/A':>8} {'N/A':>8}")

def walk_forward_test(symbol: str, total_candles: int = 2000):
    """Split data 50/50 into in-sample and out-of-sample."""
    backtester = ICTBacktester(symbol)
    df_htf, df_mtf = backtester.fetch_data(htf_limit=total_candles, 
                                            mtf_limit=total_candles * 4)
    
    split = len(df_mtf) // 2
    
    print(f"\n📈 Walk-Forward Test: {symbol}")
    
    for label, df_slice in [("IN-SAMPLE (train)", df_mtf.iloc[:split]),
                             ("OUT-OF-SAMPLE (test)", df_mtf.iloc[split:])]:
        print(f"\n  {label}: {len(df_slice)} candles")

if __name__ == "__main__":
    optimize_confluence_threshold("BTC/USDT")
    optimize_confluence_threshold("ETH/USDT")
    run_multi_symbol_backtest()
