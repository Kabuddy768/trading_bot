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

    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Initialize a global settings instance
settings = Settings()
