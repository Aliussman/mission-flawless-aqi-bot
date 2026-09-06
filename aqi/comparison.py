import pandas as pd

from aqi.india import calculate_india_aqi
from aqi.paper_aqi_rho import calculate_aqi_rho
from aqi.us import calculate_us_aqi


def compare(device_aqi, india_aqi, us_aqi, paper_aqi):
    return {
        "device_aqi": device_aqi,
        "india_aqi": india_aqi,
        "us_aqi": us_aqi,
        "aqi_rho": paper_aqi,
        "device_vs_india": None if device_aqi is None or india_aqi is None else device_aqi - india_aqi,
        "device_vs_us": None if device_aqi is None or us_aqi is None else device_aqi - us_aqi,
        "device_vs_rho": None if device_aqi is None or paper_aqi is None else device_aqi - paper_aqi,
    }


def build_comparison_frame(combined, device_aqi_columns):
    """Compute US/India/AQI-rho from the shared pollutant columns and compare
    against each device's reported AQI. One row per timestamp."""
    rows = []
    for _, rec in combined.iterrows():
        row = rec.to_dict()
        us = calculate_us_aqi(row)["aqi"]
        india = calculate_india_aqi(row)["aqi"]
        rho_res = calculate_aqi_rho(row)
        rho = rho_res["aqi"]
        rho_param = rho_res["rho"]

        entry = {
            "timestamp": row["timestamp"],
            "us_aqi": us,
            "india_aqi": india,
            "aqi_rho": rho,
            "rho_power": rho_param,
        }
        for col in device_aqi_columns:
            device_aqi = None if pd.isna(row.get(col)) else row[col]
            comp = compare(device_aqi, india, us, rho)
            entry[f"{col}_vs_us"] = comp["device_vs_us"]
            entry[f"{col}_vs_india"] = comp["device_vs_india"]
            entry[f"{col}_vs_rho"] = comp["device_vs_rho"]
        rows.append(entry)

    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    return frame.sort_values("timestamp").reset_index(drop=True)