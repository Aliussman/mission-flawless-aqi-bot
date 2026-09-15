import asyncio
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from config.loader import load_settings
from main import run_pipeline
from processing.aqi_in_parser import parse_aqi_in_csv
from processing.aurassure_parser import parse_aurassure_csv
from processing.units import CANONICAL_UNITS
from storage.raw_store import RawStore

load_dotenv()

st.set_page_config(page_title="Mission Flawless AQI Dashboard", layout="wide")

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))

NODES = {
    "aqi_in": {"label": "Prana_dixon", "source": "AQI.in"},
    "aurassure": {"label": "Plaksha University_0223CVY3", "source": "Aurassure"},
}

METHODS = ["us_aqi", "india_aqi", "aqi_rho"]
METHOD_LABELS = {
    "us_aqi": "US EPA",
    "india_aqi": "India CPCB",
    "aqi_rho": "AQI \u03c1 (paper)",
}

POLLUTANTS = ["pm2_5", "pm10", "no2", "so2", "o3", "co", "co2", "temperature", "humidity"]

UNIT_LABELS = {
    "ug_m3": "\u00b5g/m\u00b3",
    "ppb": "ppb",
    "ppm": "ppm",
    "deg_c": "\u00b0C",
    "pct": "%",
    "db": "dB",
    "index": "index",
}

DATE_FMT = "%d %b %Y, %H:%M"

COLLECTED = st.session_state.setdefault("_pipeline_ran", False)


def _friendly_unit(column):
    unit = CANONICAL_UNITS.get(column, "")
    return UNIT_LABELS.get(unit, unit)


def _label_for(column):
    base = column.replace("device_aqi_", "device: ").replace("_", " ").title()
    unit = _friendly_unit(column)
    return f"{base} ({unit})" if unit else base


# ---------------------------------------------------------------------------
# Cached data loading / pipeline execution
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_csv(path, mtime):
    return pd.read_csv(path)


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return None
    return load_csv(str(path), os.path.getmtime(path))


@st.cache_data(show_spinner=False)
def parse_raw_cached(source, path, mtime):
    if source == "aurassure":
        return parse_aurassure_csv(Path(path))
    return parse_aqi_in_csv(Path(path))


def read_raw(source, path):
    path = Path(path)
    if not path.exists():
        return None
    return parse_raw_cached(source, str(path), os.path.getmtime(path))


@st.cache_data(show_spinner=False, ttl=30 * 60)
def run_pipeline_cached(start_str, end_str, force):
    settings = load_settings()
    settings["aurassure"]["date_range"] = "Custom"
    settings["aurassure"]["start_date"] = start_str
    settings["aurassure"]["end_date"] = end_str
    settings["aqi_in"]["timeline"] = _aqi_timeline_for_range(start_str, end_str)
    return asyncio.run(run_pipeline(RawStore(), settings))


def _aqi_timeline_for_range(start_str, end_str):
    start = datetime.strptime(start_str, DATE_FMT)
    end = datetime.strptime(end_str, DATE_FMT)
    hours = (end - start).total_seconds() / 3600.0
    for label, h in (("12 hours", 12), ("1 day", 24), ("7 days", 168), ("30 days", 720)):
        if hours <= h:
            return label
    return "30 days"


# ---------------------------------------------------------------------------
# Node status
# ---------------------------------------------------------------------------

def node_status(df, device_col, now, end_dt, stale_hours=72, min_coverage=0.2):
    """Return (status, last_seen, coverage, valid_count) for a device column."""
    if df is None or device_col not in df.columns:
        return "no_data", None, 0.0, 0

    s = pd.to_numeric(df[device_col], errors="coerce")
    mask = s.notna()
    total = len(df)
    valid = int(mask.sum())
    coverage = valid / total if total else 0.0

    times = pd.to_datetime(df["timestamp"], errors="coerce")
    last_valid = times[mask]
    latest = last_valid.max() if len(last_valid) else pd.NaT
    if pd.isna(latest):
        return "offline", None, coverage, valid

    age_hours = (now - latest).total_seconds() / 3600.0
    recency_ok = latest <= end_dt + pd.Timedelta(hours=stale_hours) and age_hours <= stale_hours
    if recency_ok and coverage >= min_coverage:
        return "online", latest, coverage, valid
    return "offline", latest, coverage, valid


