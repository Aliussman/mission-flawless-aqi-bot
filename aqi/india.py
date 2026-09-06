"""India (CPCB) Air Quality Index.

Breakpoints follow the Indian National Air Quality Index (INAQI) / CPCB
methodology. Gaseous inputs are expected in canonical project units and are
converted to the concentrations required by CPCB: NO2/SO2/O3 in ug/m3, CO in
mg/m3, PM2.5/PM10 in ug/m3.
"""

from math import isfinite

from aqi.breakpoints import sub_index as _breakpoint_sub_index
from aqi.conversions import ppm_to_mgm3, ppb_to_ugm3

BREAKPOINTS = {
    "pm2_5": [  # ug/m3, 24h
        (0, 30, 0, 50),
        (31, 60, 51, 100),
        (61, 90, 101, 200),
        (91, 120, 201, 300),
        (121, 250, 301, 400),
        (251, 9999, 401, 500),
    ],
    "pm10": [  # ug/m3, 24h
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 250, 101, 200),
        (251, 350, 201, 300),
        (351, 430, 301, 400),
        (431, 9999, 401, 500),
    ],
    "no2": [  # ug/m3, 24h
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 180, 101, 200),
        (181, 280, 201, 300),
        (281, 400, 301, 400),
        (401, 9999, 401, 500),
    ],
    "so2": [  # ug/m3, 24h
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 380, 101, 200),
        (381, 800, 201, 300),
        (801, 1600, 301, 400),
        (1601, 9999, 401, 500),
    ],
    "o3": [  # ug/m3, 8h
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 168, 101, 200),
        (169, 208, 201, 300),
        (209, 748, 301, 400),
        (749, 9999, 401, 500),
    ],
    "co": [  # mg/m3, 8h
        (0.0, 1.0, 0, 50),
        (1.1, 2.0, 51, 100),
        (2.1, 10.0, 101, 200),
        (10.1, 17.0, 201, 300),
        (17.1, 34.0, 301, 400),
        (34.1, 9999, 401, 500),
    ],
}

# pollutant -> canonical input column and conversion to CPCB units
_INPUTS = {
    "pm2_5": ("pm2_5", None),
    "pm10": ("pm10", None),
    "no2": ("no2", lambda v: ppb_to_ugm3(v, "no2")),
    "so2": ("so2", lambda v: ppb_to_ugm3(v, "so2")),
    "o3": ("o3", lambda v: ppb_to_ugm3(v, "o3")),
    "co": ("co", lambda v: ppm_to_mgm3(v, "co")),
}

def _sub_index(concentration, breakpoints):
    return _breakpoint_sub_index(concentration, breakpoints)

def calculate_india_aqi(row):
    """Return dict of CPCB sub-indices and the overall INAQI value."""
    sub_indices = {}
    for pollutant, (column, convert) in _INPUTS.items():
        if column in row and not _missing(row[column]):
            value = convert(row[column]) if convert else row[column]
            sub_indices[pollutant] = _sub_index(value, BREAKPOINTS[pollutant])

    if sub_indices:
        dominant = max(sub_indices, key=lambda k: sub_indices[k])
        overall = sub_indices[dominant]
    else:
        dominant, overall = None, None

    return {
        "sub_indices": sub_indices,
        "aqi": overall,
        "dominant": dominant,
    }

def _missing(value):
    try:
        return not isfinite(float(value))
    except (TypeError, ValueError):
        return True