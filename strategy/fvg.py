import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from utils.config import settings
from risk.manager import get_pip_value

@dataclass
class FVG:
    type: str           # "BULLISH" or "BEARISH"
    top: float          # Upper boundary of the gap
    bottom: float       # Lower boundary of the gap
    midpoint: float     # (top + bottom) / 2
    formed_at: datetime # Timestamp of the middle candle
    is_filled: bool     # True if price has since closed inside the gap
    size_pips: float    # Gap size in pips

def detect_fvgs(df: pd.DataFrame, symbol: str, min_size_pips: float = settings.FVG_MIN_SIZE_PIPS) -> list[FVG]:
    """
    Scans all candles in df for bullish and bearish FVGs.
    Returns list of UNFILLED FVGs only (filled ones are irrelevant).
    """
    fvgs = []
    pip_value = get_pip_value(symbol)
    
    if len(df) < 3:
        return []

    # Vectorized acceleration: use numpy arrays for O(1) access instead of .iloc
    highs = df['high'].values
    lows = df['low'].values
    times = df.index.values

    # Needs at least 3 candles to form an FVG
    for i in range(2, len(df)):
        # Bullish FVG: high[i-2] < low[i]
        if highs[i-2] < lows[i]:
            top = lows[i]
            bottom = highs[i-2]
            size_pips = (top - bottom) / pip_value
            
            if size_pips >= min_size_pips:
                # Optimized fill check: check if any subsequent candle's low is <= FVG bottom
                is_filled = (lows[i+1:] <= bottom).any()
                
                if not is_filled:
                    fvgs.append(FVG(
                        type="BULLISH",
                        top=top,
                        bottom=bottom,
                        midpoint=(top + bottom) / 2,
                        formed_at=times[i-1],
                        is_filled=False,
                        size_pips=size_pips
                    ))
                    
        # Bearish FVG: low[i-2] > high[i]
        elif lows[i-2] > highs[i]:
            top = lows[i-2]
            bottom = highs[i]
            size_pips = (top - bottom) / pip_value
            
            if size_pips >= min_size_pips:
                # Optimized fill check: check if any subsequent candle's high is >= FVG top
                is_filled = (highs[i+1:] >= top).any()
                
                if not is_filled:
                    fvgs.append(FVG(
                        type="BEARISH",
                        top=top,
                        bottom=bottom,
                        midpoint=(top + bottom) / 2,
                        formed_at=times[i-1],
                        is_filled=False,
                        size_pips=size_pips
                    ))
                    
    return fvgs

def get_active_fvgs(df: pd.DataFrame, symbol: str, current_price: float, direction: str) -> list[FVG]:
    """
    Returns only the FVGs that are:
    ...
    3. Price is currently approaching (within 10 pips above/below midpoint)
    """
    all_fvgs = detect_fvgs(df, symbol)
    active_fvgs = []
    pip_value = get_pip_value(symbol)
    
    for fvg in all_fvgs:
        if direction == "LONG" and fvg.type == "BULLISH":
            # For long, we want to buy when price approaches the FVG from above
            if current_price > fvg.midpoint:
                dist_pips = (current_price - fvg.midpoint) / pip_value
                if dist_pips <= 10.0:
                    active_fvgs.append(fvg)
        elif direction == "SHORT" and fvg.type == "BEARISH":
            # For short, we want to sell when price approaches the FVG from below
            if current_price < fvg.midpoint:
                dist_pips = (fvg.midpoint - current_price) / pip_value
                if dist_pips <= 10.0:
                    active_fvgs.append(fvg)
                    
    return active_fvgs
