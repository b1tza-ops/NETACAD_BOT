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

### Key design notes

- All Playwright interactions use `.evaluate("el => el.click()")` for JS-triggered elements that don't respond to native clicks.
- The navigator caps traversal at 500 pages per course and uses a `visited` URL set to detect cycles.
- `_human_delay()` in `quiz.py` reads `DELAY_MIN`/`DELAY_MAX` from the environment on each call.
- Debug screenshots are saved to `logs/` on any fatal error or login failure.
