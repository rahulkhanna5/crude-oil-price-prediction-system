"""Optional: macro indicators from FRED (Federal Reserve Bank of St. Louis).

Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html and put it
in crudeoil_prod/.env as FRED_API_KEY=... . Without a key this feed is skipped.
"""

import pandas as pd
import requests

from .utils import get_key, log

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED series id -> column name
FRED_SERIES = {
    "T10YIE": "inflation_expectation",  # 10-year breakeven inflation rate
    "T10Y2Y": "yield_curve",            # 10-year minus 2-year Treasury spread
}


def get_fred_data(start: str) -> pd.DataFrame | None:
    api_key = get_key("FRED_API_KEY")
    if api_key is None:
        log("FRED", "No FRED_API_KEY set, skipping macro data.")
        return None

    columns = []
    for series_id, name in FRED_SERIES.items():
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start,
        }
        try:
            response = requests.get(FRED_URL, params=params, timeout=30)
            response.raise_for_status()
            observations = response.json()["observations"]
        except Exception as exc:
            log("FRED", f"{series_id} failed, skipping it: {exc}")
            continue

        series = pd.Series(
            pd.to_numeric([o["value"] for o in observations], errors="coerce"),  # "." means missing
            index=pd.to_datetime([o["date"] for o in observations]),
            name=name,
        ).dropna()
        # Daily FRED values are published the next business day.
        series.index = series.index + pd.Timedelta(days=1)
        columns.append(series)
        log("FRED", f"{series_id}: {len(series):,} observations")

    return pd.concat(columns, axis=1).sort_index() if columns else None
