import ccxt
import pandas as pd
from utils.logger import logger
from utils.config import settings

def fetch_historical_data(exchange_id: str, symbol: str, timeframe: str = settings.CANDLE_TIMEFRAME, limit: int = settings.CANDLE_LIMIT) -> pd.DataFrame:
    """
    Fetches historical OHLCV data for a given symbol from the specified exchange.
    Returns a pandas DataFrame.
    """
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({
            'enableRateLimit': True,
        })
        
        logger.info(f"Fetching {limit} candles of {timeframe} data for {symbol} on {exchange_id}...")
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcv:
            logger.error(f"No data returned for {symbol}.")
            return pd.DataFrame()
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()
