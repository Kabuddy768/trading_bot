import os
import json
from typing import Dict, Any
from utils.config import settings
from utils.logger import logger
from utils.database import db
class KillSwitch:
    def __init__(self, max_failures: int = 3):
        self.consecutive_failures = 0
        self.max_failures = max_failures
        self.is_triggered = False
        
    def record_success(self):
        """Reset failures cleanly."""
        self.consecutive_failures = 0
        
    def record_failure(self):
        """Increment failures and trigger killswitch if needed."""
        self.consecutive_failures += 1
        logger.warning(f"API Error recorded. Consecutive Failures: {self.consecutive_failures}/{self.max_failures}")
        
        if self.consecutive_failures >= self.max_failures:
            self.trigger()
            
    def trigger(self):
        """Activates the killswitch."""
        self.is_triggered = True
        logger.critical(f"KILLSWITCH ENGAGED: {self.max_failures} consecutive API failures detected. Stopping all bot activity.")
        # We will integrate Telegram alert specifically here in the main loop or via a callback.
        
def calculate_position_size(paper_equity: float, risk_per_trade: float = settings.MAX_RISK_PER_TRADE) -> float:
    """
    Returns the nominal dollar amount to risk for the trade.
    """
    return paper_equity * risk_per_trade

def check_stop_loss(current_position: Dict[str, Any], current_tickers: Dict[str, Any], paper_equity: float) -> str | None:
    """
    Evaluates if the current open position has breached maximum drawdown or time limits.
    Returns a reason string if a stop loss is hit, else None.
    """
    if not current_position:
        return None
        
    # Time-based stop loss
    timestamp_str = current_position.get("opened_at")
    if timestamp_str:
        from datetime import datetime
        opened_at = datetime.fromisoformat(timestamp_str)
        hours_open = (datetime.now() - opened_at).total_seconds() / 3600
        if hours_open >= settings.MAX_TRADE_HOURS:
            return f"time_stop_{settings.MAX_TRADE_HOURS}h"

    # Drawdown stop loss (Simplified MTF estimate without hitting ccxt again)
    sym_y = current_position["symbol_y"]
    sym_x = current_position["symbol_x"]
    
    # Needs live ticker prices
    if sym_y not in current_tickers or sym_x not in current_tickers:
        return None
        
    price_y = current_tickers[sym_y]["last"] or current_tickers[sym_y]["close"]
    price_x = current_tickers[sym_x]["last"] or current_tickers[sym_x]["close"]
    
    entry_y = current_position["y_trade"]
    entry_x = current_position["x_trade"]
    
    if current_position["type"] == "SHORT_SPREAD":
        pnl_y = (entry_y["price"] - price_y) * entry_y["amount_base"]
        pnl_x = (price_x - entry_x["price"]) * entry_x["amount_base"]
    else: # LONG_SPREAD
        pnl_y = (price_y - entry_y["price"]) * entry_y["amount_base"]
        pnl_x = (entry_x["price"] - price_x) * entry_x["amount_base"]
        
    total_unrealized_pnl = pnl_y + pnl_x
    max_allowed_loss = paper_equity * settings.MAX_DRAWDOWN_PCT
    
    if total_unrealized_pnl <= -max_allowed_loss:
        return f"drawdown_stop_{total_unrealized_pnl:.2f}"
        
    return None


def load_state() -> Dict[str, Any]:
    """Loads bot state from database so positions survive restarts."""
    current_position = db.load_state_val("current_position")
    paper_equity = db.load_state_val("paper_equity")
    
    state = {}
    if current_position is not None:
        state["current_position"] = current_position
    if paper_equity is not None:
        state["paper_equity"] = paper_equity
        
    return state

def save_state(current_position: Dict[str, Any] | None, paper_equity: float):
    """Saves bot position and equity state to database."""
    try:
        db.save_state_val("current_position", current_position)
        db.save_state_val("paper_equity", paper_equity)
        logger.debug("State saved to database successfully.")
    except Exception as e:
        logger.error(f"Failed to save state to database: {e}")
