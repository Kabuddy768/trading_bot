import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from utils.logger import logger

def calculate_spread(series_y: pd.Series, series_x: pd.Series) -> pd.Series:
    """
    Performs an OLS Regression: Y = beta * X + epsilon
    Returns the spread (epsilon).
    Here, Y is typically BTC and X is ETH (as per spec, Price_BTC = beta * Price_ETH + epsilon)
    """
    try:
        x_with_const = sm.add_constant(series_x)
        model = sm.OLS(series_y, x_with_const).fit()
        spread = series_y - model.predict(x_with_const)
        return spread
    except Exception as e:
        logger.error(f"Error calculating spread: {e}")
        return pd.Series(dtype=float)

def check_cointegration(spread: pd.Series, significance_level: float = 0.05) -> bool:
    """
    Runs ADF Test on the spread.
    If p-value > significance_level, the pair is not cointegrated.
    """
    if spread.empty:
        return False
        
    try:
        adf_result = adfuller(spread)
        p_value = adf_result[1]
        
        logger.info(f"ADF Test p-value: {p_value:.4f}")
        
        if p_value > significance_level:
            logger.warning(f"Pair is NOT cointegrated (p-value {p_value:.4f} > {significance_level}).")
            return False
            
        logger.info("Pair IS cointegrated.")
        return True
    except Exception as e:
        logger.error(f"Error running ADF test: {e}")
        return False

def calculate_zscore(spread: pd.Series, window: int = 20) -> pd.Series:
    """
    Calculates the Rolling Z-Score of the spread.
    Z-Score = (Spread - Rolling Mean) / Rolling StdDev
    """
    if spread.empty:
        return pd.Series(dtype=float)
        
    rolling_mean = spread.rolling(window=window).mean()
    rolling_std = spread.rolling(window=window).std()
    z_score = (spread - rolling_mean) / rolling_std
    return z_score

def generate_signals(current_zscore: float, entry_threshold: float = 2.0) -> str:
    """
    Generates trading signals based on Z-Score.
    Z-Score > 2.0 -> SELL SPREAD (Sell BTC, Buy ETH)
    Z-Score < -2.0 -> BUY SPREAD (Buy BTC, Sell ETH)
    Z-Score ~ 0.0 -> EXIT
    """
    if current_zscore > entry_threshold:
        return "SELL_SPREAD"
    elif current_zscore < -entry_threshold:
        return "BUY_SPREAD"
    # To handle exits, typically a threshold around 0, e.g., cross 0. 
    # For now returning NO_ACTION if we aren't at extreme points. 
    # Exit logic will be managed by execution state tracking in Phase 3.
    elif abs(current_zscore) < 0.1:
        return "EXIT_SPREAD"
        
    return "NO_ACTION"
