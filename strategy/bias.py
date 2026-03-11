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
    if len(df) < 20:
        return "RANGING"

    # Minimal logic for finding local swing highs and lows (5-candle pivot: 2 left, 2 right)
    highs = df['high'].values
    lows = df['low'].values
    
    swing_highs = []
    swing_lows = []
    
    # Needs a minimum of 2 bars on each side
    for i in range(2, len(df) - 2):
        # Local High
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(highs[i])
            
        # Local Low
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(lows[i])

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "RANGING"
        
    # Check Market Structure via latest 2 confirmed swings
    last_hh = swing_highs[-1] > swing_highs[-2]
    last_hl = swing_lows[-1] > swing_lows[-2]
    
    last_lh = swing_highs[-1] < swing_highs[-2]
    last_ll = swing_lows[-1] < swing_lows[-2]
    
    if last_hh and last_hl:
        return "BULLISH"
    elif last_lh and last_ll:
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
        
    # Use the full provided HTF frame context to compute the range
    highest_high = df['high'].max()
    lowest_low = df['low'].min()
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
