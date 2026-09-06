import pandas as pd

def merge_hourly(source_frames, on="timestamp"):
    """Outer-join hourly frames from multiple sources on timestamp.

    Shared pollutant columns (same canonical units) are kept as-is from the
    first source; the device-reported AQI from each source is kept separate
    under ``device_aqi_<source>``.
    """
    merged = None
    for source, df in source_frames:
        frame = df.copy()
        if "device_aqi" in frame.columns:
            frame = frame.rename(columns={"device_aqi": f"device_aqi_{source}"})

        if merged is None:
            merged = frame
            continue

        incoming = frame.drop(
            columns=[c for c in frame.columns if c != on and c in merged.columns]
        )
        merged = pd.merge(merged, incoming, on=on, how="outer")

    merged[on] = pd.to_datetime(merged[on], errors="coerce")
    return merged.sort_values(on).reset_index(drop=True)