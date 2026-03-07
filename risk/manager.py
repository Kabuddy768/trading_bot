from utils.config import settings
from utils.logger import logger

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
