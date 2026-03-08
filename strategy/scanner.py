"""
strategy/scanner.py

Scans a watchlist of pairs each cycle and returns the best cointegrated
pair available. This lets the bot automatically find opportunities rather
than being hardcoded to BTC/ETH.
"""

import pandas as pd
from dataclasses import dataclass
from typing import Optional
from statsmodels.tsa.stattools import adfuller
import statsmodels.api as sm

from utils.logger import logger


# ---------------------------------------------------------------------------
# Watchlist — add/remove pairs freely. Bot will scan all of these each cycle.
# ---------------------------------------------------------------------------
WATCHLIST: list[tuple[str, str]] = [
    ("BTC/USDT", "ETH/USDT"),
    ("BTC/USDT", "BNB/USDT"),
    ("BTC/USDT", "SOL/USDT"),
    ("ETH/USDT", "BNB/USDT"),
    ("ETH/USDT", "SOL/USDT"),
    ("BNB/USDT", "SOL/USDT"),
]


@dataclass
class ScanResult:
    """Holds the result of a successful cointegration scan."""
    symbol_y: str
    symbol_x: str
    p_value: float
    spread: pd.Series
    beta: float  # OLS hedge ratio


def _calculate_spread_and_beta(series_y: pd.Series, series_x: pd.Series) -> tuple[pd.Series, float]:
    """OLS regression: Y = beta * X + epsilon. Returns (spread, beta)."""
    x_with_const = sm.add_constant(series_x)
    model = sm.OLS(series_y, x_with_const).fit()
    spread = series_y - model.predict(x_with_const)
    beta = float(model.params.iloc[1])
    return spread, beta


def scan_for_best_pair(
    data: dict[str, pd.DataFrame],
    significance_level: float = 0.05,
) -> Optional[ScanResult]:
    """
    Iterates over WATCHLIST pairs using pre-fetched data.
    Returns the ScanResult with the lowest ADF p-value (strongest cointegration),
    or None if no pair passes the significance threshold.

    Args:
        data: dict mapping symbol -> DataFrame (must have 'close' column)
        significance_level: ADF p-value threshold (default 0.05)
    """
    best: Optional[ScanResult] = None

    for symbol_y, symbol_x in WATCHLIST:
        # Skip if we don't have data for either symbol
        if symbol_y not in data or symbol_x not in data:
            logger.debug(f"Skipping {symbol_y}/{symbol_x} — data not available.")
            continue

        df_y = data[symbol_y]
        df_x = data[symbol_x]

        if df_y.empty or df_x.empty:
            continue

        try:
            # Align on shared timestamps
            combined = pd.DataFrame({
                "y": df_y["close"],
                "x": df_x["close"],
            }).dropna()

            if len(combined) < 30:
                logger.warning(f"Not enough data for {symbol_y}/{symbol_x} after alignment.")
                continue

            spread, beta = _calculate_spread_and_beta(combined["y"], combined["x"])
            adf_result = adfuller(spread)
            p_value = float(adf_result[1])

            logger.info(f"  [{symbol_y} / {symbol_x}] ADF p-value: {p_value:.4f} | beta: {beta:.4f}")

            if p_value < significance_level:
                if best is None or p_value < best.p_value:
                    best = ScanResult(
                        symbol_y=symbol_y,
                        symbol_x=symbol_x,
                        p_value=p_value,
                        spread=spread,
                        beta=beta,
                    )

        except Exception as e:
            logger.error(f"Error scanning {symbol_y}/{symbol_x}: {e}")
            continue

    if best:
        logger.info(f"✅ Best pair: {best.symbol_y} / {best.symbol_x} (p={best.p_value:.4f})")
    else:
        logger.warning("❌ No cointegrated pairs found in watchlist this cycle.")

    return best


def get_all_symbols() -> list[str]:
    """Returns a flat deduplicated list of all symbols in the watchlist."""
    symbols = set()
    for y, x in WATCHLIST:
        symbols.add(y)
        symbols.add(x)
    return list(symbols)