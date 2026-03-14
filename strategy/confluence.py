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

def calculate_structural_sl(df_mtf: pd.DataFrame, direction: str, entry: float, symbol: str) -> tuple[Optional[float], Optional[float]]:
    """
    Calculates SL structurally based on recent 15m swings.
    TP is projected using Risk/Reward Ratio based on the SL distance.
    """
    from risk.manager import get_pip_value
    pip_value = get_pip_value(symbol)
    
    if direction == "LONG":
        # SL goes below the most recent swing low in the last 20 candles
        recent_low = df_mtf['low'].iloc[-20:].min()
        sl = recent_low - (2 * pip_value)
    else:
        recent_high = df_mtf['high'].iloc[-20:].max()
        sl = recent_high + (2 * pip_value)
            
    # SL MUST be correctly positioned relative to entry
    if direction == "LONG" and sl >= entry:
        sl = entry - (10 * pip_value)
    elif direction == "SHORT" and sl <= entry:
        sl = entry + (10 * pip_value)
            
    sl_dist = abs(entry - sl)
    
    # Enforce min/max SL distance
    min_sl = 10 * pip_value
    max_sl = 200 * pip_value
    
    if sl_dist < min_sl:
        sl_dist = min_sl
        sl = entry - min_sl if direction == "LONG" else entry + min_sl
        
    if sl_dist > max_sl:
        return None, None
        
    rr_ratio = getattr(settings, 'RR_RATIO', 3.0)
    tp = entry + (sl_dist * rr_ratio) if direction == "LONG" else entry - (sl_dist * rr_ratio)
        
    return sl, tp

def score_setup(
    symbol: str,
    df_mtf: pd.DataFrame,
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
    current_price = df_mtf['close'].iloc[-1]
    entry_price = current_price
    direction = bias["direction"]
    
    if not bias["tradeable"]:
        return None

    # --- ATR Exhaustion Filter ---
    # We use average candle range over the last 20 candles
    avg_candle_range = (df_mtf['high'] - df_mtf['low']).rolling(20).mean()
    current_range = df_mtf['high'].iloc[-1] - df_mtf['low'].iloc[-1]
    multiplier = getattr(settings, 'ATR_EXHAUSTION_MULTIPLIER', 2.0)
    
    if len(avg_candle_range) >= 2 and current_range > multiplier * avg_candle_range.iloc[-2]:
        return None  # Exhausted move, skip

    # --- Momentum Confirmation Filter ---
    # Reject only if the structure has genuinely broken down
    # Use candles -25 to -5 as the "established" structure reference
    if len(df_mtf) >= 25:
        if direction == "LONG":
            reference_low = df_mtf['low'].iloc[-25:-5].min()
            last_5_lows = df_mtf['low'].iloc[-5:]
            if (last_5_lows < reference_low * 0.998).any():
                return None  # Recent candles broke established structure
        elif direction == "SHORT":
            reference_high = df_mtf['high'].iloc[-25:-5].max()
            last_5_highs = df_mtf['high'].iloc[-5:]
            if (last_5_highs > reference_high * 1.002).any():
                return None  # Recent candles broke established structure

    confluences.append(f"HTF Bias: {bias['structure']} in {bias['zone']}")
    
    from risk.manager import get_pip_value
    pip_value = get_pip_value(symbol)
    
    # Score FVGs — use wider proximity (20 pips) for scoring, tight (5 pips) for entry
    relevant_fvgs = [f for f in fvgs if f.type == ("BULLISH" if direction == "LONG" else "BEARISH")]
    near_fvgs = []
    for fvg in relevant_fvgs:
        if direction == "LONG":
            dist = (current_price - fvg.midpoint) / pip_value
            if 0 < dist <= 20:
                near_fvgs.append(fvg)
        else:
            dist = (fvg.midpoint - current_price) / pip_value
            if 0 < dist <= 20:
                near_fvgs.append(fvg)
    
    if near_fvgs:
        score += 1
        confluences.append(f"FVG present ({len(near_fvgs)})")
        # Use midpoint (Consequent Encroachment) — much higher fill probability
        entry_price = near_fvgs[0].midpoint
        primary_zone = "FVG"

    # Score OBs — 15 pip window
    relevant_obs = [o for o in obs if o.type == ("BULLISH" if direction == "LONG" else "BEARISH")]
    near_obs = []
    for ob in relevant_obs:
        if direction == "LONG":
            dist = (current_price - ob.top) / pip_value
            if 0 < dist <= 15:
                near_obs.append(ob)
        else:
            dist = (ob.bottom - current_price) / pip_value
            if 0 < dist <= 15:
                near_obs.append(ob)
    
    if near_obs:
        score += 1
        confluences.append(f"Order Block present ({len(near_obs)})")
        if primary_zone == "NONE":
            entry_price = near_obs[0].top if direction == "LONG" else near_obs[0].bottom
            primary_zone = "OB"

    # Score Breakers — 15 pip window
    relevant_breakers = [b for b in breakers if b.type == ("BULLISH" if direction == "LONG" else "BEARISH")]
    near_breakers = []
    for bb in relevant_breakers:
        if direction == "LONG":
            dist = (current_price - bb.top) / pip_value
            if 0 < dist <= 15:
                near_breakers.append(bb)
        else:
            dist = (bb.bottom - current_price) / pip_value
            if 0 < dist <= 15:
                near_breakers.append(bb)
    
    if near_breakers:
        score += 1
        confluences.append(f"Breaker Block present ({len(near_breakers)})")
        if primary_zone == "NONE":
            entry_price = near_breakers[0].top if direction == "LONG" else near_breakers[0].bottom
            primary_zone = "BREAKER"

    # Score Zones — 20 pip window
    relevant_zones = [z for z in zones if z.type == ("DEMAND" if direction == "LONG" else "SUPPLY")]
    near_zones = []
    for zone in relevant_zones:
        if direction == "LONG":
            dist = (current_price - zone.proximal_line) / pip_value
            if 0 < dist <= 20:
                near_zones.append(zone)
        else:
            dist = (zone.proximal_line - current_price) / pip_value
            if 0 < dist <= 20:
                near_zones.append(zone)
    
    if near_zones:
        near_zones.sort(key=lambda x: (not x.is_fresh, abs(current_price - x.proximal_line)))
        zone = near_zones[0]
        score += 2 if zone.is_fresh else 1
        confluences.append(f"{'Fresh' if zone.is_fresh else 'Tested'} {zone.type} Zone")
        if primary_zone == "NONE":
            entry_price = zone.proximal_line
            primary_zone = "ZONE"

    min_required = settings.MIN_CONFLUENCES_BY_SYMBOL.get(symbol, settings.MIN_CONFLUENCES)
    max_allowed = settings.MAX_CONFLUENCES_BY_SYMBOL.get(symbol, 99)
    
    if score < min_required:
        return None
        
    if score > max_allowed:
        # Too many confluences often mean the move is already over (exhausted)
        return None
        
    sl, tp = calculate_structural_sl(df_mtf, direction, entry_price, symbol)
    
    if sl is None:
        return None
        
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
