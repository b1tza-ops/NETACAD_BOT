import os
import logging
import asyncio
from playwright.async_api import Page

logger = logging.getLogger(__name__)

NETACAD_URL = "https://www.netacad.com"


async def login(page: Page) -> None:
    logger.info("Navigating to Netacad...")
    await page.goto(NETACAD_URL, wait_until="networkidle")
    await asyncio.sleep(2)

    email = os.getenv("NETACAD_EMAIL")
    password = os.getenv("NETACAD_PASSWORD")
    if not email or not password:
        raise ValueError("NETACAD_EMAIL and NETACAD_PASSWORD must be set in .env")

    # Dismiss OneTrust cookie banner via JS so it doesn't block clicks
    await page.evaluate("document.getElementById('onetrust-consent-sdk')?.remove()")
    await asyncio.sleep(0.5)
    logger.info("Dismissed cookie consent banner")

    # Trigger login via JS click (button has no href, uses JS handler)
    logger.info("Clicking Login button...")
    await page.locator("#netacad-login-button").evaluate("el => el.click()")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    # Step 1: Enter username on Keycloak SSO page
    logger.info("Entering email (step 1)...")
    username_field = page.locator("input[name='username']").first
    await username_field.wait_for(timeout=15000)
    await username_field.fill(email)
    await page.locator("input[type='submit']#kc-login").click()
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    # Step 2: Enter password
    logger.info("Entering password (step 2)...")
    password_field = page.locator("input[type='password'][name='password']").first
    await password_field.wait_for(timeout=15000)
    await password_field.fill(password)
    await page.locator("input[type='submit']#kc-login").click()
    # Wait for redirect away from auth domain (SPA dashboard may never reach networkidle)
    try:
        await page.wait_for_url(lambda url: "auth.netacad.com" not in url, timeout=30000)
    except Exception:
        pass
    await asyncio.sleep(3)

    # Verify login succeeded
    if "auth.netacad.com" in page.url or "login-actions" in page.url:
        await page.screenshot(path="logs/login_failed.png", full_page=True)
        raise RuntimeError("Login failed — still on auth page. Check your credentials.")

    logger.info("Logged in successfully. Current URL: %s", page.url)
