"""
Quick smoke test / connectivity check.
Run with: python -m uv run python test_connection.py
This does NOT require valid API keys for the read-only parts.
"""
import sys

print("=== Trading Bot Smoke Test ===\n")

# 1. Check Python version
print(f"[1] Python version: {sys.version}")
assert sys.version_info >= (3, 12), "Python 3.12+ is required!"
print("    ✓ Python version OK\n")

# 2. Check all imports
print("[2] Checking imports...")
try:
    import ccxt
    import pandas
    import statsmodels
    import loguru
    import pydantic_settings
    import requests
    print("    ✓ All imports OK\n")
except ImportError as e:
    print(f"    ✗ Import failed: {e}")
    sys.exit(1)

# 3. Test public Binance connection (no API keys needed)
print("[3] Testing Binance public API...")
try:
    exchange = ccxt.binance({'enableRateLimit': True})
    ticker = exchange.fetch_ticker("BTC/USDT")
    print(f"    ✓ Binance connected! BTC/USDT price: ${ticker['last']:,.2f}\n")
except Exception as e:
    print(f"    ✗ Binance connection failed: {e}\n")

# 4. Test data fetching
print("[4] Testing historical data fetch (last 10 candles)...")
try:
    ohlcv = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=10)
    print(f"    ✓ Fetched {len(ohlcv)} candles OK\n")
    ohlcv_eth = exchange.fetch_ohlcv("ETH/USDT", "1h", limit=10)
    print(f"    ✓ Fetched {len(ohlcv_eth)} ETH/USDT candles OK\n")
except Exception as e:
    print(f"    ✗ Data fetch failed: {e}\n")

# 5. Test strategy math
print("[5] Testing OLS + ADF + Z-Score calculations...")
try:
    import pandas as pd
    import statsmodels.api as sm
    from statsmodels.tsa.stattools import adfuller
    import traceback
    
    # Use the fetched data, convert explicitly to float Series
    btc_close = pd.Series([float(c[4]) for c in ohlcv], dtype='float64')
    eth_close = pd.Series([float(c[4]) for c in ohlcv_eth], dtype='float64')

    x = sm.add_constant(eth_close)
    model = sm.OLS(btc_close, x).fit()
    spread = btc_close - model.predict(x)

    rolling_mean = spread.rolling(window=5).mean()
    rolling_std = spread.rolling(window=5).std()
    z_score = (spread - rolling_mean) / rolling_std

    print(f"    ✓ OLS fitted. Beta: {model.params.iloc[1]:.4f}")
    print(f"    ✓ Spread calculated. Latest: {spread.iloc[-1]:.4f}")
    print(f"    ✓ Latest Z-Score: {z_score.iloc[-1]:.4f}\n")
except Exception as e:
    print(f"    ✗ Strategy math failed: {e}\n")
    traceback.print_exc()

print("=== Smoke Test Complete ===")
print("If all checks passed, you're ready to run: python -m uv run python main.py")
