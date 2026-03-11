import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from utils.config import settings
from risk.manager import get_pip_value

@dataclass
class OrderBlock:
    type: str           # "BULLISH" or "BEARISH"
    top: float          # High of the OB candle
    bottom: float       # Low of the OB candle
    formed_at: datetime
    is_mitigated: bool  # True if price has traded back into the OB
    strength: float     # Size of the impulse move that created it (in pips)

@dataclass
class BreakerBlock:
    type: str           # "BULLISH" or "BEARISH" (direction it NOW acts as)
    top: float
    bottom: float
    formed_at: datetime
    original_ob_type: str  # What it was before being broken

def detect_order_blocks(df: pd.DataFrame, symbol: str, lookback: int = settings.OB_LOOKBACK) -> list[OrderBlock]:
    """
    Scans for valid Order Blocks by:
    ...
    Returns only UN-mitigated OBs.
    """
    obs_dict = {}
    pip_value = get_pip_value(symbol)
    
    # We need some history to find impulse moves
    for i in range(lookback, len(df) - 1):
        current_candle = df.iloc[i]
        next_candle = df.iloc[i+1]
        
        # Bullish OB check: Strong bullish move breaking structure
        # A simple proxy for "breaking structure" is a candle with a large body
        body_size = abs(next_candle['close'] - next_candle['open'])
        body_size_pips = body_size / pip_value
        
        if next_candle['close'] > next_candle['open'] and body_size_pips > 5.0:
            # Look back for the last bearish candle
            for j in range(i, i - lookback, -1):
                prev_candle = df.iloc[j]
                if prev_candle['close'] < prev_candle['open']:
                    ob_time = prev_candle.name if hasattr(prev_candle, 'name') else None
                    if ob_time in obs_dict:
                        break # Already tracked this OB
                        
                    ob = OrderBlock(
                        type="BULLISH",
                        top=prev_candle['high'],
                        bottom=prev_candle['low'],
                        formed_at=ob_time,
                        is_mitigated=False,
                        strength=body_size_pips
                    )
                    
                    # Check if mitigated since formation
                    is_mitigated = False
                    for k in range(j+1, len(df)):
                        if df.iloc[k]['low'] <= ob.bottom:
                            is_mitigated = True
                            break
                    
                    if not is_mitigated:
                        obs_dict[ob_time] = ob
                    break # Found the last opposing candle
                    
        # Bearish OB check
        elif next_candle['close'] < next_candle['open'] and body_size_pips > 5.0:
            # Look back for the last bullish candle
            for j in range(i, i - lookback, -1):
                prev_candle = df.iloc[j]
                if prev_candle['close'] > prev_candle['open']:
                    ob_time = prev_candle.name if hasattr(prev_candle, 'name') else None
                    if ob_time in obs_dict:
                        break

                    ob = OrderBlock(
                        type="BEARISH",
                        top=prev_candle['high'],
                        bottom=prev_candle['low'],
                        formed_at=ob_time,
                        is_mitigated=False,
                        strength=body_size_pips
                    )
                    
                    # Check if mitigated since formation
                    is_mitigated = False
                    for k in range(j+1, len(df)):
                        if df.iloc[k]['high'] >= ob.top:
                            is_mitigated = True
                            break
                    
                    if not is_mitigated:
                        obs_dict[ob_time] = ob
                    break
                    
    return list(obs_dict.values())

