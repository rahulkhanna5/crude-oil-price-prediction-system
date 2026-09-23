"""Optional: weekly US crude oil inventories from the EIA (US Energy Information Administration).

Get a free key at https://www.eia.gov/opendata/register.php and put it in
crudeoil_prod/.env as EIA_API_KEY=... . Without a key this feed is skipped.
"""

import pandas as pd
import requests

from .utils import get_key, log

EIA_URL = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
# Weekly US ending stocks of crude oil excluding the Strategic Petroleum Reserve
INVENTORY_SERIES = "WCESTUS1"


def get_eia_inventories(start: str) -> pd.DataFrame | None:
    """Return a DataFrame with a `crude_inventory` column, or None if unavailable."""
    api_key = get_key("EIA_API_KEY")
    if api_key is None:
        log("EIA", "No EIA_API_KEY set, skipping inventories.")
        return None

    params = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": INVENTORY_SERIES,
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    try:
        response = requests.get(EIA_URL, params=params, timeout=30)
        response.raise_for_status()
        records = response.json()["response"]["data"]
    except Exception as exc:  # network problems or a bad key shouldn't stop the forecast
        log("EIA", f"Request failed, skipping inventories: {exc}")
        return None

    if not records:
        log("EIA", "No inventory data returned.")
        return None

    df = pd.DataFrame(records)[["period", "value"]]
    df["period"] = pd.to_datetime(df["period"])
    df["crude_inventory"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.set_index("period")[["crude_inventory"]].dropna().sort_index()
    # EIA publishes each week's number the following Wednesday. Shift the dates
    # forward so the model never "sees" a number before it was public.
    df.index = df.index + pd.Timedelta(days=5)
    log("EIA", f"{len(df):,} weekly inventory reports")
    return df
