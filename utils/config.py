from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Exchange
    BINANCE_API_KEY: str
    BINANCE_API_SECRET: str
    
    # Telegram
    TELEGRAM_TOKEN: str
    TELEGRAM_CHAT_ID: str
    
    # Strategy
    LIVE_TRADING: bool = False
    PAPER_TRADING: bool = True
    CANDLE_TIMEFRAME: str = "1h"
    CANDLE_LIMIT: int = 1000
    
    # Risk
    PAPER_EQUITY: float = 10000.0
    MAX_RISK_PER_TRADE: float = 0.02
    PAPER_FEE_RATE: float = 0.001       # 0.1% Taker fee on Binance
    PAPER_SLIPPAGE: float = 0.0005      # 0.05% Slippage penalty
    MAX_DRAWDOWN_PCT: float = 0.05      # Hard stop if position loses 5% of paper equity
    MAX_Z_SCORE_STOP: float = 4.0       # Hard stop if Z-Score diverges infinitely
    MAX_TRADE_HOURS: int = 48           # Hard stop if position is open for 48 hours

    # ICT Strategy Settings
    ICT_SYMBOLS: list = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]
    BIAS_TIMEFRAME: str = "1h"       # HTF for market structure bias
    SETUP_TIMEFRAME: str = "15m"     # MTF for setup detection
    ENTRY_TIMEFRAME: str = "5m"      # LTF for entry refinement
    BIAS_CANDLE_LIMIT: int = 200     # Candles for HTF bias
    SETUP_CANDLE_LIMIT: int = 100    # Candles for setup detection

    # ICT Signal Thresholds
    MIN_CONFLUENCES: int = 2         # Minimum confluences required to enter
    FVG_MIN_SIZE_PIPS: float = 2.0   # Minimum FVG size to be valid
    OB_LOOKBACK: int = 10            # Candles to look back for Order Blocks
    ZONE_STRENGTH_THRESHOLD: int = 2 # Minimum touches to validate S/D zone

    # Pip-based Risk (Crypto: 1 pip = $1 USDT for BTC pairs)
    PIP_VALUE_USDT: float = 1.0      # 1 pip = $1 USDT (adjust per pair)
    SL_PIPS: int = 5                 # Stop Loss in pips
    TP_PIPS: int = 20                # Take Profit in pips

    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Initialize a global settings instance
settings = Settings()
