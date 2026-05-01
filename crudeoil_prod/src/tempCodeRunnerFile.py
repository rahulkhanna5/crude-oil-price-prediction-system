 params = {
    "api_key": EIA_API_KEY,
    "frequency": "daily",
    "data[0]": "value",
    "facets[series][]": "PET.RWTC.D",
    "start": start.replace("-", ""),
    "end": end.replace("-", ""),
    "sort[0][column]": "period",
    "sort[0][direction]": "desc"