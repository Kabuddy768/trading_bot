import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from utils.config import settings

@dataclass
class TradeSetup:
    symbol: str
    direction: str          # "LONG" or "SHORT"
    entry_price: float      # Suggested entry (midpoint of primary confluence zone)
    sl_price: float         # Entry ± (SL_PIPS * PIP_VALUE_USDT)
    tp_price: float         # Entry ± (TP_PIPS * PIP_VALUE_USDT)
    confluence_score: int   # Total score
    confluences: List[str]  # Human-readable list of what aligned
    primary_zone: str       # What the main entry zone is (FVG / OB / Zone)
    timeframe: str          # "15m" or "5m"
    timestamp: datetime

def calculate_pip_levels(entry: float, direction: str, symbol: str) -> tuple[float, float]:
    """
    Calculates SL and TP prices from entry based on pip settings.
    """
    from risk.manager import get_pip_value
    multiplier = get_pip_value(symbol)
    sl_dist = settings.SL_PIPS_BY_SYMBOL.get(symbol, 10) * multiplier
    tp_dist = settings.TP_PIPS_BY_SYMBOL.get(symbol, 30) * multiplier
    
    if direction == "LONG":
        sl = entry - sl_dist
        tp = entry + tp_dist
    else: # SHORT
        sl = entry + sl_dist
        tp = entry - tp_dist
        
    return sl, tp

def score_setup(
    symbol: str,
    current_price: float,
    bias: dict,
    fvgs: list,
    obs: list,
    breakers: list,
    zones: list,
) -> Optional[TradeSetup]:
    """
    Combines all detected structures.
    Scores the setup.
    Returns a TradeSetup if score >= MIN_CONFLUENCES, else None.
    Calculates exact entry, SL, and TP prices.
    """
    score = 0
    confluences = []
    primary_zone = "NONE"
    entry_price = current_price
    
    # Required: HTF Bias alignment MUST be present based on structure
    if not bias["tradeable"]:
        return None
        
    direction = bias["direction"]
    confluences.append(f"HTF Bias: {bias['structure']} in {bias['zone']}")
    
    # FVG
    if fvgs:
        score += 1
        confluences.append(f"FVG present ({len(fvgs)})")
        # Use the closest FVG midpoint as entry candidate
        entry_price = fvgs[0].midpoint
        primary_zone = "FVG"
        
    # Order Block
    if obs:
        score += 1
        confluences.append(f"Order Block present ({len(obs)})")
        
        # If overlapping with an FVG, OB proximal edge is a safter, more conservative entry usually
        ob_entry = obs[0].top if direction == "LONG" else obs[0].bottom
        entry_price = ob_entry
        primary_zone = "OB"
            
    # Breaker Block
    if breakers:
        score += 1
        confluences.append(f"Breaker Block present ({len(breakers)})")
        if primary_zone == "NONE":
            entry_price = breakers[0].top if direction == "LONG" else breakers[0].bottom
            primary_zone = "BREAKER"
            
    # Supply/Demand Zone
    if zones:
        zone = zones[0]
        if zone.is_fresh:
            score += 2
            confluences.append(f"Fresh {zone.type} Zone")
        else:
            score += 1
            confluences.append(f"Tested {zone.type} Zone")
            
        if primary_zone == "NONE":
            entry_price = zone.proximal_line
            primary_zone = "ZONE"
            
    # Check if we meet the minimum requirements
    min_required = settings.MIN_CONFLUENCES_BY_SYMBOL.get(symbol, settings.MIN_CONFLUENCES)
    if score >= min_required:
        sl, tp = calculate_pip_levels(entry_price, direction, symbol)
        
        return TradeSetup(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            sl_price=sl,
            tp_price=tp,
            confluence_score=score,
            confluences=confluences,
            primary_zone=primary_zone,
            timeframe=settings.SETUP_TIMEFRAME,
            timestamp=datetime.now()
        )
        
    return None