# ---------------------------------------------------------------------------
# Sidebar: run configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("\U0001f534 Mission Flawless AQI")

    st.subheader("Date range")
    preset = st.radio(
        "Range preset",
        ["Last 24 hours", "Last 7 days", "Last 30 days", "Custom"],
        index=1,
    )

    now = datetime.now()
    if preset == "Custom":
        start_date, end_date = st.date_input(
            "Period", value=[date.today() - timedelta(days=7), date.today()]
        )
        start_time = st.time_input("Start time", value=time(0, 0))
        end_time = st.time_input("End time", value=time(23, 0))
        start_dt = datetime.combine(start_date, start_time)
        end_dt = datetime.combine(end_date, end_time)
        if end_dt <= start_dt:
            st.error("End must be after start.")
            end_dt = start_dt + timedelta(hours=6)
    else:
        days = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30}[preset]
        end_dt = now
        start_dt = now - timedelta(days=days)
    start_str = start_dt.strftime(DATE_FMT)
    end_str = end_dt.strftime(DATE_FMT)

    st.caption(f"Range: {start_str} \u2192 {end_str}")

    st.divider()

    st.subheader("Pipeline")
    st.caption("Command-line runs use config/settings.yaml; the values below override it in-memory \u2014 nothing is written back to the file.")
    if st.button("Fetch & Process Data", type="primary", width="stretch"):
        with st.spinner("Scraping nodes and calculating AQI..."):
            try:
                results = run_pipeline_cached(start_str, end_str, False)
            except Exception as exc:
                st.session_state._pipeline_ran = False
                st.sidebar.error(f"Pipeline failed: {exc}")
            else:
                st.session_state._pipeline_ran = True
                st.session_state._last_results = results
                st.sidebar.success("Collection + processing complete.")
    force = st.checkbox("Force re-scrape (bypass cache)", value=False)
    if force:
        run_pipeline_cached.clear()
        st.caption("\u26a0\ufe0f Cache cleared \u2014 next fetch will re-scrape both dashboards.")

    creds = {
        "AQIIN_EMAIL": "AQI.in",
        "AQIIN_PASSWORD": "AQI.in",
        "AURASSURE_EMAIL": "Aurassure",
        "AURASSURE_PASSWORD": "Aurassure",
    }
    missing = [src for env, src in creds.items() if not os.getenv(env)]
    if missing:
        st.warning(f"Missing credentials in .env for: {', '.join(missing)}. Scraping will fail \u2014 connect them and click the button again.")

# ---------------------------------------------------------------------------
# Load latest data artifacts
# ---------------------------------------------------------------------------

hourly_path = DATA_DIR / "processed" / "combined" / "hourly_devices.csv"
comparison_path = DATA_DIR / "processed" / "combined" / "comparison.csv"
summary_path = DATA_DIR / "reports" / "comparison_summary.csv"

dev = read_csv(hourly_path)
cmp = read_csv(comparison_path)
summary = read_csv(summary_path)

# ---------------------------------------------------------------------------
# Header / hero
# ---------------------------------------------------------------------------

st.title("Mission Flawless AQI \u2014 Monitoring Dashboard")
st.caption(
    "Low-cost AQI sensor network (Prana_dixon via AQI.in, Plaksha University via Aurassure). "
    "Three methodologies are compared against each device-reported AQI."
)

if not dev is None and not cmp is None and not st.session_state._pipeline_ran:
    st.info("Showing the last processed dataset. Click **Fetch & Process Data** in the sidebar to pull fresh data for the selected range.")
elif not dev is None and not cmp is None and st.session_state._pipeline_ran:
    st.success(f"Latest data covers the requested range and is ready below.")
elif dev is None and cmp is None:
    st.info("No processed data found yet. Configure a date range and run **Fetch & Process Data** from the sidebar.")

# ---------------------------------------------------------------------------
# Pipeline status
# ---------------------------------------------------------------------------

results = st.session_state.get("_last_results", {})
if results:
    st.subheader("Latest fetch")
    for key, res in results.items():
        if res.get("status") == "success":
            st.success(f"**{res.get('collector', key)}** \u2014 saved {res.get('download_filename', '')} ({res.get('stored_path', '')})")
        else:
            st.error(f"**{res.get('collector', key)}** failed: {res.get('error', 'unknown error')}")

# ---------------------------------------------------------------------------
# Node status monitor
# ---------------------------------------------------------------------------

st.subheader("\U0001f4e1 Node status")

