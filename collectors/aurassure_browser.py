import os
import re
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

class AurassureBrowserCollector:
    def __init__(self, store, base_url=None, asset_name=None, date_range=None,
                 start_date=None, end_date=None):
        self.store = store
        self.base_url = base_url or os.getenv("AURASSURE_BASE_URL", "https://app.aurassure.com/")
        self.asset_name = asset_name or os.getenv("AURASSURE_ASSET_NAME", "Plaksha University_0223CVY3")
        self.date_range = date_range or os.getenv("AURASSURE_DATE_RANGE", "Last 7 days")
        self.start_date = start_date
        self.end_date = end_date

    async def collect(self):
        email = os.getenv("AURASSURE_EMAIL")
        password = os.getenv("AURASSURE_PASSWORD")

        if not email or not password:
            raise RuntimeError(
                "AURASSURE_EMAIL and AURASSURE_PASSWORD must be set in the local environment."
            )

        result = {
            "collector": "aurassure_browser",
            "asset": self.asset_name,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                accept_downloads=True,
                timezone_id="Asia/Kolkata",
            )
            page = await context.new_page()
            download = None

            def handle_download(dl):
                nonlocal download
                download = dl

            page.on("download", handle_download)

            try:
                # 1. Open site
                await page.goto(self.base_url, wait_until="domcontentloaded")
                result["site_opened"] = True

                # Accept cookies if present
                try:
                    cookie_btn = page.locator("#acceptCookie")
                    if await cookie_btn.is_visible(timeout=3000):
                        await cookie_btn.click()
                except PlaywrightTimeoutError:
                    pass

                # 2. Log in
                await page.fill("#email", email)
                await page.click("#next_btn")
                await page.wait_for_timeout(1500)
                await page.fill("#password", password)
                await page.click("#form_submit_btn")
                await page.wait_for_load_state("networkidle", timeout=15000)
                await page.wait_for_timeout(3000)
                result["logged_in"] = True

                # 3. Go to Reports
                await page.goto(f"{self.base_url}enterprise/17468/reports", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # 4. Click Custom Reports
                await page.click("text=Custom Reports")
                await page.wait_for_timeout(2000)

                # 5. Apply the configured date range (preset or Custom)
                await self._set_date_range(page, self.date_range, self.start_date, self.end_date)
                result["date_range"] = self.date_range
                await page.wait_for_timeout(1000)

                # 6. Generate the report (Average format is default)
                await page.click("text=Generate Report")
                await page.wait_for_timeout(10000)
                result["report_generated"] = True

                # 6. Open download modal
                await page.click('span[class*="download-btn"]')
                await page.wait_for_timeout(2000)

                # 7. Select CSV format
                await page.click('.ant-modal input[type="radio"][value="csv"]')
                await page.wait_for_timeout(500)

                # 8. Trigger CSV download
                await page.click('.ant-modal-footer button:has-text("Download")')
                await page.wait_for_timeout(5000)

                if download:
                    filename = download.suggested_filename
                    target_dir = Path("/tmp/opencode/var/aurassure")
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target = target_dir / filename
                    await download.save_as(str(target))

                    # Copy into store data dir
                    store_path = self.store.save_raw_file(target, f"aurassure/{filename}")
                    result["status"] = "success"
                    result["download_filename"] = filename
                    result["stored_path"] = str(store_path)
                    result["online"] = self._infer_online_status(target)
                else:
                    result["status"] = "error"
                    result["error"] = "No download was triggered"

            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
            finally:
                await browser.close()

        result["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    async def _set_date_range(self, page, date_range, start_date=None, end_date=None):
        """Select the report period from the #ddrange preset dropdown.

        Presets seen on the dashboard: 'Last 7 days', 'This Week',
        'Last week', 'Last 30 days', 'Last Month', 'This month',
        'This Quarter (Jul - Sep)', 'Last Quarter (Apr - Jun)',
        'this_year', 'Custom'.

        When 'Custom' is chosen, ``start_date`` / ``end_date`` are required
        in the format the picker accepts, e.g. '01 Jun 2026, 00:00'.
        """
        if not date_range:
            return

        # Only change it when the currently selected preset differs.
        selected = page.locator(
            ".ant-select:has(#ddrange) .ant-select-selection-item"
        )
        current = ""
        try:
            current = (await selected.inner_text()).strip()
        except Exception:
            pass

        if current == date_range and date_range.lower() != "custom":
            return

        await page.click(".ant-select:has(#ddrange)")
        await page.wait_for_timeout(800)

        options = page.locator(
            ".ant-select-dropdown:visible .ant-select-item-option"
        )
        matched = False
        for i in range(await options.count()):
            text = (await options.nth(i).inner_text()).strip()
            if text == date_range:
                await options.nth(i).click()
                matched = True
                break

        if not matched:
            raise RuntimeError(
                f"Date range '{date_range}' not found in the Custom Reports options"
            )

        if date_range.lower() == "custom":
            if not start_date or not end_date:
                raise RuntimeError(
                    "Custom date range requires 'start_date' and 'end_date' "
                    "in settings.yaml (format 'DD Mon YYYY, HH:mm')."
                )
            await page.wait_for_timeout(800)
            start_input = page.locator("input#custom_range")
            end_input = page.locator('.ant-picker-range input').nth(1)
            await start_input.click()
            await start_input.fill(start_date)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(300)
            await end_input.click()
            await end_input.fill(end_date)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(300)

    def _infer_online_status(self, csv_path: Path) -> bool:
        try:
            content = csv_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"From:\s*([\d]{2} [A-Za-z]{3} [\d]{4}, [\d]{2}:\d{2})\s*to\s*([\d]{2} [A-Za-z]{3} [\d]{4}, [\d]{2}:\d{2})", content)
            if match:
                end_str = match.group(2)
                end = datetime.strptime(end_str, "%d %b %Y, %H:%M")
                return (datetime.now(timezone.utc) - end.replace(tzinfo=timezone.utc)).total_seconds() < 3600
            return False
        except Exception:
            return False