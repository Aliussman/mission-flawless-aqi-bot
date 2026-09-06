import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from aqi.comparison import build_comparison_frame
from collectors.aqi_in_browser import AQIInBrowserCollector
from collectors.aurassure_browser import AurassureBrowserCollector
from config.loader import load_settings
from processing.aqi_in_parser import parse_aqi_in_csv
from processing.aurassure_parser import parse_aurassure_csv
from processing.hourly import aggregate_hourly
from processing.merge import merge_hourly
from processing.units import unit_label
from reporting.summary import build_report
from storage.raw_store import RawStore

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def collect_source(collector_cls, store, name, init_kwargs=None, collect_kwargs=None):
    collector = collector_cls(store=store, **(init_kwargs or {}))
    try:
        return await collector.collect(**(collect_kwargs or {}))
    except Exception as e:
        logging.error(f"{name} collector failed: {e}")
        return {"collector": name, "status": "error", "error": str(e)}

async def main():
    store = RawStore()
    settings = load_settings()

    results = {}
    aqi_settings = settings["aqi_in"]
    aur_settings = settings["aurassure"]

    results["aqi_in"] = await collect_source(
        AQIInBrowserCollector, store, "aqi_in",
        init_kwargs={"base_url": aqi_settings["base_url"], "station_name": aqi_settings["station_name"]},
        collect_kwargs={"timeline": aqi_settings["timeline"], "slot": aqi_settings["slot"]},
    )
    results["aurassure"] = await collect_source(
        AurassureBrowserCollector, store, "aurassure",
        init_kwargs={
            "base_url": aur_settings["base_url"],
            "asset_name": aur_settings["asset_name"],
            "date_range": aur_settings["date_range"],
            "start_date": aur_settings["start_date"],
            "end_date": aur_settings["end_date"],
        },
    )

    for key, result in results.items():
        print(f"\n=== {key} ===")
        import json
        print(json.dumps(result, indent=2, default=str))

    await process_sources(store, results)

async def process_sources(store, results):
    hourly_frames = {}
    for key in ["aurassure", "aqi_in"]:
        stored_path = results.get(key, {}).get("stored_path")
        if not stored_path:
            logging.warning(f"No stored_path for {key}, skipping processing")
            continue
        path = Path(stored_path)
        try:
            if key == "aurassure":
                df = parse_aurassure_csv(path)
            else:
                df = parse_aqi_in_csv(path)
        except Exception as e:
            logging.error(f"Failed to parse {key} CSV: {e}")
            continue

        hourly = aggregate_hourly(df)
        out_path = store.root / "processed" / key / "hourly.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        hourly.to_csv(out_path, index=False)
        print(f"\nHourly {key} data saved to {out_path}")
        hourly_frames[key] = hourly

    if len(hourly_frames) >= 1:
        combined = merge_hourly(list(hourly_frames.items()))
        out_path = store.root / "processed" / "combined" / "hourly_devices.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(out_path, index=False)
        units = {c: unit_label(c) for c in combined.columns if c != "timestamp"}
        print(f"\nCombined hourly data saved to {out_path}")
        print("Units:", units)

    device_cols = [
        c for c in combined.columns
        if c.startswith("device_aqi_")
    ] if 'combined' in locals() and combined is not None else []
    if device_cols:
        comparison = build_comparison_frame(combined, device_cols)
        out_path = store.root / "processed" / "combined" / "comparison.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        comparison.to_csv(out_path, index=False)
        print(f"\nAQI comparison saved to {out_path}")

        report_dir = store.root / "reports"
        build_report(
            comparison_csv=out_path,
            hourly_csv=store.root / "processed" / "combined" / "hourly_devices.csv",
            out_dir=report_dir,
        )

if __name__ == "__main__":
    asyncio.run(main())