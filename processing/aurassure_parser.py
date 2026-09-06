import io
import pandas as pd

from processing.units import standardize_units

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

def parse_aurassure_csv(file_path):
    content = file_path.read_text(encoding="utf-8", errors="replace")

    lines = content.splitlines()
    start_idx = None
    header_idx = None

    for i, line in enumerate(lines):
        if "Detailed Data" in line:
            start_idx = i + 1
            continue
        if start_idx and "Date & time" in line:
            header_idx = i
            break

    if start_idx is None or header_idx is None:
        raise ValueError("Could not locate the Detailed Data section in CSV")

    data_lines = [l for l in lines[header_idx:] if l.strip()]
    csv_str = "\n".join(data_lines)

    df = pd.read_csv(io.StringIO(csv_str))

    if "Date & time (DD MMM, HH:mm - DD MMM YYYY, HH:mm)" in df.columns:
        time_col = "Date & time (DD MMM, HH:mm - DD MMM YYYY, HH:mm)"
    elif "Date & time" in str(df.columns):
        time_col = [c for c in df.columns if "Date" in c][0]
    else:
        time_col = df.columns[0]

    df.rename(columns={time_col: "timestamp"}, inplace=True)

    df = df.rename(columns={
        col: COLUMN_MAP.get(str(col).split()[0], col)
        for col in df.columns
        if str(col).split()
    })

    for col in ["device_aqi", "pm2_5", "pm10", "no2", "so2", "o3", "co", "co2", "temperature", "humidity"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["timestamp"] = df["timestamp"].apply(_parse_aurassure_time)
    df = df.dropna(subset=["timestamp"])

    return standardize_units(df, "aurassure")

def _parse_aurassure_time(val):
    if isinstance(val, str):
        parts = val.split(" - ")
        if len(parts) == 2:
            start, end = parts[0].strip(), parts[1].strip()
            end_cleaned = " ".join(end.split())
            try:
                end_dt = pd.to_datetime(end_cleaned, format="%d %b %Y , %H:%M")
            except ValueError:
                try:
                    end_dt = pd.to_datetime(end_cleaned, format="%d %b %Y, %H:%M")
                except ValueError:
                    try:
                        end_dt = pd.to_datetime(end_cleaned)
                    except Exception:
                        return pd.NaT
            # Start part lacks the year, borrow it from the end part
            try:
                start_dt = pd.to_datetime(f"{start}, {end_dt.year}", format="%d %b, %H:%M, %Y")
            except Exception:
                try:
                    start_dt = pd.to_datetime(f"{start} {end_dt.year}")
                except Exception:
                    return end_dt
            return start_dt
        return val.strip()
    return val