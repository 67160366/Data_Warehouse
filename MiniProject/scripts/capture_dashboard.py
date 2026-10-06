"""Capture actual Streamlit browser pages. Requires a running local app and Playwright."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TITLES = ["1 · ปัญหาปัจจุบัน", "2 · จุดที่ควรแก้ก่อน", "3 · เงื่อนไขการพลาด", "4 · ผลเมื่อมี 3Eyes", "5 · การตัดสินใจลงทุน"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--executable", default=None)
    args = parser.parse_args()
    out = ROOT / "reports/screenshots"
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.executable)
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(args.url)
        for i, title in enumerate(TITLES, 1):
            page.set_viewport_size({"width": 1600, "height": 1100})
            page.get_by_text(title, exact=True).first.click()
            page.get_by_role("heading", name=title, exact=True).wait_for(timeout=30000)
            page.locator('[data-testid="stPlotlyChart"]').first.wait_for(timeout=30000)
            page.wait_for_timeout(1500)
            if page.locator('[data-testid="stException"]').count():
                raise RuntimeError(page.locator('[data-testid="stException"]').inner_text())
            height = page.locator('[data-testid="stMain"]').evaluate("el => el.scrollHeight")
            page.set_viewport_size({"width": 1600, "height": min(6500, height + 100)})
            page.wait_for_timeout(400)
            page.screenshot(path=str(out / f"page-{i}.png"), full_page=True)
        browser.close()
    if errors:
        raise RuntimeError(errors)
    print("Captured 5 pages; no browser JavaScript errors")


if __name__ == "__main__":
    main()
