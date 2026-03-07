import asyncio
import sys
import time
from datetime import datetime, timezone

from utils.logger import logger
from utils.config import settings
from utils.telegram import send_telegram_message

from data.fetcher import fetch_historical_data
from strategy.cointegration import calculate_spread, check_cointegration, calculate_zscore, generate_signals
from risk.manager import KillSwitch, calculate_position_size
from execution.engine import ExecutionEngine

# Fix for Windows asyncio loop policy (specifically for CCXT/WebSockets)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main_loop():
    engine = ExecutionEngine()
    killswitch = KillSwitch(max_failures=3)
    
    symbol_y = "BTC/USDT"
    symbol_x = "ETH/USDT"
    
    send_telegram_message("🟢 <b>Trading Bot Started</b>\nMonitoring the BTC/ETH spread...")
    logger.info("Starting main bot loop...")
    
    last_heartbeat = time.time()
    
    # State tracking
    # current_position can be None or a dict holding entry trade details:
    # {"type": "LONG_SPREAD"|"SHORT_SPREAD", "y_trade": dict, "x_trade": dict}
    current_position = None
    
    while not killswitch.is_triggered:
        try:
            # Hourly heartbeat
            now = time.time()
            if now - last_heartbeat > 3600:
                send_telegram_message("💓 <b>Bot Heartbeat</b>\nStatus: Running gracefully.")
                last_heartbeat = now
                
            logger.info("--- New Cycle ---")
            
            # 1. Fetch Data
            df_y = fetch_historical_data("binance", symbol_y)
            df_x = fetch_historical_data("binance", symbol_x)
            
            if df_y.empty or df_x.empty:
                raise Exception("Empty dataframes returned from exchange.")
                
            # 2. Strategy Calculation
            # We align close prices
            series_y = df_y['close']
            series_x = df_x['close']
            
            spread = calculate_spread(series_y, series_x)
            if spread.empty:
                logger.warning("Spread is empty. Skipping cycle.")
                await asyncio.sleep(60)
                continue
                
            is_coint = check_cointegration(spread)
            
            # Send ADF result if not cointegrated
            if not is_coint:
                msg = f"⚠️ <b>Cointegration Lost</b>\nPair {symbol_y} vs {symbol_x} is no longer cointegrated."
                logger.warning(msg)
                send_telegram_message(msg)
                await asyncio.sleep(60)
                continue
                
            z_score_series = calculate_zscore(spread)
            if z_score_series.empty or z_score_series.isna().iloc[-1]:
                logger.warning("Z-Score valid dataset not available yet.")
                await asyncio.sleep(60)
                continue
                
            current_z = z_score_series.iloc[-1]
            logger.info(f"Calculated Z-Score: {current_z:.2f} - No Action" if abs(current_z) < 2.0 else f"Calculated Z-Score: {current_z:.2f}")
            
            signal = generate_signals(current_z)
            
            # 3. Execution & Position Sizing
            pos_size = calculate_position_size(settings.PAPER_EQUITY)
            
            if signal == "SELL_SPREAD" and (current_position is None or current_position["type"] != "SHORT_SPREAD"):
                logger.info("Executing SELL_SPREAD")
                trade_y = engine.execute_trade(symbol_y, "sell", pos_size)
                trade_x = engine.execute_trade(symbol_x, "buy", pos_size)
                
                if trade_y and trade_x:
                    current_position = {
                        "type": "SHORT_SPREAD",
                        "y_trade": trade_y,
                        "x_trade": trade_x
                    }
                    send_telegram_message(f"📉 <b>Entry (Short Spread)</b>\nZ-Score: {current_z:.2f}\nAction: Sold {symbol_y}, Bought {symbol_x}")
                
            elif signal == "BUY_SPREAD" and (current_position is None or current_position["type"] != "LONG_SPREAD"):
                logger.info("Executing BUY_SPREAD")
                trade_y = engine.execute_trade(symbol_y, "buy", pos_size)
                trade_x = engine.execute_trade(symbol_x, "sell", pos_size)
                
                if trade_y and trade_x:
                    current_position = {
                        "type": "LONG_SPREAD",
                        "y_trade": trade_y,
                        "x_trade": trade_x
                    }
                    send_telegram_message(f"📈 <b>Entry (Long Spread)</b>\nZ-Score: {current_z:.2f}\nAction: Bought {symbol_y}, Sold {symbol_x}")
                
            elif signal == "EXIT_SPREAD" and current_position is not None:
                logger.info("Executing EXIT_SPREAD")
                pos_type = current_position["type"]
                entry_y = current_position["y_trade"]
                entry_x = current_position["x_trade"]
                
                # Flattening out the positions
                if pos_type == "SHORT_SPREAD":
                    # We had sold Y and bought X. Now we buy Y and sell X.
                    exit_y = engine.execute_trade(symbol_y, "buy", pos_size)
                    exit_x = engine.execute_trade(symbol_x, "sell", pos_size)
                    
                    pnl_y = engine.log_closed_trade(symbol_y, is_long=False, amount_base=entry_y['amount_base'], entry_price=entry_y['price'], exit_price=exit_y['price']) if exit_y else 0
                    pnl_x = engine.log_closed_trade(symbol_x, is_long=True, amount_base=entry_x['amount_base'], entry_price=entry_x['price'], exit_price=exit_x['price']) if exit_x else 0
                    
                else: # LONG_SPREAD
                    # We had bought Y and sold X. Now we sell Y and buy X.
                    exit_y = engine.execute_trade(symbol_y, "sell", pos_size)
                    exit_x = engine.execute_trade(symbol_x, "buy", pos_size)

                    pnl_y = engine.log_closed_trade(symbol_y, is_long=True, amount_base=entry_y['amount_base'], entry_price=entry_y['price'], exit_price=exit_y['price']) if exit_y else 0
                    pnl_x = engine.log_closed_trade(symbol_x, is_long=False, amount_base=entry_x['amount_base'], entry_price=entry_x['price'], exit_price=exit_x['price']) if exit_x else 0

                total_pnl = pnl_y + pnl_x
                current_position = None
                send_telegram_message(f"✅ <b>Exit</b>\nZ-Score returned to ~0 ({current_z:.2f}). Positions closed.\n💰 <b>Total PnL:</b> ${total_pnl:.2f}")
            
            # On success, clear the killswitch failures
            killswitch.record_success()
            logger.info("Cycle complete. Waiting 60 seconds...")
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            send_telegram_message(f"❌ <b>Error</b>\nException in main loop: {e}")
            killswitch.record_failure()
            if killswitch.is_triggered:
                send_telegram_message("🛑 <b>Killswitch Engaged</b>\nToo many consecutive API failures. Bot stopped.")
                break
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually by user.")
        send_telegram_message("🛑 <b>Bot Stopped Manually</b>")
