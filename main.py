import asyncio
import sys
import time

from utils.logger import logger
from utils.config import settings
from utils.telegram import send_telegram_message

from data.fetcher import fetch_historical_data
from strategy.scanner import scan_for_best_pair, get_all_symbols
from strategy.cointegration import calculate_zscore, generate_signals
from risk.manager import KillSwitch, calculate_position_size, load_state, save_state, check_stop_loss
from execution.engine import ExecutionEngine
from utils.streamer import BinanceStreamer
from datetime import datetime

# WindowsSelectorEventLoopPolicy removed — deprecated in 3.14, removed in 3.16.
# Not needed for REST-only polling bots.


async def fetch_all(symbols: list[str]) -> dict:
    """
    Fetches historical data for every symbol in the watchlist concurrently.
    Returns a dict: { "BTC/USDT": DataFrame, ... }
    """
    loop = asyncio.get_event_loop()

    async def fetch_one(symbol: str):
        df = await loop.run_in_executor(
            None, fetch_historical_data, "binance", symbol
        )
        return symbol, df

    results = await asyncio.gather(*[fetch_one(s) for s in symbols], return_exceptions=True)

    data = {}
    for item in results:
        if isinstance(item, Exception):
            logger.error(f"Fetch error: {item}")
            continue
        symbol, df = item
        data[symbol] = df

    return data


async def _close_position(
    engine: ExecutionEngine,
    position: dict,
    paper_equity: float,
    reason: str = "exit_signal",
) -> float:
    """
    Helper to close an open position and return total PnL.
    """
    pos_type = position["type"]
    symbol_y = position["symbol_y"]
    symbol_x = position["symbol_x"]
    entry_y = position["y_trade"]
    entry_x = position["x_trade"]
    pos_size = paper_equity * settings.MAX_RISK_PER_TRADE

    if pos_type == "SHORT_SPREAD":
        exit_y = engine.execute_trade(symbol_y, "buy", pos_size)
        exit_x = engine.execute_trade(symbol_x, "sell", pos_size)
        pnl_y = engine.log_closed_trade(symbol_y, is_long=False, amount_base=entry_y["amount_base"], entry_price=entry_y["price"], exit_price=exit_y["price"]) if exit_y else 0
        pnl_x = engine.log_closed_trade(symbol_x, is_long=True, amount_base=entry_x["amount_base"], entry_price=entry_x["price"], exit_price=exit_x["price"]) if exit_x else 0
    else:
        exit_y = engine.execute_trade(symbol_y, "sell", pos_size)
        exit_x = engine.execute_trade(symbol_x, "buy", pos_size)
        pnl_y = engine.log_closed_trade(symbol_y, is_long=True, amount_base=entry_y["amount_base"], entry_price=entry_y["price"], exit_price=exit_y["price"]) if exit_y else 0
        pnl_x = engine.log_closed_trade(symbol_x, is_long=False, amount_base=entry_x["amount_base"], entry_price=entry_x["price"], exit_price=exit_x["price"]) if exit_x else 0

    total_pnl = pnl_y + pnl_x
    logger.info(f"Position closed ({reason}). PnL: ${total_pnl:+.2f}")
    return total_pnl


