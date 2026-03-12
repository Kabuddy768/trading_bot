import time
import asyncio
from datetime import datetime
from utils.config import settings
from utils.logger import logger
from utils.database import db
from utils.telegram import send_telegram_message
from data.fetcher import fetch_historical_data
from execution.engine import ExecutionEngine
from risk.manager import calculate_position_size, check_sl_tp, load_state, save_state, KillSwitch, get_pip_value
from strategy.bias import get_bias
from strategy.fvg import detect_fvgs
from strategy.orderblock import detect_order_blocks, detect_breaker_blocks
from strategy.supply_demand import detect_zones
from strategy.confluence import score_setup

class ICTTradingBot:
    def __init__(self):
        self.engine = ExecutionEngine()
        self.killswitch = KillSwitch(max_failures=3)
        self.cooldowns: dict[str, datetime] = {}
        self.state = load_state()
        # load_state already ensures paper_equity and current_positions exist
            
        logger.info("ICT Trading Bot Initialized.")
        send_telegram_message("🤖 ICT Trading Bot Started.")

    async def run(self):
        while True:
            if self.killswitch.is_triggered:
                logger.critical("Bot stopped by KillSwitch.")
                send_telegram_message("🔴 <b>CRITICAL: BOT STOPPED BY KILLSWITCH</b>\nConsecutive API failures reached threshold.")
                break

            try:
                logger.info("--- Starting New Cycle ---")
                
                # Step 1: Fetch Data and Step 2-4: Process each symbol
                for symbol in settings.ICT_SYMBOLS:
                    if self.killswitch.is_triggered: break
                    await self.process_symbol(symbol)
                
                # Step 7: Ongoing Position Monitoring
                if not self.killswitch.is_triggered:
                    await self.monitor_positions()
                
                # Save state
                save_state(self.state["current_positions"], self.state["paper_equity"])
                
                logger.info("Cycle Complete. Sleeping for 60 seconds...")
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self.killswitch.record_failure()
                await asyncio.sleep(60)

    async def process_symbol(self, symbol: str):
        # Already in position? Skip entry logic
        if symbol in self.state["current_positions"]:
            return

        # Cooldown check: don't re-enter within 5 minutes of a stop loss
        if symbol in self.cooldowns:
            elapsed = (datetime.now() - self.cooldowns[symbol]).total_seconds()
            if elapsed < 300:  # 5 minute cooldown
                logger.debug(f"{symbol}: In cooldown ({300-elapsed:.0f}s remaining). Skipping.")
                return

        # Fetch Data
        df_htf = fetch_historical_data("binance", symbol, settings.BIAS_TIMEFRAME, settings.BIAS_CANDLE_LIMIT)
        df_mtf = fetch_historical_data("binance", symbol, settings.SETUP_TIMEFRAME, settings.SETUP_CANDLE_LIMIT)
        
        if df_htf.empty or df_mtf.empty:
            return

        # Step 2: HTF Bias Check
        bias = get_bias(symbol, df_htf)
        if not bias["tradeable"]:
            logger.debug(f"{symbol}: No clear HTF bias or price in equilibrium. Skipping.")
            return

        # Step 3: Structure Detection (on 15M)
        current_price = df_mtf['close'].iloc[-1]
        direction = bias["direction"]
        
        fvgs = detect_fvgs(df_mtf, symbol)
        obs = detect_order_blocks(df_mtf, symbol)
        breakers = detect_breaker_blocks(df_mtf, symbol)
        zones = detect_zones(df_mtf, symbol)

        # Step 4: Confluence Scoring
        setup = score_setup(symbol, df_mtf, bias, fvgs, obs, breakers, zones)
        
        if setup:
            logger.success(f"🚀 ICT Setup Detected for {symbol}: Score {setup.confluence_score}")
            await self.execute_entry(setup)
        else:
            logger.debug(f"{symbol}: No valid setup found (Score < MIN).")

    async def execute_entry(self, setup):
        # Calculate size based on equity
        pos_size_usd = calculate_position_size(self.state["paper_equity"])
        
        # Execute Trade
        result = self.engine.execute_trade(setup.symbol, "buy" if setup.direction == "LONG" else "sell", pos_size_usd)
        
        if result:
            # Store SL/TP and other details
            position = {
                "symbol": setup.symbol,
                "direction": setup.direction,
                "entry_price": result["price"],
                "amount_base": result["amount_base"],
                "sl_price": setup.sl_price,
                "tp_price": setup.tp_price,
                "opened_at": datetime.now().isoformat(),
                "confluence_score": setup.confluence_score,
                "confluences": setup.confluences,
                "primary_zone": setup.primary_zone
            }
            
            # Log to DB
            trade_id = db.insert_ict_trade(
                position["opened_at"],
                setup.symbol,
                setup.direction,
                result["price"],
                setup.sl_price,
                setup.tp_price,
                setup.confluence_score,
                setup.confluences,
                setup.primary_zone
            )
            position["trade_id"] = trade_id
            
            self.state["current_positions"][setup.symbol] = position
            
            # Telegram Alert
            pip_value = get_pip_value(setup.symbol)
            sl_pips = abs(result["price"] - setup.sl_price) / pip_value
            tp_pips = abs(setup.tp_price - result["price"]) / pip_value

            msg = (
                f"📍 <b>ICT SETUP DETECTED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Symbol:     {setup.symbol}\n"
                f"Direction:  {'🟢 LONG' if setup.direction == 'LONG' else '🔴 SHORT'}\n"
                f"Timeframe:  {settings.SETUP_TIMEFRAME} / {settings.BIAS_TIMEFRAME}\n\n"
                f"Entry:      ${result['price']:.2f}\n"
                f"Stop Loss:  ${setup.sl_price:.2f}  (-{sl_pips:.1f} pips)\n"
                f"Take Profit: ${setup.tp_price:.2f}  (+{tp_pips:.1f} pips)\n"
                f"R:R Ratio:  1:{(tp_pips/sl_pips):.1f}\n\n"
                f"Confluences (Score: {setup.confluence_score}):\n"
                + "\n".join([f"  ✅ {c}" for c in setup.confluences]) + "\n\n"
                f"Primary Zone: {setup.primary_zone}"
            )
            send_telegram_message(msg)

    async def monitor_positions(self):
        symbols_to_remove = []
        
        for symbol, pos in self.state["current_positions"].items():
            try:
                # Get latest price
                ticker = self.engine.fetch_ticker(symbol)
                self.killswitch.record_success()
                current_price = ticker['last'] or ticker['close']
                
                exit_reason = check_sl_tp(pos, current_price)
                
                # Also check time stop
                opened_at = datetime.fromisoformat(pos["opened_at"])
                hours_open = (datetime.now() - opened_at).total_seconds() / 3600
                if not exit_reason and hours_open >= settings.MAX_TRADE_HOURS:
                    exit_reason = "TIME_STOP"
                    
                if exit_reason:
                    await self.execute_exit(symbol, pos, current_price, exit_reason)
                    symbols_to_remove.append(symbol)
            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")
                self.killswitch.record_failure()
                if self.killswitch.is_triggered: break
                
        for symbol in symbols_to_remove:
            del self.state["current_positions"][symbol]

    async def execute_exit(self, symbol, pos, exit_price, reason):
        # Execute Exit Trade
        if reason == "STOP_LOSS":
            self.cooldowns[symbol] = datetime.now()
            
        side = "sell" if pos["direction"] == "LONG" else "buy"
        # In paper mode, amount_base is what we exit
        amount_usd = pos["amount_base"] * exit_price
        
        result = self.engine.execute_trade(symbol, side, amount_usd)
        
        final_exit_price = result["price"] if result else exit_price
        
        # Calculate PnL
        is_long = (pos["direction"] == "LONG")
        net_pnl = self.engine.log_closed_trade(symbol, is_long, pos["amount_base"], pos["entry_price"], final_exit_price)
        
        # Pips
        pip_value = get_pip_value(symbol)
        pips = (final_exit_price - pos["entry_price"]) / pip_value
        if not is_long:
            pips = -pips
            
        # Update ICT trades table
        db.update_ict_trade_exit(
            pos["trade_id"],
            final_exit_price,
            reason,
            pips,
            net_pnl,
            datetime.now().isoformat()
        )
        
        # Update Equity
        self.state["paper_equity"] += net_pnl
        
        # Telegram Alert
        emoji = "✅" if pips > 0 else "🛑"
        title = "TAKE PROFIT HIT" if reason == "TAKE_PROFIT" else "STOP LOSS HIT"
        if reason == "TIME_STOP":
            title = "TIME STOP HIT"
            
        msg = (
            f"{emoji} <b>{title}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Symbol:     {symbol}\n"
            f"Direction:  {pos['direction']}\n"
            f"Exit Price: ${final_exit_price:.2f}\n"
            f"PnL:        {pips:+.1f} pips / ${net_pnl:+,.2f}\n"
            f"Equity:     ${self.state['paper_equity']:,.2f}"
        )
        send_telegram_message(msg)
        logger.info(f"Position closed for {symbol}: {reason} at {final_exit_price}")

if __name__ == "__main__":
    bot = ICTTradingBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped manually.")
        send_telegram_message("🛑 Bot stopped manually.")
