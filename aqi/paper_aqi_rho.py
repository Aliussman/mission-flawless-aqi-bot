"""AQI-rho method following Tiwari, Srinivasan & Ramanathan (2026),
"Atmospheric Environment: X", 31, 100480 (the Plaksha / AQI.in paper).

Method (Section 3.3 and Section 4):
  1. Compute per-pollutant sub-indices I_i using the standard CPCB piecewise
     linear formula:  I_i = (I_HI - I_LO)/(BP_HI - BP_LO) * (C_i - BP_LO) + I_LO
  2. Power-mean aggregation (paper Eq. 1):
        AQI_rho = ( sum_i I_i**rho ) ** (1/rho),   rho != 0
     (note: this is the SUM power-mean, NOT divided by the number of pollutants)
  3. Optimal rho via Pareto multi-objective optimization, per row:
     - Search rho in [2, 50] with increment 0.05
     - Benchmarks:  AQI_max = max(I_i),  AQI_sum = sum(I_i)
     - Objectives:  O1(rho) = |AQI_rho - AQI_max|,
                    O2(rho) = |AQI_rho - AQI_sum|
     - Build the Pareto front (non-dominated candidates)
     - Normalize O1, O2 (min-max) to O1*, O2* over the sampled candidates
     - Distance to ideal point (0,0): d(rho) = sqrt(O1*^2 + O2*^2)
     - rho* = argmin d(rho)
  4. Final AQI_rho = ( sum_i I_i**rho* ) ** (1/rho*)
"""

from math import isfinite

import numpy as np

from aqi.india import BREAKPOINTS, _sub_index, _INPUTS

RHO_MIN = 2.0
RHO_MAX = 50.0
RHO_STEP = 0.05


def _subindices_from_row(row):
    """Compute CPCB sub-indices for all pollutants present in row."""
    subs = {}
    for pollutant, (column, convert) in _INPUTS.items():
        if column in row and not _missing(row[column]):
            value = convert(row[column]) if convert else row[column]
            si = _sub_index(value, BREAKPOINTS[pollutant])
            if si is not None:
                subs[pollutant] = si
    return subs


def _power_mean(values, rho):
    if rho == 0:
        return np.exp(np.mean(np.log(np.asarray(values, dtype=float))))
    vals = np.asarray(values, dtype=float)
    return np.power(np.sum(np.power(vals, rho)), 1.0 / rho)


def _paretto_optimal_rho(subindices):
    """Return (rho_star, AQI_rho) via Pareto optimization per the paper."""
    vals = list(subindices.values())
    if not vals:
        return None, None

    aqi_max = float(max(vals))
    aqi_sum = float(sum(vals))

    rhos = np.arange(RHO_MIN, RHO_MAX + 1e-6, RHO_STEP)
    o1 = np.abs([_power_mean(vals, r) - aqi_max for r in rhos])
    o2 = np.abs([_power_mean(vals, r) - aqi_sum for r in rhos])

    # Pareto non-dominated candidates
    non_dominated = []
    for i in range(len(rhos)):
        dominated = False
        for j in range(len(rhos)):
            if i == j:
                continue
            if (o1[j] <= o1[i] and o2[j] <= o2[i]) and (
                o1[j] < o1[i] or o2[j] < o2[i]
            ):
                dominated = True
                break
        if not dominated:
            non_dominated.append(i)

    if not non_dominated:
        # fallback: entire set
        non_dominated = list(range(len(rhos)))

    idx = np.array(non_dominated, dtype=int)
    o1_nd, o2_nd = o1[idx], o2[idx]

    # Normalize (min-max) over the Pareto set
    rng1 = o1_nd.max() - o1_nd.min()
    rng2 = o2_nd.max() - o2_nd.min()
    o1_star = (o1_nd - o1_nd.min()) / rng1 if rng1 > 0 else np.zeros_like(o1_nd)
    o2_star = (o2_nd - o2_nd.min()) / rng2 if rng2 > 0 else np.zeros_like(o2_nd)

    dist = np.sqrt(o1_star ** 2 + o2_star ** 2)
    best = int(idx[np.argmin(dist)])
    rho_star = float(rhos[best])
    aqi_rho = float(_power_mean(vals, rho_star))
    return rho_star, aqi_rho


def calculate_aqi_rho(row):
    """Return AQI_rho (and selected rho) for a pollutant row.

    Returns a dict with 'aqi', 'rho', and the CPCB sub-indices used.
    """
    subindices = _subindices_from_row(row)
    if not subindices:
        return {"aqi": None, "rho": None, "sub_indices": {}, "dominant": None}

    rho_star, aqi_rho = _paretto_optimal_rho(subindices)
    dominant = max(subindices, key=lambda k: subindices[k])
    return {
        "aqi": aqi_rho,
        "rho": rho_star,
        "sub_indices": subindices,
        "dominant": dominant,
    }


def _missing(value):
    try:
        return not isfinite(float(value))
    except (TypeError, ValueError):
        return True