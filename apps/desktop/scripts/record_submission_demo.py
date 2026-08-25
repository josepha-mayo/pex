from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(r"C:\Users\JosephMayo\Projects\pex\docs\demo")
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(
        viewport={"width": 438, "height": 720},
        record_video_dir=str(out),
        record_video_size={"width": 438, "height": 720},
    )
    page = context.new_page()
    page.goto("http://127.0.0.1:1420", wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(out / "01-compact.png"))
    page.locator(".pet-actor").first.click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / "02-inspector.png"))
    page.get_by_role("button", name="Open desk").click()
    page.wait_for_timeout(900)
    page.locator("summary").filter(has_text="Pet").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Tally", exact=True).scroll_into_view_if_needed()
    page.get_by_role("button", name="Tally", exact=True).click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / "03-desk-tally.png"))
    page.get_by_role("button", name="Relay", exact=True).click()
    page.wait_for_timeout(700)
    page.get_by_role("button", name="Pex", exact=True).click()
    page.wait_for_timeout(700)
    page.locator("summary").filter(has_text="Active work").click()
    page.wait_for_timeout(500)
    page.screenshot(path=str(out / "04-active-work.png"))
    page.get_by_role("button", name="Back").click()
    page.wait_for_timeout(600)
    page.screenshot(path=str(out / "05-inspector-return.png"))
    page.wait_for_timeout(400)
    context.close()
    browser.close()

videos = list(out.glob("*.webm"))
print("videos", [str(path) for path in videos])
