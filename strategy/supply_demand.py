import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from utils.config import settings

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

def detect_zones(df: pd.DataFrame, min_impulse_pips: float = 10.0) -> list[Zone]:
    """
    Identifies Supply and Demand zones by:
    1. Finding candles/areas with strong departure moves (big impulse away)
    2. Measuring the consolidation base before the move
    3. Tracking how many times price has returned to test the zone
    4. Marking zones as fresh (untested) or tested
    Returns all active (unbroken) zones.
    """
    zones = []
    
    # Simple logic: A zone is a base (consolidation) followed by an impulse
    # We'll look for impulse candles first
    for i in range(5, len(df) - 1):
        candle = df.iloc[i]
        body_size_pips = abs(candle['close'] - candle['open']) / settings.PIP_VALUE_USDT
        
        if body_size_pips >= min_impulse_pips:
            # Found a potential impulse move
            # Look back for "base" (1-3 candles with small bodies)
            base_idx = i - 1
            base_candle = df.iloc[base_idx]
            
            zone_type = "DEMAND" if candle['close'] > candle['open'] else "SUPPLY"
            
            # Define zone boundaries based on the base candle
            top = max(base_candle['high'], df.iloc[base_idx-1]['high'] if base_idx > 0 else base_candle['high'])
            bottom = min(base_candle['low'], df.iloc[base_idx-1]['low'] if base_idx > 0 else base_candle['low'])
            
            zone = Zone(
                type=zone_type,
                top=top,
                bottom=bottom,
                strength=0,
                is_fresh=True,
                formed_at=base_candle.name if hasattr(base_candle, 'name') else None,
                proximal_line=bottom if zone_type == "DEMAND" else top,
                distal_line=top if zone_type == "DEMAND" else bottom
            )
            
            # Track tests and validity
            tested_count = 0
            is_broken = False
            for j in range(i + 1, len(df)):
                high = df.iloc[j]['high']
                low = df.iloc[j]['low']
                close = df.iloc[j]['close']
                
                # Check for test: price enters the zone but doesn't close beyond it
                if zone.type == "DEMAND":
                    if low <= zone.top and low > zone.bottom:
                        tested_count += 1
                    if close < zone.bottom:
                        is_broken = True
                        break
                else: # SUPPLY
                    if high >= zone.bottom and high < zone.top:
                        tested_count += 1
                    if close > zone.top:
                        is_broken = True
                        break
                        
            if not is_broken and tested_count <= settings.ZONE_STRENGTH_THRESHOLD:
                zone.strength = tested_count
                zone.is_fresh = (tested_count == 0)
                zones.append(zone)
                
    return zones

def get_zones_near_price(
    zones: list[Zone],
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
    
    for zone in zones:
        if direction == "LONG" and zone.type == "DEMAND":
            if current_price > zone.proximal_line:
                dist = (current_price - zone.proximal_line) / settings.PIP_VALUE_USDT
                if dist <= proximity_pips:
                    candidates.append(zone)
        elif direction == "SHORT" and zone.type == "SUPPLY":
            if current_price < zone.proximal_line:
                dist = (zone.proximal_line - current_price) / settings.PIP_VALUE_USDT
                if dist <= proximity_pips:
                    candidates.append(zone)
                    
    # Sort by freshness (True first) then by proximity
    candidates.sort(key=lambda x: (not x.is_fresh, abs(current_price - x.proximal_line)))
    
    return candidates
