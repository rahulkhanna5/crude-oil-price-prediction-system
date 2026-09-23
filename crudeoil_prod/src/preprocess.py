"""Turn raw prices into model features and targets.

Key idea: we predict the *percentage change* in price, not the price itself.
Prices drift to levels the models may never have seen, but daily changes
look roughly the same year after year, which makes them easier to learn.
(Technically we use log returns: log(price_later / price_now).)
"""

import numpy as np
import pandas as pd


def attach_optional(market: pd.DataFrame, extra: pd.DataFrame | None) -> pd.DataFrame:
    """Line up a slower data source (weekly/daily macro) with the trading-day index.

    Each trading day gets the most recent value that was already published.
    """
    if extra is None or extra.empty:
        return market
    combined = market.join(extra, how="outer").sort_index()
    combined[extra.columns] = combined[extra.columns].ffill()
    return combined.loc[market.index]


def rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index: 0-100, high values mean recent gains dominate."""
    change = prices.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    return 100 - 100 / (1 + gain / (loss + 1e-9))


def build_features(data: pd.DataFrame, asset: str) -> pd.DataFrame:
    """Create one row of features per trading day for `asset` ("wti" or "brent").

    Every feature uses only information available at that day's close.
    """
    price = data[asset]
    log_ret = np.log(price).diff()
    f = pd.DataFrame(index=data.index)

    # Recent momentum: how much did the price move over the last N days?
    for n in (1, 2, 5, 10, 20):
        f[f"ret_{n}d"] = np.log(price / price.shift(n))

    # Volatility: how jumpy has the price been?
    f["vol_10d"] = log_ret.rolling(10).std()
    f["vol_20d"] = log_ret.rolling(20).std()

    # Technical indicators traders watch
    f["rsi_14"] = rsi(price) / 100
    ema12 = price.ewm(span=12, adjust=False).mean()
    ema26 = price.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    f["macd_hist"] = (macd - macd.ewm(span=9, adjust=False).mean()) / price
    f["dist_sma20"] = price / price.rolling(20).mean() - 1
    f["dist_sma50"] = price / price.rolling(50).mean() - 1

    # Spread between the two benchmarks
    f["brent_wti_spread"] = np.log(data["brent"] / data["wti"])
    f["spread_chg_5d"] = f["brent_wti_spread"].diff(5)

    # Other markets: yesterday-to-today moves
    for col in ("natgas", "dollar", "sp500"):
        if col in data:
            f[f"{col}_ret_1d"] = np.log(data[col]).diff()
            f[f"{col}_ret_5d"] = np.log(data[col]).diff(5)
    if "vix" in data:
        f["vix"] = data["vix"] / 100
    if "us10y" in data:
        f["us10y_chg_5d"] = data["us10y"].diff(5)

    # Optional sources (only present when API keys are configured)
    if "crude_inventory" in data:
        f["inventory_chg_4w"] = np.log(data["crude_inventory"]).diff(20)
    for col in ("inflation_expectation", "yield_curve"):
        if col in data:
            f[col] = data[col]

    # Calendar
    f["day_of_week"] = data.index.dayofweek
    f["month"] = data.index.month

    return f.replace([np.inf, -np.inf], np.nan)


def build_target(price: pd.Series, horizon: int) -> pd.Series:
    """Log return from today's close to the close `horizon` trading days later."""
    return np.log(price.shift(-horizon) / price)
