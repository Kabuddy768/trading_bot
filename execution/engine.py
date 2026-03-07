import os
import csv
import ccxt
import time
from datetime import datetime
from utils.config import settings
from utils.logger import logger
from typing import Dict, Any, Optional

class ExecutionEngine:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': settings.BINANCE_API_KEY,
            'secret': settings.BINANCE_API_SECRET,
            'enableRateLimit': True,
        })
        self.paper_trading = settings.PAPER_TRADING
        self.live_trading = settings.LIVE_TRADING
        self.last_api_call = 0
        
        # Ensure our trade log exists
        self.csv_path = "trades.csv"
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Pair", "Side", "Amount", "EntryPrice", "ExitPrice", "PnL_USD"])
        
    def enforce_rate_limit(self):
        """Ensure we don't hit the API more than once every 10 seconds per spec."""
        now = time.time()
        elapsed = now - self.last_api_call
        if elapsed < 10.0:
            sleep_time = 10.0 - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds.")
            time.sleep(sleep_time)
        self.last_api_call = time.time()

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        self.enforce_rate_limit()
        logger.info(f"Fetching ticker for {symbol}...")
        return self.exchange.fetch_ticker(symbol)

    def execute_trade(self, symbol: str, side: str, amount_usd: float) -> Optional[Dict[str, Any]]:
        """
        Executes a trade. Returns a dict with trade details if successful, else None.
        If PAPER_TRADING is true, simulates execution using current ticker.
        """
        try:
            ticker = self.fetch_ticker(symbol)
            current_price = ticker['bid'] if side == 'sell' else ticker['ask']
            
            # Simplified amount calculation
            amount_base = amount_usd / current_price
            
            result = {
                "symbol": symbol,
                "side": side,
                "amount_usd": amount_usd,
                "amount_base": amount_base,
                "price": current_price,
            }
            
            if self.paper_trading:
                logger.info(f"[PAPER TRADE] {side.upper()} {amount_base:.6f} {symbol} @ {current_price:.2f} USD = {amount_usd:.2f} USD")
                return result
                
            if self.live_trading:
                logger.info(f"[LIVE TRADE] Executing {side.upper()} {amount_base:.6f} {symbol} @ market")
                self.enforce_rate_limit()
                order = self.exchange.create_market_order(symbol, side, amount_base)
                logger.success(f"Trade successful: {order['id']}")
                result['price'] = order.get('average', current_price) # Use actual fill price if available
                return result
                
            logger.warning("Neither PAPER_TRADING nor LIVE_TRADING is enabled. No action taken.")
            return None
            
        except Exception as e:
            logger.error(f"Error executing trade for {symbol}: {e}")
            raise e

    def log_closed_trade(self, symbol: str, is_long: bool, amount_base: float, entry_price: float, exit_price: float):
        """Calculates PnL for a closed position and appends it to trades.csv"""
        if is_long:
            pnl = (exit_price - entry_price) * amount_base
        else: # Short
            pnl = (entry_price - exit_price) * amount_base
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        side_str = "LONG" if is_long else "SHORT"
        
        with open(self.csv_path, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, symbol, side_str, amount_base, entry_price, exit_price, pnl])
            
        logger.info(f"Logged PnL for {symbol} {side_str}: ${pnl:.2f}")
        return pnl
