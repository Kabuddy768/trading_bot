import json
import os
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from data.fetcher import fetch_historical_data
from strategy.bias import get_bias
from strategy.fvg import detect_fvgs
from strategy.orderblock import detect_order_blocks, detect_breaker_blocks
from strategy.supply_demand import detect_zones
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
class PendingOrder:
    symbol: str
    direction: str
    entry_price: float
    sl_price: float
    tp_price: float
    setup_idx: int
    confluence_score: int
    equity_at_setup: float
    expires_at_idx: int

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
    equity_at_entry: float = 0.0
    position_size: float = 0.0

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

    def fetch_data(self, htf_limit: int = 500, mtf_limit: int = 500, since_date: str = None, until_date: str = None) -> tuple:
        """Fetch a historical dataset for backtesting."""
        print(f"Fetching historical data for {self.symbol}...")
        df_htf = fetch_historical_data("binance", self.symbol, settings.BIAS_TIMEFRAME, htf_limit, since_date, until_date)
        df_mtf = fetch_historical_data("binance", self.symbol, settings.SETUP_TIMEFRAME, mtf_limit, since_date, until_date)
        return df_htf, df_mtf

    def run(self, htf_limit: int = 500, mtf_limit: int = 500, since_date: str = None, until_date: str = None) -> BacktestResult:
        df_htf, df_mtf = self.fetch_data(htf_limit, mtf_limit, since_date, until_date)
        
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
        pending_order: Optional[PendingOrder] = None
        
        # --- PERFORMANCE OPTIMIZATION ---
        # Pre-compute HTF end positions for each MTF candle (prevents O(N^2) boolean indexing)
        htf_times = df_htf.index
        mtf_times = df_mtf.index
        htf_end_positions = htf_times.searchsorted(mtf_times, side='right')
        
        last_htf_candle = None
        cached_bias = None
        
        last_structure_candle = None
        cached_fvgs = []
        cached_obs = []
        cached_breakers = []
        cached_zones = []
        # --------------------------------
        
        print(f"Running backtest on {len(df_mtf)} MTF candles...")
        
        skip_bias = 0
        skip_confluence = 0
        trades_entered = 0
        limit_orders_created = 0
        limit_orders_canceled = 0
        
        iterator = range(WARMUP, len(df_mtf))
        if HAS_TQDM:
            iterator = tqdm(iterator, desc=self.symbol)

        for i in iterator:
            current_price = df_mtf['close'].iloc[i]
            candle = df_mtf.iloc[i]

            # --- Monitor pending order ---
            if pending_order:
                direction = pending_order.direction
                entry_px = pending_order.entry_price
                
                hit_entry = False
                if direction == "LONG" and candle['low'] <= entry_px:
                    hit_entry = True
                elif direction == "SHORT" and candle['high'] >= entry_px:
                    hit_entry = True
                    
                if hit_entry:
                    trades_entered += 1
                    sl_dist = abs(entry_px - pending_order.sl_price)
                    if sl_dist == 0:
                        sl_dist = 1.0 # Prevent Division by Zero
                        
                    risk_usd = equity * self.risk_per_trade
                    trade_size = risk_usd / sl_dist
                    
                    active_trade = BacktestTrade(
                        symbol=pending_order.symbol,
                        direction=pending_order.direction,
                        entry_price=entry_px,
                        sl_price=pending_order.sl_price,
                        tp_price=pending_order.tp_price,
                        entry_idx=i,
                        confluence_score=pending_order.confluence_score,
                        equity_at_entry=equity,
                        position_size=trade_size
                    )
                    result.trades.append(active_trade)
                    pending_order = None
                elif i >= pending_order.expires_at_idx:
                    limit_orders_canceled += 1
                    pending_order = None

            # --- Monitor open position ---
            if active_trade and active_trade.exit_reason == "OPEN":
                direction = active_trade.direction
                
                hit_sl = (direction == "LONG" and candle['low'] <= active_trade.sl_price) or \
                         (direction == "SHORT" and candle['high'] >= active_trade.sl_price)
                hit_tp = (direction == "LONG" and candle['high'] >= active_trade.tp_price) or \
                         (direction == "SHORT" and candle['low'] <= active_trade.tp_price)

                if hit_sl and hit_tp:
                    # Ambiguous collision: determine which is closer to the candle OPEN
                    open_px = candle['open']
                    dist_to_sl = abs(open_px - active_trade.sl_price)
                    dist_to_tp = abs(open_px - active_trade.tp_price)
                    
                    # The closer one is assumed to have hit first
                    if dist_to_tp < dist_to_sl:
                        hit_sl = False # TP hit first
                    else:
                        hit_tp = False # SL hit first

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
                    # We lock in the entry constraints rather than using current equity
                    amount_base = active_trade.position_size

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
                
            # If we have a pending order but no fill yet, we do not look for new setups
            # Because an active structure is currently in play
            if pending_order:
                continue

            # --- Look for new entry ---
            # PERFORMANCE: Use pre-computed integer indices for slicing
            htf_end = htf_end_positions[i]
            df_htf_slice = df_htf.iloc[max(0, htf_end-200):htf_end]
            df_mtf_slice = df_mtf.iloc[max(0, i-99):i+1]

            if len(df_htf_slice) < 20 or len(df_mtf_slice) < 20:
                continue

            try:
                # PERFORMANCE: Only rerun High-Timeframe bias if the HTF candle has closed
                current_htf_candle = df_htf_slice.index[-1]
                if current_htf_candle != last_htf_candle:
                    cached_bias = get_bias(self.symbol, df_htf_slice)
                    last_htf_candle = current_htf_candle
                
                bias = cached_bias
                if not bias or not bias["tradeable"]:
                    skip_bias += 1
                    continue

                # PERFORMANCE: Structure detection is expensive. Only rerun every 5 MTF candles.
                if last_structure_candle is None or (i - last_structure_candle) >= 5:
                    cached_fvgs = detect_fvgs(df_mtf_slice, self.symbol)
                    cached_obs = detect_order_blocks(df_mtf_slice, self.symbol)
                    cached_breakers = detect_breaker_blocks(df_mtf_slice, self.symbol)
                    cached_zones = detect_zones(df_mtf_slice, self.symbol)
                    last_structure_candle = i
                
                fvgs = cached_fvgs
                obs = cached_obs
                breakers = cached_breakers
                zones = cached_zones

                setup = score_setup(self.symbol, df_mtf_slice, bias, fvgs, obs, breakers, zones)

                if not setup:
                    skip_confluence += 1
                    continue
                    
                limit_orders_created += 1
                
                # Create limit order instead of executing at market close
                expiry_candles = getattr(settings, 'ORDER_EXPIRY_CANDLES', 8)
                pending_order = PendingOrder(
                    symbol=self.symbol,
                    direction=setup.direction,
                    entry_price=setup.entry_price,
                    sl_price=setup.sl_price,
                    tp_price=setup.tp_price,
                    setup_idx=i,
                    confluence_score=setup.confluence_score,
                    equity_at_setup=equity,
                    expires_at_idx=i + expiry_candles
                )

            except Exception:
                continue

        # Close any open trade at last price
        if active_trade and active_trade.exit_reason == "OPEN":
            active_trade.exit_price = df_mtf['close'].iloc[-1]
            active_trade.exit_reason = "END_OF_DATA"
            active_trade.exit_idx = len(df_mtf) - 1

        result.final_equity = equity
        
        print(f"  Skipped by bias: {skip_bias}")
        print(f"  Skipped by confluence: {skip_confluence}")
        print(f"  Limit orders created: {limit_orders_created}")
        print(f"  Limit orders canceled: {limit_orders_canceled}")
        print(f"  Trades entered: {trades_entered}")
        
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
    
    # We fetch data based on the explicit date bounds to cover 2024 to present
    SINCE = "2024-01-01"
    UNTIL = "2026-03-10"

    try:
        for symbol in symbols:
            print(f"\n--- {symbol} ---")
            backtester = ICTBacktester(symbol)
            result = backtester.run(since_date=SINCE, until_date=UNTIL)
            result.print_summary()
            all_results[symbol] = result
    except KeyboardInterrupt:
        print("\n\n⚠️  Backtest interrupted by user. Saving progress...")

    if not all_results:
        print("No results to export.")
        return

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
    # optimize_confluence_threshold("BTC/USDT")
    # optimize_confluence_threshold("ETH/USDT")
    run_multi_symbol_backtest()
