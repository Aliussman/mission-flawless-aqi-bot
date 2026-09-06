import pandas as pd

from processing.units import standardize_units

def parse_aqi_in_csv(file_path):
    df = pd.read_csv(file_path)

    # First two columns are junk device IDs ("85", "86"); drop them
    df = df.loc[:, ~df.columns.astype(str).str.isdigit()]

    df = df.rename(columns={
        "date": "timestamp",
        "aqi": "aqi_raw",
        "aqi-us": "aqi_us",
        "pm2.5": "pm2_5",
        "pm1": "pm1",
    })

    for col in df.columns:
        if col != "timestamp":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # The dashboard headline AQI is the US AQI value
    df["device_aqi"] = df["aqi_us"]

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    return standardize_units(df, "aqi_in")