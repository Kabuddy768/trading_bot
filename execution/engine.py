import os
import ccxt
import time
from datetime import datetime
from utils.config import settings
from utils.logger import logger
from utils.database import db
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
        If PAPER_TRADING is true, simulates execution using current ticker with slippage.
        """
        try:
            ticker = self.fetch_ticker(symbol)
            
            if self.paper_trading:
                # Apply slippage penalty: buy higher, sell lower
                ask_price = ticker['ask'] * (1 + settings.PAPER_SLIPPAGE)
                bid_price = ticker['bid'] * (1 - settings.PAPER_SLIPPAGE)
                current_price = bid_price if side == 'sell' else ask_price
            else:
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
                # Use Maker Limit Orders to save fees. 
                # Place limit order at current bid/ask
                limit_price = current_price
                logger.info(f"[LIVE TRADE] Placing LIMIT {side.upper()} {amount_base:.6f} {symbol} @ {limit_price}")
                
                self.enforce_rate_limit()
                order = self.exchange.create_limit_order(symbol, side, amount_base, limit_price)
                order_id = order['id']
                logger.info(f"Order placed: {order_id}. Waiting for fill...")
                
                # Order tracking loop (simple polling for demonstration)
                # In a serious production system with websockets, we wouldn't block here
                max_retries = 12 # Wait up to 60 seconds (12 * 5s)
                for _ in range(max_retries):
                    time.sleep(5)
                    self.enforce_rate_limit()
                    order_status = self.exchange.fetch_order(order_id, symbol)
                    
                    if order_status['status'] == 'closed':
                        logger.success(f"Trade successfully FILLED: {order_id}")
                        result['price'] = order_status.get('average', limit_price)
                        return result
                        
                    elif order_status['status'] in ['canceled', 'rejected']:
                        logger.error(f"Order {order_id} was {order_status['status']} before filling.")
                        return None
                        
                # Timeout reached
                logger.warning(f"Order {order_id} timed out. Canceling...")
                self.enforce_rate_limit()
                self.exchange.cancel_order(order_id, symbol)
                return None
                
            logger.warning("Neither PAPER_TRADING nor LIVE_TRADING is enabled. No action taken.")
            return None
            
        except Exception as e:
            logger.error(f"Error executing trade for {symbol}: {e}")
            raise e

    def log_closed_trade(self, symbol: str, is_long: bool, amount_base: float, entry_price: float, exit_price: float):
        """Calculates PnL for a closed position, deducts simulated fees, and logs it to the database"""
        if is_long:
            gross_pnl = (exit_price - entry_price) * amount_base
        else: # Short
            gross_pnl = (entry_price - exit_price) * amount_base
            
        # Calculate fees for both entry and exit volume
        total_volume_usd = (entry_price * amount_base) + (exit_price * amount_base)
        fee_usd = total_volume_usd * settings.PAPER_FEE_RATE if self.paper_trading else 0.0
        
        net_pnl = gross_pnl - fee_usd
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        side_str = "LONG" if is_long else "SHORT"
        
        db.insert_trade(timestamp, symbol, side_str, amount_base, entry_price, exit_price, net_pnl)
            
        logger.info(f"Logged PnL for {symbol} {side_str}: ${net_pnl:.2f} (Gross: ${gross_pnl:.2f}, Fees: ${fee_usd:.2f})")
        return net_pnl
