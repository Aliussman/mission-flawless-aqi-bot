"""Revised Air Quality Index (RAQI) following Cheng et al. (2004).

Wan-Lin Cheng et al., "Revised air quality index derived from an entropy
function", Atmospheric Environment 38 (2004) 383-391.

Method (Section 2):
  The PSI sub-indices I_j for the five criteria pollutants (PM10, SO2, CO,
  NO2, O3) are computed from Taiwan-EPA breakpoints (paper Table 1) using the
  standard piecewise-linear formula. RAQI then combines three factors:

      RAQI_d = Max[I1..I5]_d
               x  AvgDaily[Sum(Ij)]_d / AvgAnnual[ AvgDaily[Sum(Ij)] ]
               x  AvgAnnual{ Entropy_daily[Max(I1..I5)] }
                  / Entropy_daily[Max(I1..I5)]_d

  1. Max[I1..I5]: the PSI maximum-sub-index (= classic PSI), which carries the
     dominant-pollutant effect and reduces index eclipsing.
  2. AvgDaily[Sum(Ij)] / AvgAnnual[AvgDaily[Sum(Ij)]]: keeps today's summed
     sub-indices relative to the long-run (annual) mean sum; amplifies the
     index when the multi-pollutant load is above the background level so the
     other (non-dominant) pollutants are no longer eclipsed.
  3. AvgAnnual{E_d} / E_d: Shannon-entropy correction of the day's sub-index
     distribution (base 10, per the paper). A diffuse (spread) distribution
     has high entropy and pulls RAQI towards the mean; a concentrated one has
     low entropy and boosts RAQI to flag the eclipse-prone case.

Interpretation notes (verify against the paper PDF):
  * The paper defines the index on DAILY means. Hourly data is first
    aggregated to calendar-day means before sub-indices are computed.
  * "Annual" statistics are the averages over the whole available reference
    window (a full year when that much history exists). This module accepts an
    optional precomputed baseline so a true annual window can be supplied.
  * The published equation renders factor 2 as
    AvgDaily[Sum(Ij)] / AvgAnnual[AvgDaily[Sum(Ij)]]; the OCR of the paper text
    also contains a "5" that is dropped here to match the rendered fraction
    bars (the "5" cancels with the /5 in a cross-pollutant daily mean).
  * NO2 is only defined at PSI >= 200 in the Taiwan table, so its sub-index is
    missing below 0.6 ppm and is excluded from the sums/entropy.

Units: canonical project units in, Taiwan table units used internally:
PM10 in ug/m3 (24 h), SO2 in ppm (24 h), CO in ppm (8 h), NO2 in ppm (1 h),
O3 in ppm (1 h). Gases enter in ppb and are converted to ppm.
"""

from math import isfinite

import numpy as np
import pandas as pd

from aqi.breakpoints import sub_index as _bp_sub_index

RAQI_POLLUTANTS = ["pm10", "so2", "co", "no2", "o3"]

_PPB_TO_PPM = 1e-3

# Taiwan EPA PSI breakpoints (Cheng et al. 2004, Table 1): (c_lo, c_hi, i_lo, i_hi)
BREAKPOINTS = {
    "pm10": [  # ug/m3, 24 h
        (0.0, 50.0, 0, 50),
        (50.0, 150.0, 50, 100),
        (150.0, 350.0, 100, 200),
        (350.0, 420.0, 200, 300),
        (420.0, 500.0, 300, 400),
        (500.0, 600.0, 400, 500),
    ],
    "so2": [  # ppm, 24 h
        (0.0, 0.03, 0, 50),
        (0.03, 0.14, 50, 100),
        (0.14, 0.3, 100, 200),
        (0.3, 0.6, 200, 300),
        (0.6, 0.8, 300, 400),
        (0.8, 1.0, 400, 500),
    ],
    "co": [  # ppm, 8 h
        (0.0, 4.5, 0, 50),
        (4.5, 9.0, 50, 100),
        (9.0, 15.0, 100, 200),
        (15.0, 30.0, 200, 300),
        (30.0, 40.0, 300, 400),
        (40.0, 50.0, 400, 500),
    ],
    "no2": [  # ppm, 1 h - Taiwan defines NO2 only at PSI >= 200
        (0.6, 1.2, 200, 300),
        (1.2, 1.6, 300, 400),
        (1.6, 2.0, 400, 500),
    ],
    "o3": [  # ppm, 1 h
        (0.0, 0.06, 0, 50),
        (0.06, 0.12, 50, 100),
        (0.12, 0.2, 100, 200),
        (0.2, 0.4, 200, 300),
        (0.4, 0.5, 300, 400),
        (0.5, 0.6, 400, 500),
    ],
}

