import requests
from utils.config import settings
from utils.logger import logger

def send_telegram_message(message: str) -> bool:
    """Sends a message via Telegram bot."""
    if not settings.TELEGRAM_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not populated. Skipping message.")
        return False
        
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": message[:4000],  # Max size
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False
