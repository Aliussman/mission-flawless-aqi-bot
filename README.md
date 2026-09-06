# Mission Flawless AQI Bot

Automated air-quality data collection and AQI computation for a low-cost sensor
network. Two device dashboards are scraped with browser automation, the raw data
is normalized, aggregated to hourly readings, and compared against three AQI
methodologies.

## Sources

- **AQI.in** — station `Prana_dixon` (`https://dash.aqi.in/`)
- **Aurassure** — asset `Plaksha University_0223CVY3` (`https://app.aurassure.com/`)

Both dashboards authenticate with email/password and offer a CSV export. The
collectors drive that flow headlessly with Playwright and save the exported CSV.

## Pipeline

```
collectors/        ──┬─ aqi_in_browser.py   (AQI.in    export wizard)
                     └─ aurassure_browser.py (Aurassure detailed data export)
                          │
                          ▼
storage/raw_store.py    saves exported CSVs under data/raw/<source>/
                          │
                          ▼
processing/
  aqi_in_parser.py       parse + drop junk columns,  device_aqi = dashboard AQI
  aurassure_parser.py    parse layered CSV,          device_aqi = dashboard AQI
  units.py               standardize to canonical units per source
  hourly.py              resample to 1-hour averages
  merge.py               outer join sources on timestamp (device_aqi kept per source)
                          │
                          ▼
data/processed/combined/hourly_devices.csv
                          │
                          ▼
aqi/
  breakpoints.py         continuous piecewise sub-index interpolation
  conversions.py         ppb/ppm ↔ µg/m³, ppm ↔ mg/m³
  us.py                  US EPA AQI (40 CFR Appendix G)
  india.py               India CPCB / INAQI
  paper_aqi_rho.py       AQI-ρ (Tiwari et al. 2026 power-mean method)
  comparison.py          per-row US / India / AQI-ρ + device deviations
                          │
                          ▼
data/processed/combined/comparison.csv
                          │
                          ▼
reporting/summary.py     stats CSV + matplotlib charts → data/reports/
```

## Canonical units

All pollutants are normalized to a single unit system before AQI math:

| Parameter   | Canonical unit |
|-------------|----------------|
| pm2_5/pm10/pm1 | µg/m³      |
| no2/so2/o3/nh3/h2s | ppb        |
| co/co2/tvoc | ppm             |
| temperature | °C              |
| humidity    | %               |
| noise       | dB              |
| methane     | %               |

Source-specific conversions are in `processing/units.py` (AQI.in exports gases
in ppm; Aurassure exports CO in ppb).

## AQI methodologies

### US EPA (`aqi/us.py`)
Breakpoints per 40 CFR Part 58 Appendix G / the EPA AQI Technical Assistance
Document. PM in µg/m³, CO in ppm, NO₂/SO₂/O₃ in ppb (8-hour ozone primary,
1-hour used when ≥ 0.125 ppm).

### India CPCB (`aqi/india.py`)
Indian National AQI breakpoints. Gases converted to µg/m³ (NO₂/SO₂/O₃) and
mg/m³ (CO) at 25 °C.

### AQI-ρ (`aqi/paper_aqi_rho.py`)
Adaptive power-mean aggregation from:

> Prashant Tiwari, Srikant Srinivasan, T. V. Ramanathan (2026), *A data-driven
> framework for multi-pollutant air quality assessment*, Atmospheric
> Environment: X 31, 100480.

- Sub-indices from CPCB breakpoints.
- `AQIρ = (Σᵢ Iᵢ^ρ)^(1/ρ)` — the sum power-mean (not normalized by `n`), so it
  reflects cumulative multi-pollutant exposure while still recovering the
  standard max-AQI as ρ → ∞.
- Optimal ρ per row chosen by a Pareto optimization over a `[2, 50]` grid
  (step 0.05), minimizing the Euclidean distance of
  `(|AQIρ − max I|, |AQIρ − Σ I|)` (normalized) to the ideal point.

`comparison.csv` stores `us_aqi`, `india_aqi`, `aqi_rho`, `rho_power`, and the
per-device deviation of each device-reported AQI against each method.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # then fill in credentials
```

`.env`:
```
AQIIN_EMAIL=...
AQIIN_PASSWORD=...
AURASSURE_EMAIL=...
AURASSURE_PASSWORD=...
DATA_DIR=./data
```

## Run

```bash
python main.py
```

Outputs:
- `data/raw/<source>/` — raw exported CSVs
- `data/processed/<source>/hourly.csv` — per-source hourly averages
- `data/processed/combined/hourly_devices.csv` — merged hourly panel
- `data/processed/combined/comparison.csv` — AQI comparison table
- `data/reports/` — `comparison_summary.csv` (bias / RMSE / correlation) and PNG charts

## Security

- Secrets live only in local `.env` (git-ignored); never hard-code passwords,
  API keys, cookies, or session tokens.
- `.env.example` documents the required variables without real values.