# minimum concentration below which a pollutant's PSI sub-index is undefined
_SENSOR_FLOOR = {
    "pm10": 0.0,
    "so2": 0.0,
    "co": 0.0,
    "no2": 0.6,
    "o3": 0.0,
}


def psi_sub_index(pollutant, concentration):
    """PSI sub-index for a pollutant given its Taiwan-table concentration."""
    if concentration is None or not isfinite(float(concentration)):
        return None
    c = float(concentration)
    if c < _SENSOR_FLOOR[pollutant]:
        return None
    return _bp_sub_index(c, BREAKPOINTS[pollutant])


def subindices(row):
    """Return {pollutant: PSI sub-index} for a row (canonical unit columns)."""
    out = {}
    conc = {
        "pm10": row.get("pm10"),
        "so2": row.get("so2") * _PPB_TO_PPM if row.get("so2") is not None else None,
        "co": row.get("co"),
        "no2": row.get("no2") * _PPB_TO_PPM if row.get("no2") is not None else None,
        "o3": row.get("o3") * _PPB_TO_PPM if row.get("o3") is not None else None,
    }
    for poll in RAQI_POLLUTANTS:
        si = psi_sub_index(poll, conc[poll])
        if si is not None:
            out[poll] = si
    return out


def entropy(sub_indices, base=10.0):
    """Shannon entropy (base ``base``) of a sub-index distribution.

    Weights are the normalized sub-indices w_j = I_j / Sum(I_j); the standard
    p*log(p) convention with 0*log(0) = 0.
    """
    vals = [v for v in sub_indices if v is not None and isfinite(float(v))]
    if len(vals) < 2:
        return None
    vals = np.asarray(vals, dtype=float)
    total = vals.sum()
    if total <= 0:
        return None
    w = vals / total
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = w * np.log(w) / np.log(base)
    return float(-np.nansum(terms))


def daily_from_hourly(df, timestamp_column="timestamp"):
    """Aggregate hourly panel to calendar-day means of pollutant columns."""
    out = df.copy()
    out[timestamp_column] = pd.to_datetime(out[timestamp_column], errors="coerce")
    out = out.dropna(subset=[timestamp_column])
    out["date"] = out[timestamp_column].dt.date
    numeric = RAQI_POLLUTANTS + [c for c in out.columns if c not in (timestamp_column, "date")]
    numeric = [c for c in numeric if c in out.columns and pd.api.types.is_numeric_dtype(out[c])]
    return out[numeric + ["date"]].groupby("date", as_index=False).mean()


def compute_raqi(daily_frame, date_column="date", baseline=None):
    """Compute daily RAQI from a daily-mean pollutant panel.

    ``daily_frame``: DataFrame with a date column and PM10/SO2/CO/NO2/O3
    columns in canonical project units, one row per day.

    ``baseline``: optional dict of annual reference statistics
    (``sum_annual``, ``entropy_annual``) to use instead of the window's own
    means. Keys mirror the returned DataFrame final rows.

    Returns a DataFrame sorted by date with per-day sub-indices, PSI max,
    summed sub-indices, entropy and the RAQI factor breakdown.
    """
    df = daily_frame.copy()
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    df = df.dropna(subset=[date_column]).sort_values(date_column)
    if df.empty:
        return pd.DataFrame()

    rows = []
    for idx, day in df.iterrows():
        subs = subindices(day.to_dict())
        present = list(subs.values())
        max_v = max(present) if present else None
        sum_v = sum(present) if present else None
        entr = entropy(present) if present else None
        rows.append({"date": day[date_column], **subs, "max_psi": max_v,
                     "sum_idx": sum_v, "entropy": entr})
    frame = pd.DataFrame(rows)

    if baseline is None:
        sum_annual = float(frame["sum_idx"].mean())
        entropy_annual = float(frame["entropy"].mean()) if frame["entropy"].notna().any() else 0.0
    else:
        sum_annual = float(baseline["sum_annual"])
        entropy_annual = float(baseline.get("entropy_annual", 0.0) or 0.0)

    frame["factor1_max"] = frame["max_psi"]
    frame["factor2"] = np.where(
        np.isfinite(sum_annual) and sum_annual > 0,
        frame["sum_idx"] / sum_annual,
        np.nan,
    )
    frame["factor3"] = np.where(
        frame["entropy"].notna() & (frame["entropy"] > 0) & (entropy_annual > 0),
        entropy_annual / frame["entropy"],
        1.0,
    )
    frame["raqi"] = frame["factor1_max"] * frame["factor2"] * frame["factor3"]
    frame["sum_annual"] = sum_annual
    frame["entropy_annual"] = entropy_annual
    return frame.reset_index(drop=True)