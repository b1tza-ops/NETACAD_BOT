import logging
import asyncio
import re
from playwright.async_api import Page, BrowserContext
from .quiz import handle_quiz_in_frame

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://www.netacad.com/dashboard"


async def navigate_all_courses(page: Page, context: BrowserContext) -> None:
    """Navigate to the dashboard, find enrolled courses, and process each."""
    logger.info("Navigating to dashboard...")
    await page.goto(DASHBOARD_URL, wait_until="load")

    # Wait for enrolled course buttons (SPA renders async)
    enrolled = []
    for _ in range(20):
        await asyncio.sleep(1)
        try:
            btns = page.locator('button[aria-label^="Resume"]')
            cnt = await btns.count()
            if cnt > 0:
                for i in range(cnt):
                    label = await btns.nth(i).get_attribute("aria-label") or ""
                    title = label.replace("Resume ", "").strip()
                    enrolled.append(title)
                break
        except Exception:
            pass

    if not enrolled:
        logger.warning("No enrolled courses found. Taking debug screenshot.")
        await page.screenshot(path="logs/dashboard_debug.png", full_page=True)
        return

    logger.info("Found %d enrolled course(s): %s", len(enrolled), enrolled)

    for i, title in enumerate(enrolled):
        logger.info("── Course %d/%d: %s", i + 1, len(enrolled), title)
        try:
            await _process_course(page, i, title)
        except Exception as e:
            logger.error("Error processing course '%s': %s", title, e)
            await page.screenshot(path=f"logs/error_course_{i}.png", full_page=True)

    logger.info("All courses processed.")


async def _scroll_content_frame(page: Page) -> None:
    """Scroll incrementally through the content iframe so the page is marked complete."""
    try:
        iframe = page.locator("iframe[src*='/content/']").first
        if await iframe.count() == 0:
            return
        frame = await iframe.content_frame()
        if not frame:
            return

        scroll_height = await frame.evaluate("document.body.scrollHeight")
        if scroll_height <= 0:
            return

        step = 400
        current = 0
        while current < scroll_height:
            current = min(current + step, scroll_height)
            await frame.evaluate(f"window.scrollTo(0, {current})")
            await asyncio.sleep(0.4)

        logger.debug("  Scrolled content iframe (height: %d)", scroll_height)
    except Exception as e:
        logger.debug("  Could not scroll content frame: %s", e)


async def _process_course(page: Page, btn_idx: int, title: str) -> None:
    """Click the Resume button for a course and linearly traverse all pages."""
    # Go back to dashboard and click the course
    await page.goto(DASHBOARD_URL, wait_until="load")
    for _ in range(15):
        await asyncio.sleep(1)
        try:
            btns = page.locator('button[aria-label^="Resume"]')
            if await btns.count() > btn_idx:
                break
        except Exception:
            pass

    btn = page.locator('button[aria-label^="Resume"]').nth(btn_idx)
    await btn.evaluate("el => el.click()")
    await page.wait_for_url(lambda url: "/launch" in url, timeout=20000)
    await asyncio.sleep(4)

    logger.info("  Opened: %s", page.url)

    m = re.search(r'id=([^&]+)', page.url)
    if not m:
        logger.warning("  Could not extract course id from URL: %s", page.url)
        return

    course_id = m.group(1)
    curriculum_url = f"https://www.netacad.com/launch?id={course_id}&tab=curriculum"

    async def _goto_curriculum_and_wait() -> int:
        """Navigate to the curriculum tab and poll until module headers appear. Returns count."""
        await page.goto(curriculum_url, wait_until="domcontentloaded")
        for _ in range(20):
            await asyncio.sleep(1)
            try:
                cnt = await page.locator('[class*="nodeInfoContainer"]').count()
                if cnt > 0:
                    return cnt
            except Exception:
                # SPA triggered a secondary navigation — wait for it to settle then retry
                try:
                    await page.wait_for_load_state("load", timeout=5000)
                except Exception:
                    pass
        return 0

    hcnt = await _goto_curriculum_and_wait()
    if hcnt == 0:
        logger.warning("  No module headers found — taking debug screenshot")
        await page.screenshot(path=f"logs/no_modules_{course_id}.png", full_page=True)
        return

    logger.info("  Found %d module(s) in sidebar", hcnt)

    visited = set()
    page_num = 0
    max_pages = 500

    for hi in range(hcnt):
        # Return to curriculum and wait for sidebar to fully render
        current_hcnt = await _goto_curriculum_and_wait()
        if current_hcnt <= hi:
            logger.warning("  Module %d no longer in DOM (only %d found), stopping", hi, current_hcnt)
            break

        headers = page.locator('[class*="nodeInfoContainer"]')

        header_txt = ""
        try:
            header_txt = (await headers.nth(hi).inner_text()).strip()
            logger.info("  ── Module %d/%d: %s", hi + 1, hcnt, header_txt[:60])
            await headers.nth(hi).evaluate("el => el.click()")
            await asyncio.sleep(3)
        except Exception as e:
            logger.warning("  Could not click module %d: %s", hi, e)
            continue

        # Check this module has navigable content
        nxt = page.locator('[class*="moduleNavBtn"][class*="next"]').first
        if await nxt.count() == 0:
            logger.info("  Module has no next button — skipping")
            continue

        # Traverse all pages within this module
        for _ in range(max_pages):
            current_url = page.url
            if current_url in visited:
                nxt = page.locator('[class*="moduleNavBtn"][class*="next"]').first
                if await nxt.count() == 0:
                    break
                aria = await nxt.get_attribute("aria-label") or ""
                if not aria:
                    break
                await nxt.evaluate("el => el.click()")
                await asyncio.sleep(2)
                if page.url == current_url:
                    break
                continue

            visited.add(current_url)
            page_num += 1
            logger.debug("    Page %d: %s", page_num, current_url[-60:])

            # Scroll through content to mark page as complete
            await _scroll_content_frame(page)
            await asyncio.sleep(1)

            # Attempt any quiz on this page
            try:
                await handle_quiz_in_frame(page)
            except Exception as e:
                logger.warning("    Quiz handling error on page %d: %s", page_num, e)

            # Advance to next page
            nxt = page.locator('[class*="moduleNavBtn"][class*="next"]').first
            if await nxt.count() == 0:
                logger.info("    End of module content after %d page(s)", page_num)
                break
            aria = await nxt.get_attribute("aria-label") or ""
            if not aria:
                break
            # Stop before final exams — do not attempt them
            if any(kw in aria.lower() for kw in ["final exam", "final assessment", "final quiz"]):
                logger.info("    Skipping final: %s", aria)
                break

            await nxt.evaluate("el => el.click()")
            await asyncio.sleep(2)

    logger.info("  Finished course '%s' — %d total page(s) processed", title, page_num)
