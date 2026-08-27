"""Record the current companion UI: home roster, Ask PEX, Settings page."""

from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parents[3] / "docs" / "demo"
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(
        viewport={"width": 920, "height": 700},
        record_video_dir=str(out),
        record_video_size={"width": 920, "height": 700},
    )
    page = context.new_page()
    page.goto("http://localhost:1420", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "01-home.png"))
    roster = page.locator(".roster-pet")
    if roster.count() > 1:
        roster.nth(1).click()
        page.wait_for_timeout(700)
        page.screenshot(path=str(out / "02-roster.png"))
    ask = page.get_by_role("textbox", name="Ask PEX")
    if ask.count():
        ask.fill("What needs me?")
        page.get_by_role("button", name="Ask", exact=True).click()
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out / "03-ask-pex.png"))
    page.get_by_role("button", name="Settings").click()
    page.wait_for_timeout(600)
    page.screenshot(path=str(out / "04-settings.png"))
    page.get_by_role("button", name="Back").click()
    page.wait_for_timeout(500)
    page.screenshot(path=str(out / "05-home-return.png"))
    context.close()
    browser.close()

videos = list(out.glob("*.webm"))
print("videos", [str(path) for path in videos])
