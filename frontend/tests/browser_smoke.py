"""Optional real-browser checks. Start Streamlit on port 8511 first.

Requires the playwright Python package and an installed Chrome browser.
Screenshots go to the OS temporary directory, never to benchmark folders.
"""
import os
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    errors = []
    with sync_playwright() as p:
        chrome = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))/"Google/Chrome/Application/chrome.exe"
        browser = p.chromium.launch(executable_path=str(chrome), headless=True, args=["--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1536, "height": 1050})
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto("http://127.0.0.1:8511")
        assert response.status == 200
        headings = {
            "Comparison dashboard": "Evidence before improvement.",
            "Our experimental results": "Every experiment, in context.",
            "Original paper results": "The reference benchmark.",
            "Algorithms explained": "Inside the optimization engine.",
            "3D delivery studio": "Watch the delivery system move.",
        }
        for name, heading in headings.items():
            page.get_by_test_id("stSidebar").get_by_text(name, exact=True).click()
            page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=60000)
            if name in ("Comparison dashboard", "Our experimental results", "Original paper results"):
                page.locator(".js-plotly-plot").first.wait_for(timeout=60000)
            assert page.locator('[data-testid="stException"]').count() == 0, name
            print("BROWSER PAGE OK:", name)
        frame = page.frame_locator('iframe').first
        frame.locator(".js-plotly-plot").wait_for(timeout=60000)
        frame.get_by_role("button", name="Play", exact=True).click()
        frame.locator("#timeline").evaluate("el=>new Promise(resolve=>{const poll=()=>Number(el.value)>0?resolve():setTimeout(poll,50);poll();})")
        frame.get_by_role("button", name="Pause", exact=True).click()
        frame.get_by_role("button", name="Restart", exact=True).click()
        frame.locator("#timeline").evaluate("el=>new Promise(resolve=>{const poll=()=>Number(el.value)===0?resolve():setTimeout(poll,50);poll();})")
        print("BROWSER PLAY/PAUSE/RESTART OK")
        screenshot = Path(tempfile.gettempdir())/"mfstsp-studio.png"
        page.screenshot(path=str(screenshot), full_page=True)
        page.get_by_text("Algorithm execution", exact=True).click()
        page.get_by_text("Real optimization-step playback is unavailable.", exact=False).wait_for()
        print("BROWSER TRACE LIMITATION OK")
        page.get_by_test_id("stSidebar").hover()
        page.get_by_test_id("stSidebarCollapseButton").get_by_role("button").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("heading", name="Watch the delivery system move.", exact=True).wait_for()
        page.screenshot(path=str(Path(tempfile.gettempdir())/"mfstsp-mobile.png"), full_page=True)
        assert not errors, errors
        print("BROWSER JS ERRORS:", errors)
        print("SCREENSHOT:", screenshot)
        browser.close()


if __name__ == "__main__":
    main()
