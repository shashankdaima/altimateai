from pathlib import Path
from playwright.sync_api import sync_playwright


def screenshot_url(
    url: str,
    output_path: str,
    *,
    full_page: bool = True,
    viewport: dict | None = None,
    wait_for: str | None = None,
) -> str:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=viewport or {"width": 1280, "height": 800})
        page.goto(url, wait_until="networkidle")
        if wait_for:
            page.wait_for_selector(wait_for)
        page.screenshot(path=str(p), full_page=full_page)
        browser.close()
    return str(p.resolve())


def screenshot_element(
    url: str,
    selector: str,
    output_path: str,
    *,
    viewport: dict | None = None,
) -> str:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=viewport or {"width": 1280, "height": 800})
        page.goto(url, wait_until="networkidle")
        element = page.locator(selector).first
        element.screenshot(path=str(p))
        browser.close()
    return str(p.resolve())


def screenshot_html(
    html: str,
    output_path: str,
    *,
    full_page: bool = True,
    viewport: dict | None = None,
) -> str:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=viewport or {"width": 1280, "height": 800})
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=str(p), full_page=full_page)
        browser.close()
    return str(p.resolve())


def screenshot_pdf(
    url: str,
    output_path: str,
    *,
    viewport: dict | None = None,
) -> str:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=viewport or {"width": 1280, "height": 800})
        page.goto(url, wait_until="networkidle")
        page.pdf(path=str(p))
        browser.close()
    return str(p.resolve())
