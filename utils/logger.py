import sys
from loguru import logger
from utils.config import settings

def setup_logger():
    # Remove default handlers
    logger.remove()
    
    # Add console handler (stdout)
    logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    
    # Add file handler with rotation
    logger.add("bot.log", rotation="10 MB", retention="5 days", level="INFO")
    
    logger.info("Logger initialized successfully.")

setup_logger()
