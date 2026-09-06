"""Unit conversions for AQI computations at reference conditions (25 C, 1 atm).

Standard relationship: ug/m3 = ppb * molar_mass / 24.45
(pounds: 24.45 L/mol is the molar volume of an ideal gas at 25 C, 1 atm).
"""

MOLAR_VOLUME_L = 24.45

PPB_TO_PPM = 1e-3
PPM_TO_PPB = 1e3

# molar mass (g/mol)
MOLAR_MASS = {
    "co": 28.01,
    "no2": 46.0055,
    "so2": 64.066,
    "o3": 48.0,
    "nh3": 17.031,
    "h2s": 34.08,
}

# ug/m3 per ppb
PPB_TO_UGM3 = {gas: MOLAR_MASS[gas] / MOLAR_VOLUME_L for gas in MOLAR_MASS}

# ug/m3 per ppm == mg/m3 per ppm
PPM_TO_UGM3 = {gas: MOLAR_MASS[gas] / MOLAR_VOLUME_L * 1e3 for gas in MOLAR_MASS}

def ppb_to_ugm3(value, gas):
    if value is None:
        return None
    return value * PPB_TO_UGM3[gas]

def ppm_to_ugm3(value, gas):
    if value is None:
        return None
    return value * PPM_TO_UGM3[gas]

def ppm_to_mgm3(value, gas):
    if value is None:
        return None
    return value * MOLAR_MASS[gas] / MOLAR_VOLUME_L