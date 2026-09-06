"""Robust piecewise-linear sub-index calculation.

Standard AQI breakpoints (CPCB, US EPA) are given as integer ranges that leave
gaps between consecutive bands (e.g. PM10 bands (51, 100) and (101, 250)). Real
sensor data is continuous, so a concentration such as 100.85 falls into no band
and naive loops fall through to the final band and extrapolate nonsense values.

This module interpolates across the concatenated band knots, so values inside a
band use the exact official formula and values that fall between band edges are
bridged linearly (a continuous extension of the piecewise function).
"""

import bisect
from math import isfinite


def breakpoint_knots(breakpoints):
    """Flatten (c_lo, c_hi, i_lo, i_hi) bands into sorted (c, i) knots."""
    knots = {}
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        c_lo = float(c_lo)
        c_hi = float(c_hi)
        if c_lo in knots:
            knots[c_lo] = max(knots[c_lo], float(i_lo))
        else:
            knots[c_lo] = float(i_lo)
        if c_hi in knots:
            knots[c_hi] = max(knots[c_hi], float(i_hi))
        else:
            knots[c_hi] = float(i_hi)
    return sorted(knots.items())


def sub_index(concentration, breakpoints):
    if concentration is None or not isfinite(float(concentration)):
        return None
    c = float(concentration)

    knots = breakpoint_knots(breakpoints)
    concs = [k[0] for k in knots]
    idxs = [k[1] for k in knots]

    if c <= concs[0]:
        return idxs[0]
    if c >= concs[-1]:
        x0, y0 = concs[-2], idxs[-2]
        x1, y1 = concs[-1], idxs[-1]
        if x1 - x0 == 0:
            return min(float(y1), 500.0)
        extrap = float(y1) + (y1 - y0) / (x1 - x0) * (c - x1)
        return min(extrap, 500.0)

    pos = bisect.bisect_right(concs, c)
    x0, y0 = concs[pos - 1], idxs[pos - 1]
    x1, y1 = concs[pos], idxs[pos]
    if x1 - x0 == 0:
        return float(y1)
    return float(y0) + (y1 - y0) / (x1 - x0) * (c - x0)