if dev is not None:
    cols = st.columns(len(NODES))
    for idx, (key, meta) in enumerate(NODES.items()):
        device_col = f"device_aqi_{key}"
        status, latest, coverage, valid = node_status(dev, device_col, now, end_dt)
        with cols[idx]:
            badge = {
                "online": "\U0001f7e2 Online",
                "offline": "\U0001f534 Offline",
                "no_data": "\u26ab No data",
            }[status]
            st.metric(
                f"{badge} \u2014 {meta['label']}",
                meta["source"],
                delta=f"{coverage * 100:.0f}% coverage",
            )
            if latest is not None:
                st.caption(f"Last valid reading: {latest}")
            else:
                st.caption("No valid readings in this window.")
else:
    st.info("Run the pipeline to see node online/offline status.")

# ---------------------------------------------------------------------------
# Current AQI snapshot
# ---------------------------------------------------------------------------

if cmp is not None and not cmp.empty:
    st.subheader("Latest computed AQI")
    latest_row = cmp.iloc[-1]
    cols = st.columns(len(METHODS))
    for col, m in zip(cols, METHODS):
        val = latest_row.get(m)
        col.metric(METHOD_LABELS[m], "n/a" if pd.isna(val) else f"{val:.1f}")

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

if cmp is not None and not cmp.empty:
    st.subheader("AQI methodology comparison over time")
    cmp_plot = cmp.copy()
    cmp_plot["timestamp"] = pd.to_datetime(cmp_plot["timestamp"], errors="coerce")
    cmp_plot = cmp_plot.dropna(subset=["timestamp"]).sort_values("timestamp")
    renamed = cmp_plot.rename(columns=METHOD_LABELS)
    fig1 = px.line(
        renamed, x="timestamp", y=list(METHOD_LABELS.values()),
        labels={"timestamp": "Time", "value": "AQI", "variable": "Method"},
    )
    fig1.update_layout(legend_title_text="Method", hovermode="x unified", height=430)
    st.plotly_chart(fig1, width="stretch")

if dev is not None and not dev.empty:
    st.subheader("Raw pollutant trends")
    dev_plot = dev.copy()
    dev_plot["timestamp"] = pd.to_datetime(dev_plot["timestamp"], errors="coerce")
    dev_plot = dev_plot.dropna(subset=["timestamp"]).sort_values("timestamp")

    available = [p for p in POLLUTANTS if p in dev_plot.columns]
    selected = st.multiselect(
        "Pollutants (canonical units)",
        available,
        default=[p for p in ["pm2_5", "pm10", "no2"] if p in available],
    )
    if selected:
        trace_labels = {p: _label_for(p) for p in selected}
        renamed = dev_plot[["timestamp"] + selected].rename(columns=trace_labels)
        fig2 = px.line(
            renamed, x="timestamp", y=list(trace_labels.values()),
            labels={"timestamp": "Time", "value": "Concentration", "variable": "Pollutant"},
        )
        fig2.update_layout(legend_title_text="Pollutant", hovermode="x unified", height=430)
        st.plotly_chart(fig2, width="stretch")
    else:
        st.info("Select at least one pollutant above.")

# ---------------------------------------------------------------------------
# Raw / processed data previews
# ---------------------------------------------------------------------------

with st.expander("Raw & processed CSV previews"):
    def _preview(title, df, max_rows=1000):
        if df is None:
            st.write(f"**{title}** \u2014 not available")
            return
        st.write(f"**{title}** \u2014 {len(df)} rows")
        st.dataframe(df.head(max_rows), width="stretch")

    _preview("Combined hourly (processed/combined/hourly_devices.csv)", dev)
    _preview("AQI comparison (processed/combined/comparison.csv)", cmp)
    _preview("Report summary (reports/comparison_summary.csv)", summary)

    for source in ["aqi_in", "aurassure"]:
        hourly = read_csv(DATA_DIR / "processed" / source / "hourly.csv")
        _preview(f"Hourly {source} (processed/{source}/hourly.csv)", hourly)

    raw_dir = DATA_DIR / "raw" / "aurassure"
    raw_files = sorted(raw_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True) if raw_dir.exists() else []
    if raw_files:
        latest_raw = read_raw("aurassure", raw_files[0])
        _preview(f"Latest raw Aurassure export: {raw_files[0].name}", latest_raw)
    else:
        st.write("**Raw Aurassure exports** \u2014 none found")

    rawin_dir = DATA_DIR / "raw" / "aqi_in"
    rawin_files = sorted(rawin_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True) if rawin_dir.exists() else []
    if rawin_files:
        latest_rawin = read_raw("aqi_in", rawin_files[0])
        _preview(f"Latest raw AQI.in export: {rawin_files[0].name}", latest_rawin)
    else:
        st.write("**Raw AQI.in exports** \u2014 none found")