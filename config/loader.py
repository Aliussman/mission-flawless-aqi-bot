"""Load config/settings.yaml (with defaults) so the collectors and pipeline
are configurable without editing code."""

import os
from pathlib import Path
from copy import deepcopy

import yaml

DEFAULT_SETTINGS = {
    "timezone": "Asia/Kolkata",
    "collection": {
        "interval_minutes": 60,
        "lookback_hours": 3,
        "save_raw": True,
    },
    "aqi_in": {
        "station_name": "Prana_dixon",
        "base_url": "https://dash.aqi.in/",
        "timeline": "7 days",
        "slot": "15 min",
    },
    "aurassure": {
        "asset_name": "Plaksha University_0223CVY3",
        "base_url": "https://app.aurassure.com/",
        "date_range": "Last 7 days",
        "start_date": None,
        "end_date": None,
    },
    "parameters": [
        "aqi",
        "pm2_5",
        "pm10",
        "no2",
        "so2",
        "o3",
        "co",
        "co2",
        "temperature",
        "humidity",
    ],
}


def _deep_merge(base, override):
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(path=None):
    path = Path(path or os.getenv("SETTINGS_PATH", "config/settings.yaml"))
    data = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULT_SETTINGS, data)