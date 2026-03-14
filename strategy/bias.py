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
    if len(df) < 50: # Increased minimum for EMA and enough pivots
        return "RANGING"

    # Minimal logic for finding local swing highs and lows (5-candle pivot: 2 left, 2 right)
    highs = df['high'].values
    lows = df['low'].values
    
    swing_highs = []
    swing_lows = []
    
    # 2-bar confirmation (reverting from 3-bar)
    for i in range(2, len(df) - 2):
        # Local High
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(highs[i])
            
        # Local Low
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(lows[i])

    # REQUIRE at least 3 confirmed swing highs AND 3 swing lows before calling a trend
    if len(swing_highs) < 3 or len(swing_lows) < 3:
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
    if len(df) < 10:
        return "EQUILIBRIUM"
    
    highs = df['high'].values
    lows = df['low'].values
    
    recent_swing_high = None
    recent_swing_low = None
    
    # Revert to 2-bar confirmation for pivots
    for i in range(len(df) - 3, 2, -1):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            if recent_swing_high is None:
                recent_swing_high = highs[i]
                
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            if recent_swing_low is None:
                recent_swing_low = lows[i]
                
        if recent_swing_high and recent_swing_low:
            break
    
    # If no pivots found (strong trend), returning EQUILIBRIUM is safer than guessing a range
    if not recent_swing_high or not recent_swing_low:
        return "EQUILIBRIUM"
    
    current_price = df['close'].iloc[-1]
    
    if recent_swing_high == recent_swing_low:
        return "EQUILIBRIUM"
        
    midpoint = (recent_swing_high + recent_swing_low) / 2
    equilibrium_buffer = (recent_swing_high - recent_swing_low) * 0.05
    
    if current_price > midpoint + equilibrium_buffer:
        return "PREMIUM"
    elif current_price < midpoint - equilibrium_buffer:
        return "DISCOUNT"
    else:
        return "EQUILIBRIUM"

def get_bias(symbol: str, df_htf: pd.DataFrame) -> dict:
    """
    Master bias function. Combines market structure + premium/discount + EMA filter.
    """
    # 0. EMA 200 Filter
    if len(df_htf) >= 200:
        ema200 = df_htf['close'].ewm(span=200, adjust=False).mean().iloc[-1]
    else:
        ema200 = None

    # 1. Structure Check
    highs = df_htf['high'].values
    lows = df_htf['low'].values
    closes = df_htf['close'].values
    current_price = closes[-1]
    
    swing_highs = []
    swing_lows = []
    for i in range(2, len(df_htf) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(lows[i])

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

    # --- EMA 200 Filter ---
    # Only approve LONG if price is above EMA 200, SHORT if below
    if ema200 is not None:
        if direction == "LONG" and current_price < ema200:
            tradeable = False
        elif direction == "SHORT" and current_price > ema200:
            tradeable = False

    return {
        "symbol": symbol,
        "structure": structure,
        "zone": zone,
        "tradeable": tradeable,
        "direction": direction
    }
