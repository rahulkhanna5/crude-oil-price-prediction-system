import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/rahulkhanna/Desktop/crude-oil-price-prediction-system/crudeoil_prod/.env")

EIA_API_KEY = os.getenv("EIA_API_KEY")
EIA_URL = "https://api.eia.gov/v2/seriesid/PET.RWTC.D?api_key=Bhb35DSi66KnNcDKHxHUncNNs7jm5qox0CiJOeYv&start=2020-01-01&end=2024-12-31&frequency=daily"  # FIX 1: correct endpoint

print("API KEY:", EIA_API_KEY)

def fetch_eia_wti(start: str, end: str) -> dict:
    params = {
        "api_key": EIA_API_KEY,  # FIX 2: variable, not string "EIA_API_KEY"
        "start": start,          # FIX 3: no .replace("-", ""), EIA wants YYYY-MM-DD
        "end": end,
        "frequency": "daily",
    }
    response = requests.get(EIA_URL, params=params, timeout=10)
    print(response.url)
    response.raise_for_status()
    return response.json()

def parse_to_df(raw_json: dict) -> pd.DataFrame:
    data_list = raw_json["response"]["data"]
    df = pd.DataFrame(data_list)[["period", "value"]]
    df.rename(columns={"period": "date", "value": "wti_price"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"])
    df["wti_price"] = pd.to_numeric(df["wti_price"], errors="coerce")
    df.dropna(inplace=True)
    df.sort_values("date", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

def get_live_data(days_back: int = 365) -> pd.DataFrame:
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    raw = fetch_eia_wti(start, end)
    return parse_to_df(raw)

if __name__ == "__main__":
    df = get_live_data(days_back=180)
    print(df.head(10))
    print(f"\nShape: {df.shape}")
    print(f"Latest price: ${df['wti_price'].iloc[-1]} on {df['date'].iloc[-1].date()}")
