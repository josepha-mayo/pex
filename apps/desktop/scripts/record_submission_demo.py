"""Capture local UI reference frames; this is not live-integration or submission proof."""

import re
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Playwright is optional and is not installed by PEX. Install it explicitly "
        "before capturing local UI reference frames."
    ) from exc

out = Path(__file__).resolve().parents[3] / "docs" / "demo" / "ui-reference"
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
    page.screenshot(path=str(out / "01-compact.png"))
    page.get_by_role("button", name="Inspect what PEX knows").click()
    page.wait_for_timeout(400)
    page.screenshot(path=str(out / "02-inspector.png"))
    page.get_by_role("button", name="Open command deck").click()
    page.wait_for_timeout(400)
    for index, view in enumerate(
        ["Now", "Decisions", "Context", "Interventions", "Agents", "Bench"],
        start=3,
    ):
        page.get_by_role("button", name=re.compile(rf"^{view}\b")).click()
        page.wait_for_timeout(250)
        page.screenshot(path=str(out / f"{index:02d}-deck-{view.lower()}.png"))
    page.get_by_role("button", name="Settings").click()
    page.wait_for_timeout(400)
    page.screenshot(path=str(out / "09-settings.png"))
    context.close()
    browser.close()

videos = list(out.glob("*.webm"))
print("UI reference only; do not present as live PEX evidence.")
print("videos", [str(path) for path in videos])
