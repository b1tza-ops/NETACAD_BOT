# NETACAD Bot

An automation bot that logs into [netacad.com](https://www.netacad.com), scrolls through all course modules to mark them complete, and automatically answers quizzes using OpenAI.

---

## What it does

1. Logs into your Netacad account
2. Finds all enrolled courses on your dashboard
3. For each course, clicks through every module page and scrolls through the content (marking it complete)
4. Detects any quiz on each page and answers it using OpenAI
5. Skips final exams

---

## Requirements

- Python 3.11+
- A Netacad account with enrolled courses
- An OpenAI API key

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/b1tza-ops/NETACAD_BOT.git
cd NETACAD_BOT
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install the Chromium browser (first time only)

```bash
playwright install chromium
```

### 4. Configure your credentials

Copy the example env file and fill in your details:

```bash
cp .env.example .env
```

Open `.env` and set your values:

```env
# Your Netacad login
NETACAD_EMAIL=your@email.com
NETACAD_PASSWORD=yourpassword

# Your OpenAI API key
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o        # or gpt-3.5-turbo for cheaper usage

# Bot behaviour
HEADLESS=false             # Set to true to hide the browser window
DELAY_MIN=1.0              # Minimum seconds between actions (human-like pacing)
DELAY_MAX=3.0              # Maximum seconds between actions
```

---

## Running the bot

```bash
source venv/bin/activate
python main.py
```

The bot will open a browser window (unless `HEADLESS=true`), log in, and start working through your courses automatically.

Logs are saved to the `logs/` folder. If something goes wrong, a screenshot is saved there automatically.

---

## Configuration tips

| Setting | Recommendation |
|---|---|
| `HEADLESS=false` | Keep visible while testing so you can see what's happening |
| `HEADLESS=true` | Use on a server / unattended run |
| `OPENAI_MODEL=gpt-4o` | Most accurate for networking questions |
| `OPENAI_MODEL=gpt-3.5-turbo` | Faster and cheaper, slightly less accurate |
| `DELAY_MIN` / `DELAY_MAX` | Keep at 1–3s to avoid being flagged as a bot |

---

## Troubleshooting

**Bot can't find modules**
- Check `logs/no_modules_<id>.png` — the page may have been slow to load. Try running again.

**Login fails**
- Check `logs/login_failed.png` and verify your credentials in `.env`.

**Quiz not being answered**
- The bot logs every question and AI response to `logs/bot.log`. Check there for details.

**`playwright install` errors**
- Run `playwright install-deps chromium` to install system dependencies (Linux only).

---

## Disclaimer

This tool is for personal educational use only. Use it responsibly and in accordance with Netacad's terms of service.
