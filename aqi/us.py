"""US EPA Air Quality Index (US AQI).

Breakpoints follow EPA 40 CFR Part 58 Appendix G / the AQI Technical
Assistance Document. Inputs are expected in canonical project units:
pm2_5/pm10 in ug/m3, co in ppm, no2/so2 in ppb, o3 in ppb.
"""

from math import isfinite

from aqi.breakpoints import sub_index as _breakpoint_sub_index
from aqi.conversions import PPB_TO_PPM

BREAKPOINTS = {
    "pm2_5": [
        (0.0, 9.0, 0, 50),
        (9.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 125.4, 151, 200),
        (125.5, 225.4, 201, 300),
        (225.5, 325.4, 301, 400),
        (325.5, 425.4, 401, 500),
    ],
    "pm10": [
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 504, 301, 400),
        (505, 604, 401, 500),
    ],
    # ppm, 8-hour (primary ozone metric)
    "o3_8hr": [
        (0.000, 0.054, 0, 50),
        (0.055, 0.070, 51, 100),
        (0.071, 0.085, 101, 150),
        (0.086, 0.105, 151, 200),
        (0.106, 0.200, 201, 300),
    ],
    # ppm, 1-hour (used when 8-hour exceeds the 8-hour banding)
    "o3_1hr": [
        (0.125, 0.164, 101, 150),
        (0.165, 0.204, 151, 200),
        (0.205, 0.404, 201, 300),
        (0.405, 0.504, 301, 400),
        (0.505, 0.604, 401, 500),
    ],
    "co": [
        (0.0, 4.4, 0, 50),
        (4.5, 9.4, 51, 100),
        (9.5, 12.4, 101, 150),
        (12.5, 15.4, 151, 200),
        (15.5, 30.4, 201, 300),
        (30.5, 40.4, 301, 400),
        (40.5, 50.4, 401, 500),
    ],
    "so2": [
        (0, 35, 0, 50),
        (36, 75, 51, 100),
        (76, 185, 101, 150),
        (186, 304, 151, 200),
        (305, 604, 201, 300),
        (605, 804, 301, 400),
        (805, 1004, 401, 500),
    ],
    "no2": [
        (0, 53, 0, 50),
        (54, 100, 51, 100),
        (101, 360, 101, 150),
        (361, 649, 151, 200),
        (650, 1249, 201, 300),
        (1250, 1649, 301, 400),
        (1650, 2049, 401, 500),
    ],
}

def _sub_index(concentration, breakpoints):
    return _breakpoint_sub_index(concentration, breakpoints)

def calculate_us_aqi(row):
    """Return dict of US AQI sub-indices and the overall value.

    ``row`` is a mapping with canonical-unit keys.
    """
    sub_indices = {}

    for pollutant in ("pm2_5", "pm10", "co", "so2", "no2"):
        if pollutant in row and not _missing(row[pollutant]):
            sub_indices[pollutant] = _sub_index(row[pollutant], BREAKPOINTS[pollutant])

    if "o3" in row and not _missing(row["o3"]):
        o3_ppm = float(row["o3"]) * PPB_TO_PPM
        si_8hr = _sub_index(o3_ppm, BREAKPOINTS["o3_8hr"])
        if o3_ppm >= 0.125:
            si_1hr = _sub_index(o3_ppm, BREAKPOINTS["o3_1hr"])
            sub_indices["o3"] = max(si_8hr or 0.0, si_1hr or 0.0)
        else:
            sub_indices["o3"] = si_8hr

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