def detect_breaker_blocks(df: pd.DataFrame, symbol: str) -> list[BreakerBlock]:
    """
    Finds Order Blocks that have been mitigated (price traded through them).
    ...
    Returns list of active Breaker Blocks.
    """
    # For breakers, we look for OBs that WERE mitigated by a strong move
    # A breaker is an OB that price closed BEYOND.
    breakers = []
    
    # 1. Fetch RAW (unfiltered by mitigation) OBs by hijacking detect_order_blocks logic temporarily
    # But for efficiency, we really only care about standard OB properties.
    # To avoid writing an entirely new scanner, we will find ALL blocks and track mitigation status.
    all_potential_obs = []
    pip_value = get_pip_value(symbol)
    lookback = settings.OB_LOOKBACK
    
    # Fast re-scan, capturing the index for easy forward tracing
    for i in range(lookback, len(df) - 1):
        next_candle = df.iloc[i+1]
        body_size_pips = abs(next_candle['close'] - next_candle['open']) / pip_value
        if body_size_pips > 5.0:
            for j in range(i, i - lookback, -1):
                prev_candle = df.iloc[j]
                if (next_candle['close'] > next_candle['open'] and prev_candle['close'] < prev_candle['open']) or \
                   (next_candle['close'] < next_candle['open'] and prev_candle['close'] > prev_candle['open']):
                    all_potential_obs.append({
                        "type": "BULLISH" if next_candle['close'] > next_candle['open'] else "BEARISH",
                        "top": prev_candle['high'],
                        "bottom": prev_candle['low'],
                        "formed_at": prev_candle.name if hasattr(prev_candle, 'name') else None,
                        "idx": j
                    })
                    break
                    
    for ob in all_potential_obs:
        # Check if price later closed BEYOND the OB (breaking it)
        broken = False
        broken_idx = -1
        # Start checking after the impulse candle (ob['idx'] + 2 usually)
        for k in range(ob["idx"] + 1, len(df)):
            if ob["type"] == "BULLISH": # Original OB was bullish, so we look for price breaking BELOW it
                if df.iloc[k]['close'] < ob["bottom"]:
                    broken = True
                    broken_idx = k
                    break
            else: # Original OB was bearish, looking for break ABOVE
                if df.iloc[k]['close'] > ob["top"]:
                    broken = True
                    broken_idx = k
                    break
                    
        if broken:
            # Now it acts as the OPPOSITE type
            breaker = BreakerBlock(
                type="BEARISH" if ob["type"] == "BULLISH" else "BULLISH",
                top=ob["top"],
                bottom=ob["bottom"],
                formed_at=ob["formed_at"],
                original_ob_type=ob["type"]
            )
            # Check if breaker itself is still "active" (price hasn't re-broken it)
            active = True
            for l in range(broken_idx + 1, len(df)):
                if breaker.type == "BEARISH":
                    if df.iloc[l]['close'] > breaker.top: # Price broke back above bearish breaker
                        active = False
                        break
                else:
                    if df.iloc[l]['close'] < breaker.bottom: # Price broke back below bullish breaker
                        active = False
                        break
            if active:
                breakers.append(breaker)
                
    return breakers

def get_active_ob_near_price(
    obs: list[OrderBlock],
    breakers: list[BreakerBlock],
    symbol: str,
    current_price: float,
    direction: str,
    proximity_pips: float = 10.0
) -> list[OrderBlock | BreakerBlock]:
    """
    Returns all OBs and Breakers within proximity_pips of current price
    that are aligned with the trade direction.
    """
    candidates = []
    pip_value = get_pip_value(symbol)
    
    for ob in obs:
        if direction == "LONG" and ob.type == "BULLISH":
            if current_price > ob.top:
                dist = (current_price - ob.top) / pip_value
                if dist <= proximity_pips:
                    candidates.append(ob)
        elif direction == "SHORT" and ob.type == "BEARISH":
            if current_price < ob.bottom:
                dist = (ob.bottom - current_price) / pip_value
                if dist <= proximity_pips:
                    candidates.append(ob)
                    
    for bb in breakers:
        if direction == "LONG" and bb.type == "BULLISH":
            if current_price > bb.top:
                dist = (current_price - bb.top) / pip_value
                if dist <= proximity_pips:
                    candidates.append(bb)
        elif direction == "SHORT" and bb.type == "BEARISH":
            if current_price < bb.bottom:
                dist = (bb.bottom - current_price) / pip_value
                if dist <= proximity_pips:
                    candidates.append(bb)
                    
    return candidates
