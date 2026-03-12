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
    1. Finding impulse candles (strong body size)
    2. Looking back for the last opposing candles.
    3. Checking if subsequent price action has mitigated our block.
    Returns only UN-mitigated OBs.
    """
    obs_dict = {}
    pip_value = get_pip_value(symbol)
    
    if len(df) < lookback + 2:
        return []

    # Vectorized acceleration: use numpy arrays
    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    closes = df['close'].values
    times = df.index.values

    for i in range(lookback, len(df) - 1):
        # Body size of the potential impulse candle (i+1)
        body_size_pips = abs(closes[i+1] - opens[i+1]) / pip_value
        
        if body_size_pips > 5.0:
            is_bullish_impulse = closes[i+1] > opens[i+1]
            
            # Look back for the last opposing candle
            for j in range(i, i - lookback, -1):
                is_opposing = (is_bullish_impulse and closes[j] < opens[j]) or \
                              (not is_bullish_impulse and closes[j] > opens[j])
                
                if is_opposing:
                    ob_time = times[j]
                    if ob_time in obs_dict:
                        continue # Already tracked this OB candle as part of another impulse
                    
                    ob_top = highs[j]
                    ob_bottom = lows[j]
                    
                    # Optimized mitigation check
                    if is_bullish_impulse:
                        is_mitigated = (lows[j+1:] <= ob_bottom).any()
                    else:
                        is_mitigated = (highs[j+1:] >= ob_top).any()
                    
                    if not is_mitigated:
                        obs_dict[ob_time] = OrderBlock(
                            type="BULLISH" if is_bullish_impulse else "BEARISH",
                            top=ob_top,
                            bottom=ob_bottom,
                            formed_at=ob_time,
                            is_mitigated=False,
                            strength=body_size_pips
                        )
                    break # Found the last opposing candle, move to next i

    return list(obs_dict.values())

def detect_breaker_blocks(df: pd.DataFrame, symbol: str) -> list[BreakerBlock]:
    """
    Finds Order Blocks that have been mitigated (price closed through them).
    Returns list of active Breaker Blocks.
    """
    breakers = []
    pip_value = get_pip_value(symbol)
    lookback = settings.OB_LOOKBACK
    
    if len(df) < lookback + 2:
        return []

    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    closes = df['close'].values
    times = df.index.values
    
    # 1. Identify all potential OBs (even if mitigated)
    potential_obs = []
    for i in range(lookback, len(df) - 1):
        body_size_pips = abs(closes[i+1] - opens[i+1]) / pip_value
        if body_size_pips > 5.0:
            is_bullish_impulse = closes[i+1] > opens[i+1]
            for j in range(i, i - lookback, -1):
                if (is_bullish_impulse and closes[j] < opens[j]) or \
                   (not is_bullish_impulse and closes[j] > opens[j]):
                    potential_obs.append({
                        "type": "BULLISH" if is_bullish_impulse else "BEARISH",
                        "top": highs[j],
                        "bottom": lows[j],
                        "formed_at": times[j],
                        "idx": j
                    })
                    break
                    
    for ob in potential_obs:
        # 2. Check if price closed BEYOND the OB
        broken = False
        broken_idx = -1
        
        # Original OB was bullish, looking for close BELOW
        if ob["type"] == "BULLISH":
            mask = closes[ob["idx"]+1:] < ob["bottom"]
            if mask.any():
                broken = True
                broken_idx = ob["idx"] + 1 + mask.argmax()
        # Original OB was bearish, looking for close ABOVE
        else:
            mask = closes[ob["idx"]+1:] > ob["top"]
            if mask.any():
                broken = True
                broken_idx = ob["idx"] + 1 + mask.argmax()
                    
        if broken:
            # 3. Acts as opposite type now
            brk_type = "BEARISH" if ob["type"] == "BULLISH" else "BULLISH"
            brk_top = ob["top"]
            brk_bottom = ob["bottom"]
            
            # 4. Check if Breaker itself is still active (hasn't been closed back through)
            is_invalid = False
            if brk_type == "BEARISH":
                # If price closes back ABOVE top
                if (closes[broken_idx+1:] > brk_top).any():
                    is_invalid = True
            else:
                # If price closes back BELOW bottom
                if (closes[broken_idx+1:] < brk_bottom).any():
                    is_invalid = True
            
            if not is_invalid:
                breakers.append(BreakerBlock(
                    type=brk_type,
                    top=brk_top,
                    bottom=brk_bottom,
                    formed_at=ob["formed_at"],
                    original_ob_type=ob["type"]
                ))
                
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
