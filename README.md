# Statistical Arbitrage Bot

A modular, institutional-grade Python trading bot that uses Cointegration-based Mean Reversion to trade the BTC/ETH spread. 

## Features
- **Cointegration Checks**: Augmented Dickey-Fuller (ADF) tests via `statsmodels`.
- **Z-Score Logic**: Buy and short the spread dynamically using rolling metrics.
- **Risk Management**: "Paper Trading" mode, dynamic sizing based on simulated equity, and API failure killswitches.
- **Modern Infrastructure**: Async-ready with Python 3.12, strict dependencies via `uv`, logs via `loguru` and notifications via `python-telegram-bot`.