async def main_loop():
    engine = ExecutionEngine()
    killswitch = KillSwitch(max_failures=3)

    all_symbols = get_all_symbols()
    logger.info(f"Watchlist symbols: {all_symbols}")

    # Load persisted state so position tracking survives restarts
    state = load_state()
    current_position: dict | None = state.get("current_position")
    paper_equity: float = state.get("paper_equity", settings.PAPER_EQUITY)

    send_telegram_message(
        f"🟢 <b>Trading Bot Started</b>\n"
        f"Scanning {len(all_symbols)} symbols each cycle.\n"
        f"Paper Equity: ${paper_equity:,.2f}"
    )
    logger.info("Starting main bot loop...")

    # Initialize live price cache and WebSocket streamer
    live_prices: dict[str, float] = {}
    
    def on_tick(symbol, price):
        live_prices[symbol] = price

    streamer = BinanceStreamer(all_symbols, on_tick)
    asyncio.create_task(streamer.start())
    
    # Wait for initial ticks to populate
    logger.info("Waiting for WebSocket ticks...")
    await asyncio.sleep(5)

    last_heartbeat = time.time()

    while not killswitch.is_triggered:
        try:
            now = time.time()
            if now - last_heartbeat > 3600:
                pos_str = (
                    f"{current_position['type']} on {current_position['symbol_y']}/{current_position['symbol_x']}"
                    if current_position else "Flat (no open position)"
                )
                send_telegram_message(
                    f"💓 <b>Heartbeat</b>\n"
                    f"Equity: ${paper_equity:,.2f}\n"
                    f"Position: {pos_str}"
                )
                last_heartbeat = now

            logger.info("--- New Cycle ---")

            # 1. Fetch all symbols concurrently (for historical context)
            logger.info(f"Fetching {len(all_symbols)} symbols...")
            data = await fetch_all(all_symbols)

            # Update historical data with the absolute latest WebSocket price
            for sym, df in data.items():
                if sym in live_prices:
                   # Overlay the last row's close with the live tick
                   df.loc[df.index[-1], "close"] = live_prices[sym]

            if not data:
                raise Exception("No data returned from any symbol.")

            # 2. Scan all pairs — find best cointegrated one
            logger.info("Scanning pairs for cointegration...")
            best = scan_for_best_pair(data)

            if best is None:
                logger.warning("No cointegrated pairs found this cycle.")
                send_telegram_message("⚠️ <b>No Cointegrated Pairs</b>\nAll pairs failed the ADF test. Waiting...")

                # Safety: close open position if its pair lost cointegration
                if current_position is not None:
                    logger.warning("Closing open position — pair no longer cointegrated.")
                    pnl = await _close_position(engine, current_position, paper_equity, reason="cointegration_lost")
                    paper_equity += pnl
                    current_position = None
                    save_state(current_position, paper_equity)

                await asyncio.sleep(60)
                continue

            # 3. If open position is on a different pair, close it first
            if current_position is not None:
                open_pair = (current_position["symbol_y"], current_position["symbol_x"])
                if open_pair != (best.symbol_y, best.symbol_x):
                    logger.info(f"Pair rotated: {open_pair} → ({best.symbol_y}, {best.symbol_x}). Closing.")
                    pnl = await _close_position(engine, current_position, paper_equity, reason="pair_rotation")
                    paper_equity += pnl
                    current_position = None
                    save_state(current_position, paper_equity)
                    send_telegram_message(
                        f"🔄 <b>Pair Rotation</b>\n"
                        f"Closed {open_pair[0]}/{open_pair[1]}\n"
                        f"Now trading: {best.symbol_y}/{best.symbol_x}\n"
                        f"PnL on close: ${pnl:+,.2f}"
                    )

            # 4. Z-Score signal
            z_score_series = calculate_zscore(best.spread)
            if z_score_series.empty or z_score_series.isna().iloc[-1]:
                logger.warning("Z-Score not ready. Skipping.")
                await asyncio.sleep(60)
                continue

            current_z = float(z_score_series.iloc[-1])
            logger.info(f"Z-Score [{best.symbol_y}/{best.symbol_x}]: {current_z:.2f}")
            
            # Check Hard Stop Losses (Drawdown or Extreme Z-Score)
            if current_position is not None:
                # 1. Z-Score divergence stop
                if abs(current_z) >= settings.MAX_Z_SCORE_STOP:
                    logger.critical(f"Extreme Z-Score Stop Loss Hit: {current_z:.2f}")
                    pnl = await _close_position(engine, current_position, paper_equity, reason="extreme_zscore_stop")
                    paper_equity += pnl
                    current_position = None
                    save_state(current_position, paper_equity)
                    send_telegram_message(
                        f"🚨 <b>STOP LOSS: Extreme Z-Score</b>\n"
                        f"Z-Score hit {current_z:.2f}. Forcing exit.\n"
                        f"PnL: ${pnl:+,.2f}\n"
                        f"Equity: ${paper_equity:,.2f}"
                    )
                    continue

                # 2. Equity Drawdown or Time Stop
                # We need the most recent ticker prices. Since we just fetched OHLCV in `fetch_all`,
                # we can approximate current prices using the last close, or fetch live tickers.
                # To save API calls, we'll use the last close from the dataframe.
                current_tickers_approx = {
                    s: {"last": df["close"].iloc[-1]} for s, df in data.items()
                }
                
                stop_reason = check_stop_loss(current_position, current_tickers_approx, paper_equity)
                if stop_reason:
                    logger.critical(f"Risk Manager Stop Hit: {stop_reason}")
                    pnl = await _close_position(engine, current_position, paper_equity, reason=stop_reason)
                    paper_equity += pnl
                    current_position = None
                    save_state(current_position, paper_equity)
                    send_telegram_message(
                        f"🚨 <b>STOP LOSS TRIGGERED</b>\n"
                        f"Reason: {stop_reason}\n"
                        f"PnL: ${pnl:+,.2f}\n"
                        f"Equity: ${paper_equity:,.2f}"
                    )
                    continue

            current_z = float(z_score_series.iloc[-1])
            logger.info(f"Z-Score [{best.symbol_y}/{best.symbol_x}]: {current_z:.2f}")

            signal = generate_signals(current_z)
            pos_size = calculate_position_size(paper_equity)
            current_type = current_position["type"] if current_position else None

            # 5. Execute
            if signal == "SELL_SPREAD" and current_type != "SHORT_SPREAD":
                trade_y = engine.execute_trade(best.symbol_y, "sell", pos_size)
                trade_x = engine.execute_trade(best.symbol_x, "buy", pos_size)
                if trade_y and trade_x:
                    current_position = {
                        "type": "SHORT_SPREAD",
                        "symbol_y": best.symbol_y,
                        "symbol_x": best.symbol_x,
                        "y_trade": trade_y,
                        "x_trade": trade_x,
                        "opened_at": datetime.now().isoformat()
                    }
                    save_state(current_position, paper_equity)
                    send_telegram_message(
                        f"📉 <b>Entry: Short Spread</b>\n"
                        f"Pair: {best.symbol_y} / {best.symbol_x}\n"
                        f"Z-Score: {current_z:.2f} | p-value: {best.p_value:.4f}\n"
                        f"Sold {best.symbol_y} @ ${trade_y['price']:,.2f}\n"
                        f"Bought {best.symbol_x} @ ${trade_x['price']:,.2f}\n"
                        f"Size: ${pos_size:,.2f}"
                    )

            elif signal == "BUY_SPREAD" and current_type != "LONG_SPREAD":
                trade_y = engine.execute_trade(best.symbol_y, "buy", pos_size)
                trade_x = engine.execute_trade(best.symbol_x, "sell", pos_size)
                if trade_y and trade_x:
                    current_position = {
                        "type": "LONG_SPREAD",
                        "symbol_y": best.symbol_y,
                        "symbol_x": best.symbol_x,
                        "y_trade": trade_y,
                        "x_trade": trade_x,
                        "opened_at": datetime.now().isoformat()
                    }
                    save_state(current_position, paper_equity)
                    send_telegram_message(
                        f"📈 <b>Entry: Long Spread</b>\n"
                        f"Pair: {best.symbol_y} / {best.symbol_x}\n"
                        f"Z-Score: {current_z:.2f} | p-value: {best.p_value:.4f}\n"
                        f"Bought {best.symbol_y} @ ${trade_y['price']:,.2f}\n"
                        f"Sold {best.symbol_x} @ ${trade_x['price']:,.2f}\n"
                        f"Size: ${pos_size:,.2f}"
                    )

            elif signal == "EXIT_SPREAD" and current_position is not None:
                pnl = await _close_position(engine, current_position, paper_equity, reason="exit_signal")
                paper_equity += pnl
                current_position = None
                save_state(current_position, paper_equity)
                send_telegram_message(
                    f"✅ <b>Exit</b>\n"
                    f"Z-Score: {current_z:.2f}\n"
                    f"💰 Trade PnL: ${pnl:+,.2f}\n"
                    f"📊 Total Equity: ${paper_equity:,.2f}"
                )

            killswitch.record_success()
            logger.info("Cycle complete. Waiting for next tick window...")
            
            # Using a smaller sleep since we are now tick-driven/cached
            await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            send_telegram_message(f"❌ <b>Error</b>\n{e}")
            killswitch.record_failure()
            if killswitch.is_triggered:
                send_telegram_message("🛑 <b>Killswitch Engaged</b>\nToo many failures. Bot stopped.")
                break
            await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
        send_telegram_message("🛑 <b>Bot Stopped Manually</b>")