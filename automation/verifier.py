"""
Hybrid verification.

Step 1 (cheap, deterministic, always runs, no LLM): fuzzy string match
(thefuzz) between the "expected_outcome" the planner gave us and BOTH
(a) the screen's visible text, and (b) the actual current text/values held
in EditText fields, pulled straight from the UI hierarchy.

(b) matters: a typed value never reliably appears via a generic "visible
text" read on Android, so reading EditText.text directly answers "does the
field contain X" with certainty and skips the LLM/vision call entirely.

Step 2 (only if the fuzzy score lands in a genuine grey zone, AND
settings.enable_vision_fallback is True): ask the vision model to look at
a screenshot and judge whether the expected result actually happened. If
vision fallback is disabled, a grey-zone score is treated as a fail rather
than guessed at - the UI hierarchy is the source of truth.
"""

import asyncio
from thefuzz import fuzz
from selenium.webdriver.common.by import By

from app.llm.model_client import achat_vision_json
from app.utils.screenshot import take_screenshot, screenshot_to_b64
from config import settings

VERIFY_SYSTEM_PROMPT = """You are verifying whether a mobile UI automation
step succeeded. You'll be given the expected result and a screenshot.
Respond with ONLY JSON, no reasoning, no <think> tags, no explanation
outside the JSON: {"passed": true|false, "reasoning": "short reason"}
"""

GREY_ZONE_LOW = 40


def _visible_text(driver) -> str:
    """All on-screen text, concatenated - the Android equivalent of a web
    page's rendered body text."""
    try:
        elements = driver.find_elements(By.XPATH, "//*[@text!='']")
        return " ".join((el.get_attribute("text") or "") for el in elements)
    except Exception:
        return ""


def _field_values(driver) -> str:
    parts = []
    try:
        for el in driver.find_elements(By.XPATH, "//*[contains(@class,'EditText')]"):
            try:
                val = el.get_attribute("text") or ""
                rid = el.get_attribute("resource-id") or ""
                if val:
                    parts.append(f"{rid}={val}")
            except Exception:
                continue
    except Exception:
        pass
    return "; ".join(parts)


def _combined_state_text(driver) -> str:
    return f"{_visible_text(driver)}\nField values: {_field_values(driver)}"


async def averify(driver, expected_result: str) -> dict:
    """Returns {"passed": bool, "method": "fuzzy"|"vision"|"skipped", "score": int|None, "reasoning": str}"""
    if not expected_result:
        return {"passed": True, "method": "skipped", "score": None, "reasoning": "No expectation given."}

    combined_text = await asyncio.to_thread(_combined_state_text, driver)
    score = fuzz.partial_ratio(expected_result.lower(), combined_text.lower())
    threshold = settings.fuzzy_match_threshold

    if score >= threshold:
        return {
            "passed": True,
            "method": "fuzzy",
            "score": score,
            "reasoning": f"Fuzzy match score {score} >= threshold {threshold} (screen text + field values).",
        }

    if score <= GREY_ZONE_LOW or not settings.enable_vision_fallback:
        return {
            "passed": False,
            "method": "fuzzy",
            "score": score,
            "reasoning": f"Fuzzy match score {score} below threshold {threshold} (screen text + field values).",
        }

    # Grey zone AND vision fallback enabled: ask the vision model to judge.
    screenshot_path = await asyncio.to_thread(take_screenshot, driver, "verify")
    b64 = await asyncio.to_thread(screenshot_to_b64, screenshot_path)
    result = await achat_vision_json(
        VERIFY_SYSTEM_PROMPT,
        f"Expected result: {expected_result}\nDid this happen?",
        b64,
    )
    return {
        "passed": bool(result.get("passed")),
        "method": "vision",
        "score": score,
        "reasoning": result.get("reasoning", ""),
    }
