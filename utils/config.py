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
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Initialize a global settings instance
settings = Settings()
