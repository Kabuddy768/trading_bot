import ccxt
import pandas as pd
from utils.logger import logger
from utils.config import settings

def fetch_historical_data(
    exchange_id: str, 
    symbol: str, 
    timeframe: str = settings.CANDLE_TIMEFRAME, 
    limit: int = settings.CANDLE_LIMIT,
    since_date: str = None,
    until_date: str = None
) -> pd.DataFrame:
    """
    Fetches historical OHLCV data for a given symbol from the specified exchange.
    If since_date and until_date are provided (e.g. '2026-01-01'), paginates to fetch the full range.
    """
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({
            'enableRateLimit': True,
        })
        
        # Determine milliseconds
        since_ms = None
        until_ms = None
        
        if since_date:
            since_ms = exchange.parse8601(f"{since_date}T00:00:00Z")
        if until_date:
            until_ms = exchange.parse8601(f"{until_date}T23:59:59Z")
            
        all_ohlcv = []
        
        if since_ms and until_ms:
            logger.info(f"Fetching {timeframe} data for {symbol} from {since_date} to {until_date}...")
            # Paginate through time
            current_since = since_ms
            max_limit = 1000 # Binance max per request
            
            while current_since < until_ms:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=max_limit)
                if not ohlcv:
                    break
                    
                # If we get data past our until boundary, filter and break
                if ohlcv[-1][0] > until_ms:
                    ohlcv = [c for c in ohlcv if c[0] <= until_ms]
                    all_ohlcv.extend(ohlcv)
                    break
                    
                all_ohlcv.extend(ohlcv)
                
                # Advance since pointer to exactly 1 millisecond past the last fetched candle
                current_since = ohlcv[-1][0] + 1
        else:
            # Use raw limit instead
            logger.info(f"Fetching {limit} recent candles of {timeframe} data for {symbol} on {exchange_id}...")
            all_ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not all_ohlcv:
            logger.error(f"No data returned for {symbol}.")
            return pd.DataFrame()
            
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Remove duplicates just in case pagination overlapped
        df = df[~df.index.duplicated(keep='last')]
        
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()
