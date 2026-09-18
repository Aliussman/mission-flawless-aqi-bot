"""AQI-rho method following Tiwari, Srinivasan & Ramanathan (2026),
"Atmospheric Environment: X", 31, 100480 (the Plaksha / AQI.in paper).

Method (Section 3.3, Section 4.1 and Algorithm 1):
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
     - Build the Pareto front (non-dominated candidates, strict dominance)
     - Normalize O1, O2 (min-max) to O1*, O2* using the GLOBAL bounds over
       all sampled candidates (Algorithm 1, Step 20), then restrict the
       normalized values to the Pareto front
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


def subindices_from_row(row):
    """Compute CPCB sub-indices for all pollutants present in a row.

    ``row`` maps pollutant concentration columns (canonical units) to values.
    Returns a dict like {'pm2_5': 120, 'o3': 45}.
    """
    subs = {}
    for pollutant, (column, convert) in _INPUTS.items():
        if column in row and not _missing(row[column]):
            value = convert(row[column]) if convert else row[column]
            si = _sub_index(value, BREAKPOINTS[pollutant])
            if si is not None:
                subs[pollutant] = si
    return subs


def calculate_aqi_rho(subindices_dict):
    """Determine the optimal rho and final AQI_rho from daily sub-indices.

    Implements the exact Pareto based search of Algorithm 1 in
    Tiwari, Srinivasan & Ramanathan (2026).

    Args:
        subindices_dict (dict): Pollutant sub-indices, e.g.
            {'pm2_5': 120, 'o3': 45}.

    Returns:
        dict: Contains the optimal rho, final AQI_rho, and benchmark values.
    """
    # Step 1: Read daily pollutant sub-index values
    vals = list(subindices_dict.values())
    if not vals:
        return {"rho_optimal": None, "aqi_rho": None}

    I = np.array(vals, dtype=float)

    # (ii) Benchmark measures
    aqi_max = np.max(I)
    aqi_sum = np.sum(I)

    # Step 2: Define search interval rho = 2 to 50, with increment 0.05
    # Added 1e-6 to upper bound to ensure 50.0 is inclusive in np.arange
    rhos = np.arange(RHO_MIN, RHO_MAX + 1e-6, RHO_STEP)
    num_candidates = len(rhos)

    # Preallocate storage for all candidates
    aqi_rhos = np.zeros(num_candidates)
    O1 = np.zeros(num_candidates)
    O2 = np.zeros(num_candidates)

    # Step 3: for each candidate value of rho do
    for k, rho in enumerate(rhos):
        # Step 4: Compute generalized air quality index AQI_rho
        aqi_rhos[k] = (np.sum(I ** rho)) ** (1.0 / rho)

        # Step 5: Objective O1(rho) vs AQI_max
        O1[k] = np.abs(aqi_rhos[k] - aqi_max)

        # Step 6: Objective O2(rho) vs AQI_sum
        O2[k] = np.abs(aqi_rhos[k] - aqi_sum)

    # Steps 7-8: data stored in arrays indexed by k; loop ends.

    # Step 9: Pareto non-dominated sorting
    dominated = np.zeros(num_candidates, dtype=bool)

    # Step 10: for each solution i do
    for i in range(num_candidates):
        # Step 11: for each solution j do
        for j in range(num_candidates):
            if i == j:
                continue

            # Step 12: if O1(j) <= O1(i) AND O2(j) <= O2(i)
            if (O1[j] <= O1[i]) and (O2[j] <= O2[i]):
                # Step 13: at least one inequality strict
                if (O1[j] < O1[i]) or (O2[j] < O2[i]):
                    # Step 14: mark solution i as dominated
                    dominated[i] = True
                    break  # no need to check further j's

            # Steps 15-18: end of conditionals and loops

    # Step 19: extract Pareto-optimal solutions
    pareto_indices = np.where(~dominated)[0]

    if len(pareto_indices) == 0:
        # Fallback if strict inequality sorting fails (edge case protection)
        pareto_indices = np.arange(num_candidates)

    # Step 20: normalize objective functions O1*, O2*
    # Global min/max bounds over the whole sampled candidate space
    min_O1, max_O1 = np.min(O1), np.max(O1)
    min_O2, max_O2 = np.min(O2), np.max(O2)

    range_O1 = max_O1 - min_O1
    range_O2 = max_O2 - min_O2

    O1_star = (O1 - min_O1) / range_O1 if range_O1 > 0 else np.zeros_like(O1)
    O2_star = (O2 - min_O2) / range_O2 if range_O2 > 0 else np.zeros_like(O2)

    # Isolate the normalized values that belong to the Pareto front
    O1_star_pareto = O1_star[pareto_indices]
    O2_star_pareto = O2_star[pareto_indices]

    # Step 21: Euclidean distance d(rho) to the ideal point (0, 0)
    d_rho = np.sqrt(O1_star_pareto ** 2 + O2_star_pareto ** 2)

    # Step 22: select optimal parameter
    best_pareto_idx = np.argmin(d_rho)
    best_global_idx = pareto_indices[best_pareto_idx]
    rho_optimal = float(rhos[best_global_idx])

    # Step 23: compute the final proposed air quality index
    aqi_rho_final = float((np.sum(I ** rho_optimal)) ** (1.0 / rho_optimal))

    # Step 24: store
    return {
        "rho_optimal": rho_optimal,
        "aqi_rho": aqi_rho_final,
        "aqi_max": float(aqi_max),
        "aqi_sum": float(aqi_sum),
        "sub_indices": subindices_dict,
    }


def _missing(value):
    try:
        return not isfinite(float(value))
    except (TypeError, ValueError):
        return True