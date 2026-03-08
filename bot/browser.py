import os
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Page, BrowserContext


@asynccontextmanager
async def create_browser():
    headless = os.getenv("HEADLESS", "false").lower() == "true"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        # Hide webdriver flag + permanently suppress OneTrust cookie banner
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // Use MutationObserver to permanently remove OneTrust whenever it appears
            const _removeOT = () => {
                const el = document.getElementById('onetrust-consent-sdk');
                if (el) el.remove();
                // Also remove any dark filter overlay
                document.querySelectorAll('.onetrust-pc-dark-filter').forEach(e => e.remove());
            };
            _removeOT();
            const _observer = new MutationObserver(_removeOT);
            const _start = () => _observer.observe(document.body || document.documentElement, {childList: true, subtree: true});
            if (document.body) { _start(); } else { document.addEventListener('DOMContentLoaded', _start); }
        """)
        page = await context.new_page()
        try:
            yield browser, context, page
        finally:
            await browser.close()
