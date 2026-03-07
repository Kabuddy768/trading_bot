import ccxt
import time
from utils.config import settings
from utils.logger import logger
from typing import Dict, Any

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

    def execute_trade(self, symbol: str, side: str, amount_usd: float) -> bool:
        """
        Executes a trade.
        If PAPER_TRADING is true, simulates execution using current ticker.
        """
        try:
            ticker = self.fetch_ticker(symbol)
            current_price = ticker['bid'] if side == 'sell' else ticker['ask']
            
            # Simplified amount calculation
            amount_base = amount_usd / current_price
            
            if self.paper_trading:
                logger.info(f"[PAPER TRADE] {side.upper()} {amount_base:.6f} {symbol} @ {current_price:.2f} USD = {amount_usd:.2f} USD")
                return True
                
            if self.live_trading:
                logger.info(f"[LIVE TRADE] Executing {side.upper()} {amount_base:.6f} {symbol} @ market")
                self.enforce_rate_limit()
                order = self.exchange.create_market_order(symbol, side, amount_base)
                logger.success(f"Trade successful: {order['id']}")
                return True
                
            logger.warning("Neither PAPER_TRADING nor LIVE_TRADING is enabled. No action taken.")
            return False
            
        except Exception as e:
            logger.error(f"Error executing trade for {symbol}: {e}")
            raise e
