import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Set up logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log"),
    ],
)
logger = logging.getLogger(__name__)


async def main():
    from bot.browser import create_browser
    from bot.auth import login
    from bot.navigator import navigate_all_courses

    logger.info("Starting Netacad Bot")

    async with create_browser() as (browser, context, page):
        try:
            await login(page)
            await navigate_all_courses(page, context)
        except Exception as e:
            logger.error("Fatal error: %s", e)
            await page.screenshot(path="logs/fatal_error.png", full_page=True)
            raise

    logger.info("Bot finished.")


if __name__ == "__main__":
    asyncio.run(main())
