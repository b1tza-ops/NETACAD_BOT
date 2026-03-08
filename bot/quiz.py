import logging
import asyncio
import random
import os
from playwright.async_api import Page
from .ai import get_answer

logger = logging.getLogger(__name__)

FINAL_KEYWORDS = ["final exam", "final assessment", "final quiz", "course final", "final test"]


def _is_final(text: str) -> bool:
    return any(kw in text.lower() for kw in FINAL_KEYWORDS)


async def _human_delay() -> None:
    delay_min = float(os.getenv("DELAY_MIN", "1.0"))
    delay_max = float(os.getenv("DELAY_MAX", "3.0"))
    await asyncio.sleep(random.uniform(delay_min, delay_max))


async def handle_quiz_in_frame(page: Page) -> bool:
    """
    Detect and answer a quiz inside the Netacad content iframe.
    Returns True if a quiz was found and answered.
    """
    # Wait for iframe to exist
    cf = page.frame_locator("iframe[src*='/content/']").first
    try:
        quiz_widget = cf.locator('[class*="secure-one-question__widget"]')
        qcnt = await quiz_widget.count()
    except Exception:
        return False

    if qcnt == 0:
        return False

    # Check for final assessment
    try:
        widget_text = (await quiz_widget.inner_text()).strip()
        if _is_final(widget_text):
            logger.info("    Skipping final assessment quiz")
            return False
    except Exception:
        pass

    # Try to start the quiz if on intro screen
    await _try_start_quiz(cf)

    # Check if quiz is now showing a question (not the intro screen)
    try:
        html = await quiz_widget.inner_html()
        if 'intro-screen' in html:
            logger.warning("    Quiz could not be started (still on intro screen)")
            return False
    except Exception:
        return False

    # Answer all questions
    answered = 0
    max_questions = 60
    for _ in range(max_questions):
        result = await _answer_one_question(cf)
        if result == "done":
            logger.info("    Quiz complete. Answered %d question(s)", answered)
            break
        elif result == "answered":
            answered += 1
        elif result == "no_question":
            await asyncio.sleep(1)
            # Retry once
            result2 = await _answer_one_question(cf)
            if result2 != "answered":
                break
            answered += 1

    return answered > 0


async def _try_start_quiz(cf) -> None:
    """Click Start button if present."""
    start_btn = cf.locator('.start-button')
    try:
        if await start_btn.count() == 0:
            return
        logger.info("    Starting quiz...")
        await start_btn.scroll_into_view_if_needed()
        await asyncio.sleep(0.5)
        # Try standard click first
        await start_btn.click()
        await asyncio.sleep(2)
        # If still on intro, try JS event dispatch
        html = await cf.locator('[class*="secure-one-question"]').inner_html()
        if 'intro-screen' in html:
            await start_btn.evaluate("""
                el => {
                    ['pointerdown','pointerup','mousedown','mouseup','click'].forEach(ev =>
                        el.dispatchEvent(new PointerEvent(ev, {bubbles:true, cancelable:true, view:window}))
                    );
                }
            """)
            await asyncio.sleep(2)
    except Exception as e:
        logger.warning("    Start button error: %s", e)


async def _answer_one_question(cf) -> str:
    """
    Detect and answer one question.
    Returns: 'answered', 'done', or 'no_question'
    """
    # Check if quiz is complete
    try:
        results = cf.locator('[class*="results-screen"], [class*="score-screen"]')
        if await results.count() > 0:
            txt = (await results.first.inner_text()).strip()
            logger.info("    Quiz result: %s", txt[:80])
            return "done"
    except Exception:
        pass

    # Try to detect the question type and text
    # For secure-one-question quizzes, the question is shown in the widget
    # We try several specific selectors

    question_text, options_data, q_type = await _detect_question(cf)

    if not question_text:
        return "no_question"

    logger.info("    Q (%s): %s", q_type, question_text[:100])

    if not options_data:
        logger.warning("    No options found")
        return "no_question"

    option_texts = [o["text"] for o in options_data]
    logger.info("    Options: %s", [t[:40] for t in option_texts])

    correct_indices = get_answer(question_text, option_texts)
    logger.info("    AI selected: %s", [option_texts[i][:40] for i in correct_indices if i < len(option_texts)])

    # Click correct options
    for idx in correct_indices:
        if idx >= len(options_data):
            continue
        opt = options_data[idx]
        try:
            await _human_delay()
            locator = cf.locator(opt["selector"])
            await locator.scroll_into_view_if_needed()
            await locator.click()
        except Exception as e:
            logger.warning("    Could not click option %d: %s", idx, str(e)[:80])

    # Submit
    await _submit_answer(cf)
    await asyncio.sleep(1.5)
    return "answered"


