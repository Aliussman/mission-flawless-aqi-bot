import pandas as pd

NUMERIC_COLUMNS = [
    "device_aqi", "pm2_5", "pm10", "no2", "so2", "o3",
    "co", "co2", "temperature", "humidity"
]

def aggregate_hourly(df: pd.DataFrame, timestamp_column="timestamp"):
    out = df.copy()
    out[timestamp_column] = pd.to_datetime(out[timestamp_column], errors="coerce")
    out = out.dropna(subset=[timestamp_column]).set_index(timestamp_column)

    available = [c for c in NUMERIC_COLUMNS if c in out.columns]
    hourly = out[available].resample("1h").mean()
    return hourly.reset_index()
