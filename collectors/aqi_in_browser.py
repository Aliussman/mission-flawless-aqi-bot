import os
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

class AQIInBrowserCollector:
    def __init__(self, store, base_url=None, station_name=None):
        self.store = store
        self.base_url = base_url or os.getenv("AQIIN_BASE_URL", "https://dash.aqi.in/")
        self.station_name = station_name or os.getenv("AQIIN_STATION_NAME", "Prana_dixon")

    async def collect(self, timeline="7 days", slot="15 min"):
        email = os.getenv("AQIIN_EMAIL")
        password = os.getenv("AQIIN_PASSWORD")

        if not email or not password:
            raise RuntimeError(
                "AQIIN_EMAIL and AQIIN_PASSWORD must be set in the local environment."
            )

        result = {
            "collector": "aqi_in_browser",
            "station": self.station_name,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                accept_downloads=True,
                timezone_id="Asia/Kolkata",
            )
            page = await context.new_page()
            download_info = None

            def handle_download(dl):
                nonlocal download_info
                download_info = dl

            page.on("download", handle_download)

            try:
                # 1. Open AQI.in / login page
                await page.goto(self.base_url + "auth/login", wait_until="domcontentloaded")
                result["site_opened"] = True

                # 2. Log in using local .env
                await page.fill('input[name="email"]', email)
                await page.fill('input[name="password"]', password)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(3000)

                # Verify login succeeded (should leave the /auth/login page)
                if "/auth/login" in page.url or "/auth/" in page.url:
                    raise RuntimeError(
                        f"AQI.in login failed. Please check credentials. (URL: {page.url})"
                    )
                result["logged_in"] = True

                # 3. Open Devices (export-data wizard)
                await page.goto(self.base_url + "devices/export-data", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                result["devices_opened"] = True

                # 4. Find Prana_dixon station
                station = page.locator(f"text={self.station_name}")
                if await station.count() == 0:
                    raise RuntimeError(
                        f"Station '{self.station_name}' not found on the device selection step."
                    )

                # 5. Check online/offline status from the device list
                station_row = page.locator(
                    f"text={self.station_name}"
                ).first
                row_html = await station_row.evaluate(
                    "el => el.parentElement ? el.parentElement.innerText : el.innerText"
                )

                # Find a nearby "Online"/"Offline" label within the device entry
                online_status = await self._extract_online_status(page, station_row)
                result["online"] = online_status

                # 6. Select the device and proceed
                await station.first.click()
                await page.wait_for_timeout(1000)
                await page.click('button:has-text("Next Step")')
                await page.wait_for_timeout(2000)
                result["device_selected"] = True

                # 7. Configure export (timeline + slot + all parameters)
                timeline_el = page.locator(f'div.timeline:has-text("{timeline.lower()}")')
                if await timeline_el.count() == 0:
                    raise RuntimeError(f"Timeline option '{timeline}' not found")
                await timeline_el.click()

                slot_el = page.locator(f'div.data-type:has-text("{slot.lower()}")')
                if await slot_el.count() == 0:
                    raise RuntimeError(f"Slot type '{slot}' not found")
                await slot_el.click()

                sensors = await page.query_selector_all("div.sensor")
                for sensor in sensors:
                    await sensor.click()
                await page.wait_for_timeout(500)
                result["export_configured"] = True

                # 8. Trigger the CSV download
                dl_btn = page.locator('button:has-text("Download CSV")')
                if await dl_btn.is_disabled():
                    raise RuntimeError("Download CSV button is disabled")
                await dl_btn.click()

                # Wait for the download to arrive
                for _ in range(60):
                    await page.wait_for_timeout(1000)
                    if download_info is not None:
                        break

                if download_info is None:
                    raise RuntimeError("No CSV download was triggered")

                filename = download_info.suggested_filename
                target = Path("/tmp/opencode/var/aqi_in") / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                await download_info.save_as(str(target))

                store_path = self.store.save_raw_file(target, f"aqi_in/{filename}")
                result["status"] = "success"
                result["download_filename"] = filename
                result["stored_path"] = str(store_path)

            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
            finally:
                await browser.close()

        result["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    async def _extract_online_status(self, page, station_el) -> bool:
        try:
            # Grab the whole device entry container text and look for Online/Offline
            parent = await station_el.evaluate("""el => {
                let n = el.parentElement;
                for (let i = 0; i < 4 && n; i++) {
                    const t = n.innerText || '';
                    if (/Online|Offline/.test(t) && t.length < 600) return t;
                    n = n.parentElement;
                }
                return '';
            }""")
            if parent:
                if re.search(r"\bOnline\b", parent, re.IGNORECASE):
                    return True
                if re.search(r"\bOffline\b", parent, re.IGNORECASE):
                    return False
            return None
        except Exception:
            return None