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
    ...
    Returns list of UNFILLED FVGs only (filled ones are irrelevant).
    """
    fvgs = []
    pip_value = get_pip_value(symbol)
    
    # Needs at least 3 candles to form an FVG
    for i in range(2, len(df)):
        candle_1 = df.iloc[i-2]
        candle_2 = df.iloc[i-1]
        candle_3 = df.iloc[i]
        
        # Bullish FVG: candle[i-2].high < candle[i].low
        if candle_1['high'] < candle_3['low']:
            top = candle_3['low']
            bottom = candle_1['high']
            size = top - bottom
            
            size_pips = size / pip_value
            
            if size_pips >= min_size_pips:
                fvg = FVG(
                    type="BULLISH",
                    top=top,
                    bottom=bottom,
                    midpoint=(top + bottom) / 2,
                    formed_at=candle_2.name if hasattr(candle_2, 'name') else None,
                    is_filled=False,
                    size_pips=size_pips
                )
                
                # Check if it was filled in subsequent candles
                is_filled = False
                for j in range(i+1, len(df)):
                    if df.iloc[j]['low'] <= fvg.bottom:
                        is_filled = True
                        break
                
                if not is_filled:
                    fvgs.append(fvg)
                    
        # Bearish FVG: candle[i-2].low > candle[i].high
        elif candle_1['low'] > candle_3['high']:
            top = candle_1['low']
            bottom = candle_3['high']
            size = top - bottom
            size_pips = size / pip_value
            
            if size_pips >= min_size_pips:
                fvg = FVG(
                    type="BEARISH",
                    top=top,
                    bottom=bottom,
                    midpoint=(top + bottom) / 2,
                    formed_at=candle_2.name if hasattr(candle_2, 'name') else None,
                    is_filled=False,
                    size_pips=size_pips
                )
                
                # Check if it was filled in subsequent candles
                is_filled = False
                for j in range(i+1, len(df)):
                    if df.iloc[j]['high'] >= fvg.top:
                        is_filled = True
                        break
                
                if not is_filled:
                    fvgs.append(fvg)
                    
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
                if dist_pips <= 2.0:
                    active_fvgs.append(fvg)
        elif direction == "SHORT" and fvg.type == "BEARISH":
            # For short, we want to sell when price approaches the FVG from below
            if current_price < fvg.midpoint:
                dist_pips = (fvg.midpoint - current_price) / pip_value
                if dist_pips <= 2.0:
                    active_fvgs.append(fvg)
                    
    return active_fvgs
