# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`netacad-bot` is a Python automation bot that logs into [netacad.com](https://www.netacad.com), iterates through all enrolled courses, and auto-answers quiz questions using the OpenAI API.

## Setup & Running

```bash
# Install dependencies (use the venv)
source venv/bin/activate
pip install -r requirements.txt

# Install Playwright browsers (first time only)
playwright install chromium

# Copy and fill in credentials
cp .env.example .env

# Run the bot
python main.py
```

## Environment Variables (`.env`)

| Variable | Description |
|---|---|
| `NETACAD_EMAIL` | Netacad account email |
| `NETACAD_PASSWORD` | Netacad account password |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Model to use (default: `gpt-4o`) |
| `HEADLESS` | `true` to run without visible browser (default: `false`) |
| `DELAY_MIN` / `DELAY_MAX` | Human-like delay range in seconds between actions |

## Architecture

The bot is a single-entrypoint async application with no test suite. All browser automation uses Playwright (`async_api`).

```
main.py              # Entry point: sets up logging, runs main()
bot/
  browser.py         # create_browser() context manager — launches Chromium with anti-detection settings
  auth.py            # login() — handles Netacad's two-step Keycloak SSO login
  navigator.py       # navigate_all_courses() — discovers enrolled courses, traverses all pages linearly
  quiz.py            # handle_quiz_in_frame() — detects and answers quizzes inside content iframes
  ai.py              # get_answer() — sends question + options to OpenAI, returns 0-based correct indices
logs/                # Created at runtime; contains bot.log and debug screenshots on errors
```

### Data flow

1. `main.py` → `browser.py`: Chromium launches with webdriver flag hidden and OneTrust cookie banner suppressed via `MutationObserver`.
2. `auth.py`: Two-step login (username page → password page) via Keycloak SSO. Saves a screenshot to `logs/login_failed.png` on failure.
3. `navigator.py`: Finds all `button[aria-label^="Resume"]` elements on the dashboard, then for each course clicks through every page using `[class*="moduleNavBtn"][class*="next"]`. Skips final exams/assessments by keyword matching on the nav button's `aria-label`.
4. `quiz.py`: On each page, looks for `iframe[src*='/content/']` and within it a `[class*="secure-one-question__widget"]`. Supports three question types: radio buttons, object matching (`button.base.objectMatching-option-item`), and generic button choices. Skips quizzes identified as final assessments.
5. `ai.py`: Formats the question and numbered options into a prompt and calls the OpenAI chat completions API with `temperature=0`. Parses the comma-separated number response into 0-based indices.

## Known Issues & What Needs Fixing

### 1. Module detection fails for some courses (Ethical Hacker)
The selector `[class*="nodeInfoContainer"]` does not match the sidebar items for the Ethical Hacker course — the page was still a loading spinner when the screenshot was taken, suggesting either:
- The course uses a different sidebar component/class entirely, or
- The course player is a completely different SPA (some Netacad courses use a legacy player)

**What to do:** Run the bot with `HEADLESS=false`, open the Ethical Hacker course manually, inspect the sidebar elements in DevTools, and find the correct selector. Then add it as a fallback alongside `[class*="nodeInfoContainer"]` in `navigator.py:_goto_curriculum_and_wait()` and the `headers` locator.

### 2. Quiz answering is untested end-to-end
The quiz flow (`bot/quiz.py`) was written based on Netacad's DOM structure but has not been confirmed to successfully answer and submit a question in a real session. The following need verification:
- **Start button**: `.start-button` may not be the correct selector — confirm with a real quiz page
- **Question text extraction**: `_get_question_text()` tries 9 selectors in order; log which one actually matches
- **Option clicking**: The `nth-of-type` CSS selectors built in `_detect_question()` may not target the right elements after scrolling; consider using `nth()` on the locator instead
- **Submit button**: `_submit_answer()` tries 6 selectors — add logging to confirm which one fires

### 3. SPA navigation timing is fragile
The current fix (catching "execution context destroyed" and waiting for `load`) works but is reactive. A more robust approach would be to:
- Use `page.wait_for_url()` to wait for the URL to stabilise after `goto` (the SPA always redirects to add `?view=<uuid>`)
- Then proceed with DOM queries

### 4. Module traversal re-navigates on every module (slow)
For each module, the bot navigates back to `curriculum_url`, waits for the sidebar to render (up to 20s), then clicks the module. With 49–51 modules per course this is very slow. Consider:
- Collecting all module click targets (e.g. `href` or a data attribute) before starting, then navigating directly to each one instead of going back to the curriculum page each time

### 5. No handling for already-completed pages
The bot re-processes pages it has already completed in previous runs. Consider storing visited course/page IDs in a local JSON file so the bot can skip them on re-runs.

---

### Key design notes

- All Playwright interactions use `.evaluate("el => el.click()")` for JS-triggered elements that don't respond to native clicks.
- The navigator caps traversal at 500 pages per course and uses a `visited` URL set to detect cycles.
- `_human_delay()` in `quiz.py` reads `DELAY_MIN`/`DELAY_MAX` from the environment on each call.
- Debug screenshots are saved to `logs/` on any fatal error or login failure.
