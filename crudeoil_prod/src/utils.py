"""Small shared helpers: file paths, API keys, and logging."""

import os
from pathlib import Path

from dotenv import load_dotenv

# crudeoil_prod/ (the folder that contains app.py)
PROD_DIR = Path(__file__).resolve().parents[1]
# Repository root (one level above crudeoil_prod/)
REPO_ROOT = PROD_DIR.parent

# The website reads this file. The pipeline writes it.
FORECAST_JSON = REPO_ROOT / "web" / "data" / "forecast.json"

# Load API keys from crudeoil_prod/.env if it exists. In GitHub Actions the
# keys come from repository secrets instead, so a missing .env is fine.
load_dotenv(PROD_DIR / ".env")


def get_key(name: str) -> str | None:
    """Return an API key from the environment, or None if it isn't set."""
    value = os.getenv(name, "").strip()
    if not value or value.startswith("YOUR_"):
        return None
    return value


def log(source: str, message: str) -> None:
    print(f"[{source}] {message}", flush=True)