async def _detect_question(cf) -> tuple[str, list[dict], str]:
    """
    Detect question text, options, and type from the quiz widget.
    Returns (question_text, options_data, question_type)
    """
    question_text = ""
    options_data = []
    q_type = "unknown"

    # ── Strategy 1: Radio button question (multiple choice) ──
    radios = cf.locator('input[type="radio"]')
    radio_cnt = await radios.count()
    if radio_cnt > 0:
        q_type = "radio"
        # Get question text from the question stem (not the widget intro)
        question_text = await _get_question_text(cf)
        if question_text:
            for i in range(radio_cnt):
                radio = radios.nth(i)
                inp_id = await radio.get_attribute("id") or ""
                label_text = ""
                if inp_id:
                    label = cf.locator(f"label[for='{inp_id}']")
                    if await label.count() > 0:
                        label_text = (await label.first.inner_text()).strip()
                if not label_text:
                    try:
                        label_text = await radio.evaluate(
                            "el => el.closest('label')?.innerText || el.parentElement?.innerText || ''"
                        )
                        label_text = label_text.strip()
                    except Exception:
                        pass
                options_data.append({
                    "text": label_text or f"Option {i + 1}",
                    "selector": f"input[type='radio']:nth-of-type({i + 1})",
                })
        return question_text, options_data, q_type

    # ── Strategy 2: Object matching / drag-drop question ──
    match_items = cf.locator('button.base.objectMatching-option-item')
    match_cnt = await match_items.count()
    if match_cnt > 0:
        q_type = "matching"
        question_text = await _get_question_text(cf)
        if question_text:
            for i in range(match_cnt):
                item = match_items.nth(i)
                txt = (await item.inner_text()).strip()
                data_id = await item.get_attribute("data-id") or str(i)
                options_data.append({
                    "text": txt or f"Item {i + 1}",
                    "selector": f"button.base.objectMatching-option-item:nth-of-type({i + 1})",
                })
        return question_text, options_data, q_type

    # ── Strategy 3: Generic button options ──
    for sel in ['[class*="answer-option"]', '[class*="choice"]', '[role="radio"]', '[role="option"]']:
        choices = cf.locator(sel)
        cnt = await choices.count()
        if cnt >= 2:
            q_type = "button-choice"
            question_text = await _get_question_text(cf)
            if question_text:
                for i in range(cnt):
                    txt = (await choices.nth(i).inner_text()).strip()
                    options_data.append({
                        "text": txt or f"Option {i + 1}",
                        "selector": f"{sel}:nth-of-type({i + 1})",
                    })
            return question_text, options_data, q_type

    return question_text, options_data, q_type


async def _get_question_text(cf) -> str:
    """Extract the question stem text from the current question screen."""
    # These selectors target the question text specifically (not the widget intro)
    selectors = [
        '.question-text',
        '.question-stem',
        '.stem',
        '.question-body',
        '[class*="questionText"]',
        '[class*="question-text"]',
        '[class*="questionStem"]',
        'p.question',
        'h2.question',
        # Fallback: any prominent text block that's NOT the widget title
        '[class*="question"]:not([class*="widget"]):not([class*="count"]):not([class*="screen"])',
    ]
    for sel in selectors:
        el = cf.locator(sel).first
        try:
            if await el.count() > 0:
                txt = (await el.inner_text()).strip()
                # Skip if it looks like the intro text
                if txt and not any(kw in txt.lower() for kw in ['instructions:', 'exam consists', 'attempts to pass', 'time limit']):
                    if len(txt) > 5:
                        return txt
        except Exception:
            pass
    return ""


async def _submit_answer(cf) -> None:
    """Click Submit / Check / Next button after selecting an answer."""
    for sel in [
        "button:has-text('Submit')",
        "button:has-text('Check Answer')",
        "button:has-text('Check')",
        "button:has-text('Next')",
        '[class*="submit"]',
        '[class*="check-answer"]',
    ]:
        btn = cf.locator(sel).first
        try:
            if await btn.count() > 0 and await btn.is_visible() and await btn.is_enabled():
                await _human_delay()
                await btn.click()
                await asyncio.sleep(1)
                return
        except Exception:
            pass
