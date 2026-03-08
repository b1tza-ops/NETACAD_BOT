import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_answer(question: str, options: list[str]) -> list[int]:
    """
    Ask OpenAI which option(s) are correct.
    Returns a list of 0-based indices of correct answers.
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    numbered = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(options))

    prompt = (
        f"You are a Cisco networking and IT expert.\n\n"
        f"Question: {question}\n\n"
        f"Options:\n{numbered}\n\n"
        f"Which option(s) is correct? Reply with ONLY the number(s) of the correct answer(s), "
        f"separated by commas if there are multiple (e.g. '2' or '1,3'). "
        f"No explanation."
    )

    logger.debug("Sending question to OpenAI: %s", question[:100])

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=20,
    )

    raw = response.choices[0].message.content.strip()
    logger.debug("OpenAI raw response: %s", raw)

    indices = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1  # convert to 0-based
            if 0 <= idx < len(options):
                indices.append(idx)

    if not indices:
        logger.warning("Could not parse AI response '%s', defaulting to option 1", raw)
        indices = [0]

    return indices
