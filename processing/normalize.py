import pandas as pd

COLUMN_MAP = {
    "PM2.5": "pm2_5",
    "PM10": "pm10",
    "NO2": "no2",
    "SO2": "so2",
    "O3": "o3",
    "CO": "co",
    "CO2": "co2",
    "Temperature": "temperature",
    "Humidity": "humidity",
    "AQI": "device_aqi",
}

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in out.columns})
    return out
