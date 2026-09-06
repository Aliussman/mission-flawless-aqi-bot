import pandas as pd

PPM_TO_PPB = 1_000.0
PPB_TO_PPM = 1e-3

CANONICAL_UNITS = {
    "device_aqi": "index",
    "aqi_us": "index",
    "aqi_raw": "index",
    "pm2_5": "ug_m3",
    "pm10": "ug_m3",
    "pm1": "ug_m3",
    "no2": "ppb",
    "so2": "ppb",
    "o3": "ppb",
    "nh3": "ppb",
    "h2s": "ppb",
    "co": "ppm",
    "co2": "ppm",
    "tvoc": "ppm",
    "temperature": "deg_c",
    "humidity": "pct",
    "noise": "db",
    "methane": "pct",
}

SOURCE_CONVERSIONS = {
    # aqi.in exports gaseous pollutants in ppm
    "aqi_in": {
        "no2": PPM_TO_PPB,
        "so2": PPM_TO_PPB,
        "o3": PPM_TO_PPB,
        "nh3": PPM_TO_PPB,
        "h2s": PPM_TO_PPB,
    },
    # aurassure exports CO in ppb (everything else already in canonical units)
    "aurassure": {
        "co": PPB_TO_PPM,
    },
}

def standardize_units(df, source):
    out = df.copy()
    conversions = SOURCE_CONVERSIONS.get(source, {})
    for col, factor in conversions.items():
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce") * factor
    return out

def unit_label(column):
    if column.startswith("device_aqi_"):
        return CANONICAL_UNITS.get("device_aqi", "")
    return CANONICAL_UNITS.get(column, "")