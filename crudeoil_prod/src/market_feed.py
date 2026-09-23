"""Daily market prices from Yahoo Finance (no API key needed).

This is the main data source. The two oil futures are what we forecast;
the other tickers are extra signals the models can learn from.
"""

import pandas as pd
import yfinance as yf

from .utils import log

# Yahoo ticker -> short column name
TICKERS = {
    "CL=F": "wti",       # WTI crude oil futures (US benchmark), USD/barrel
    "BZ=F": "brent",     # Brent crude oil futures (global benchmark), USD/barrel
    "NG=F": "natgas",    # Natural gas futures
    "DX-Y.NYB": "dollar",  # US dollar index: a stronger dollar often weighs on oil
    "^GSPC": "sp500",    # S&P 500: a rough gauge of economic mood
    "^VIX": "vix",       # Stock market "fear index"
    "^TNX": "us10y",     # 10-year US Treasury yield
}


def get_market_data(years: int = 5) -> pd.DataFrame:
    """Download daily closing prices, one column per ticker, indexed by date."""
    raw = yf.download(
        list(TICKERS),
        period=f"{years}y",
        interval="1d",
        auto_adjust=False,
        progress=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError("Yahoo Finance returned no data. Check your internet connection and try again.")

    closes = raw["Close"].rename(columns=TICKERS)
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes.sort_index()

    # Keep only days when the oil markets traded, then fill small gaps in the
    # other series (for example, US holidays when stocks were closed).
    closes = closes.dropna(subset=["wti", "brent"])
    closes = closes.ffill()

    # Futures prices can briefly go negative or to zero (WTI did in April 2020).
    # Our models work with percentage changes, which need positive prices.
    closes = closes[(closes["wti"] > 0) & (closes["brent"] > 0)]

    log("MARKET", f"{len(closes):,} trading days, {closes.index[0].date()} -> {closes.index[-1].date()}")
    return closes
