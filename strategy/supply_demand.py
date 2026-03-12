import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from utils.config import settings
from risk.manager import get_pip_value

@dataclass
class Zone:
    type: str           # "SUPPLY" or "DEMAND"
    top: float          # Upper boundary
    bottom: float       # Lower boundary
    strength: int       # Number of times price has returned to it
    is_fresh: bool      # True if price has never returned since formation
    formed_at: datetime
    proximal_line: float  # The edge closest to current price (entry edge)
    distal_line: float    # The edge furthest from current price (SL reference)

def detect_zones(df: pd.DataFrame, symbol: str, min_impulse_pips: float = 10.0) -> list[Zone]:
    """
    Identifies Supply and Demand zones by:
    1. Finding candles/areas with strong departure moves (big impulse away)
    2. Measuring the consolidation base before the move (1-3 small candles)
    Returns all active (unbroken) zones.
    """
    zones = []
    pip_value = get_pip_value(symbol)
    
    if len(df) < 5:
        return []

    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    closes = df['close'].values
    times = df.index.values
    
    # We'll look for impulse candles first
    for i in range(5, len(df) - 1):
        # Body size of the departure candle
        body_size_pips = abs(closes[i] - opens[i]) / pip_value
        
        if body_size_pips >= min_impulse_pips:
            # departure candle i
            is_bullish = closes[i] > opens[i]
            
            # --- Base Identification ---
            # Scan back for 1–3 small "base" candles
            # A base is valid if it forms a consolidation (range doesn't exceed 40% of impulse)
            base_candles = []
            base_idx_start = -1
            
            for b in range(i-1, i-4, -1):
                b_body_pips = abs(closes[b] - opens[b]) / pip_value
                # If we encounter another high-volatility candle, base ends here
                if b_body_pips > (min_impulse_pips * 0.4):
                    break
                base_candles.append(b)
                base_idx_start = b
            
            if not base_candles:
                continue
                
            # Define zone boundaries based on the entire base range
            base_highs = highs[base_idx_start:i]
            base_lows = lows[base_idx_start:i]
            
            top = base_highs.max()
            bottom = base_lows.min()
            
            zone_type = "DEMAND" if is_bullish else "SUPPLY"
            
            # Track tests and validity
            tested_count = 0
            is_broken = False
            
            # Sub-view from i+1 to end
            sub_closes = closes[i+1:]
            sub_highs = highs[i+1:]
            sub_lows = lows[i+1:]
            
            if zone_type == "DEMAND":
                # Check for closes BELOW bottom (breaking)
                mask_break = sub_closes < bottom
                if mask_break.any():
                    is_broken = True
                    # If price closed below, any "test" after that doesn't count
                    broken_pos = mask_break.argmax()
                    sub_highs = sub_highs[:broken_pos]
                    sub_lows = sub_lows[:broken_pos]
                
                # Check for tests (low enters zone top/bottom range)
                tested_count = ((sub_lows <= top) & (sub_lows > bottom)).sum()
            else: # SUPPLY
                # Check for closes ABOVE top (breaking)
                mask_break = sub_closes > top
                if mask_break.any():
                    is_broken = True
                    broken_pos = mask_break.argmax()
                    sub_highs = sub_highs[:broken_pos]
                    sub_lows = sub_lows[:broken_pos]
                    
                # Check for tests (high enters zone top/bottom range)
                tested_count = ((sub_highs >= bottom) & (sub_highs < top)).sum()
                        
            if not is_broken and tested_count <= settings.ZONE_STRENGTH_THRESHOLD:
                zones.append(Zone(
                    type=zone_type,
                    top=top,
                    bottom=bottom,
                    strength=tested_count,
                    is_fresh=(tested_count == 0),
                    formed_at=times[i-1],
                    proximal_line=bottom if zone_type == "DEMAND" else top,
                    distal_line=top if zone_type == "DEMAND" else bottom
                ))
                
    return zones

def get_zones_near_price(
    zones: list[Zone],
    symbol: str,
    current_price: float,
    direction: str,
    proximity_pips: float = 15.0
) -> list[Zone]:
    """
    Returns DEMAND zones near current price for LONG setups.
    Returns SUPPLY zones near current price for SHORT setups.
    Filters by proximity to proximal_line.
    Prioritizes fresh zones over tested ones.
    """
    candidates = []
    pip_value = get_pip_value(symbol)
    
    for zone in zones:
        if direction == "LONG" and zone.type == "DEMAND":
            if current_price > zone.proximal_line:
                dist = (current_price - zone.proximal_line) / pip_value
                if dist <= proximity_pips:
                    candidates.append(zone)
        elif direction == "SHORT" and zone.type == "SUPPLY":
            if current_price < zone.proximal_line:
                dist = (zone.proximal_line - current_price) / pip_value
                if dist <= proximity_pips:
                    candidates.append(zone)
                    
    # Sort by freshness (True first) then by proximity
    candidates.sort(key=lambda x: (not x.is_fresh, abs(current_price - x.proximal_line)))
    
    return candidates
