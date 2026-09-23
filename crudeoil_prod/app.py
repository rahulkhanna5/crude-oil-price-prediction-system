"""Run the whole pipeline: download data -> train -> forecast -> write JSON for the website.

Usage (from the repository root):
    python crudeoil_prod/app.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Let `python crudeoil_prod/app.py` work from any folder
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.eia_feed import get_eia_inventories  # noqa: E402
from src.fred_feed import get_fred_data  # noqa: E402
from src.market_feed import get_market_data  # noqa: E402
from src.predict import forecast_asset  # noqa: E402
from src.preprocess import attach_optional  # noqa: E402
from src.utils import FORECAST_JSON, log  # noqa: E402

ASSETS = {
    "wti": {"name": "WTI Crude", "ticker": "CL=F", "description": "US benchmark, Cushing, Oklahoma"},
    "brent": {"name": "Brent Crude", "ticker": "BZ=F", "description": "Global benchmark, North Sea"},
}


def main() -> None:
    # 1) Data
    data = get_market_data(years=5)
    start = data.index[0].strftime("%Y-%m-%d")
    sources = ["Yahoo Finance"]
    for name, extra in (("EIA", get_eia_inventories(start)), ("FRED", get_fred_data(start))):
        if extra is not None:
            data = attach_optional(data, extra)
            sources.append(name)

    # 2) Models + forecasts
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": sources,
        "assets": {},
    }
    for key, info in ASSETS.items():
        output["assets"][key] = {**info, **forecast_asset(data, key)}

    # 3) Save for the website
    FORECAST_JSON.parent.mkdir(parents=True, exist_ok=True)
    FORECAST_JSON.write_text(json.dumps(output, indent=1))
    log("DONE", f"Wrote {FORECAST_JSON.relative_to(FORECAST_JSON.parents[2])}")


if __name__ == "__main__":
    main()
