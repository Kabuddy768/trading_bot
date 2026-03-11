import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategy.bias import get_bias
from strategy.fvg import detect_fvgs
from strategy.orderblock import detect_order_blocks, detect_breaker_blocks
from strategy.supply_demand import detect_zones
from strategy.confluence import score_setup

def create_mock_data():
    """Creates mock OHLCV data with a bullish trend and an FVG."""
    dates = [datetime.now() - timedelta(hours=i) for i in range(100, 0, -1)]
    
    # Simple bullish trend
    close = [100 + i + np.random.normal(0, 0.5) for i in range(100)]
    open_price = [c - 0.5 for c in close]
    high = [max(o, c) + 0.5 for o, c in zip(open_price, close)]
    low = [min(o, c) - 0.5 for o, c in zip(open_price, close)]
    
    # Inject an FVG
    # candle i-2 high < candle i low
    # i = 80
    high[78] = 175.0
    open_price[79] = 176.0
    close[79] = 180.0
    low[80] = 182.0
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': [1000] * 100
    }, index=dates)
    
    return df

def test_strategy():
    df = create_mock_data()
    symbol = "BTC/USDT"
    
    print(f"Testing Strategy on {symbol}...")
    
    # Bias
    bias = get_bias(symbol, df)
    print(f"Bias: {bias['structure']} in {bias['zone']} zone. Tradeable: {bias['tradeable']}")
    
    # FVG
    fvgs = detect_fvgs(df)
    print(f"Detected {len(fvgs)} FVGs.")
    for f in fvgs:
        print(f"  - {f.type} FVG at {f.midpoint:.2f}")
        
    # OB
    obs = detect_order_blocks(df)
    print(f"Detected {len(obs)} Order Blocks.")
    
    # Breakers
    breakers = detect_breaker_blocks(df)
    print(f"Detected {len(breakers)} Breaker Blocks.")
    
    # Zones
    zones = detect_zones(df)
    print(f"Detected {len(zones)} S/D Zones.")
    
    # Confluence
    current_price = df['close'].iloc[-1]
    setup = score_setup(symbol, current_price, bias, fvgs, obs, breakers, zones)
    
    if setup:
        print(f"SUCCESS: Setup detected with score {setup.confluence_score}")
        print(f"  Direction: {setup.direction}")
        print(f"  Entry: {setup.entry_price:.2f}, SL: {setup.sl_price:.2f}, TP: {setup.tp_price:.2f}")
    else:
        print("No setup detected with current mock data.")

if __name__ == "__main__":
    test_strategy()
