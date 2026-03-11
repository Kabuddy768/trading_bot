import pandas as pd
from utils.config import settings
from utils.logger import logger

def detect_market_structure(df: pd.DataFrame) -> str:
    """
    Analyzes Higher Highs (HH), Higher Lows (HL) for bullish structure,
    or Lower Highs (LH), Lower Lows (LL) for bearish structure.

    Args:
        df: OHLCV DataFrame on the BIAS_TIMEFRAME (1H)
    Returns:
        "BULLISH" | "BEARISH" | "RANGING"
    """
    if len(df) < 5:
        return "RANGING"

    # Simplified HH/HL detection using rolling windows or last few pivots
    # For a more robust version, we could use scipy.signal.find_peaks
    
    last_highs = df['high'].iloc[-20:].tolist()
    last_lows = df['low'].iloc[-20:].tolist()
    
    # Check for Bullish: Price making overall higher highs and higher lows
    is_bullish = df['high'].iloc[-1] > df['high'].iloc[-10] and df['low'].iloc[-1] > df['low'].iloc[-10]
    
    # Check for Bearish: Price making overall lower highs and lower lows
    is_bearish = df['high'].iloc[-1] < df['high'].iloc[-10] and df['low'].iloc[-1] < df['low'].iloc[-10]
    
    if is_bullish:
        return "BULLISH"
    elif is_bearish:
        return "BEARISH"
    else:
        return "RANGING"

def identify_premium_discount(df: pd.DataFrame) -> str:
    """
    Determines if price is currently in a Premium (above 50% of range = sell zone)
    or Discount (below 50% of range = buy zone) relative to the most recent swing range.

    Returns:
        "PREMIUM" | "DISCOUNT" | "EQUILIBRIUM"
    """
    if len(df) < 20:
        return "EQUILIBRIUM"
        
    recent_range = df.iloc[-50:]
    highest_high = recent_range['high'].max()
    lowest_low = recent_range['low'].min()
    current_price = df['close'].iloc[-1]
    
    midpoint = (highest_high + lowest_low) / 2
    
    if current_price > midpoint:
        return "PREMIUM"
    elif current_price < midpoint:
        return "DISCOUNT"
    else:
        return "EQUILIBRIUM"

def get_bias(symbol: str, df_htf: pd.DataFrame) -> dict:
    """
    Master bias function. Combines market structure + premium/discount.

    Returns dict:
    {
        "symbol": str,
        "structure": "BULLISH" | "BEARISH" | "RANGING",
        "zone": "PREMIUM" | "DISCOUNT" | "EQUILIBRIUM",
        "tradeable": bool,       # True only if structure + zone align
        "direction": "LONG" | "SHORT" | None
    }
    """
    structure = detect_market_structure(df_htf)
    zone = identify_premium_discount(df_htf)
    
    tradeable = False
    direction = None
    
    if structure == "BULLISH" and zone == "DISCOUNT":
        tradeable = True
        direction = "LONG"
    elif structure == "BEARISH" and zone == "PREMIUM":
        tradeable = True
        direction = "SHORT"
        
    return {
        "symbol": symbol,
        "structure": structure,
        "zone": zone,
        "tradeable": tradeable,
        "direction": direction
    }
