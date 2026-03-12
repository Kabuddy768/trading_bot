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

def calculate_structural_sl(df: pd.DataFrame, direction: str, entry: float, symbol: str) -> tuple[float, float]:
    """
    Calculates SL structurally based on recent swings instead of fixed pips.
    TP is projected using Risk/Reward Ratio based on the SL distance.
    """
    from risk.manager import get_pip_value
    pip_value = get_pip_value(symbol)
    
    if direction == "LONG":
        # SL goes below the most recent swing low in the last 10 candles
        recent_low = df['low'].iloc[-10:].min()
        sl = recent_low - (2 * pip_value)  # 2 pip buffer below structure
    else:
        recent_high = df['high'].iloc[-10:].max()
        sl = recent_high + (2 * pip_value)
        
    sl_dist = abs(entry - sl)
    if sl_dist == 0:
        sl_dist = 1.0 * pip_value
        
    rr_ratio = getattr(settings, 'RR_RATIO', 2.0)
    
    if direction == "LONG":
        tp = entry + (sl_dist * rr_ratio)
    else:
        tp = entry - (sl_dist * rr_ratio)
        
    return sl, tp

def score_setup(
    symbol: str,
    df_mtf: pd.DataFrame,
    bias: dict,
    fvgs: list,        # Pass ALL fvgs, not pre-filtered
    obs: list,         # Pass ALL obs
    breakers: list,    # Pass ALL breakers  
    zones: list,       # Pass ALL zones
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
    if score >= min_required:
        sl, tp = calculate_structural_sl(df_mtf, direction, entry_price, symbol)
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
