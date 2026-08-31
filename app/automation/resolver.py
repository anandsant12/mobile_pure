"""
Resolves a plain-English target description (e.g. "the login button", from
the up-front plan in planner.py) to an actual on-screen element, against a
FRESH read of the current screen every time it's called.

Three tiers, cheapest first:
1. Fuzzy text match (thefuzz) of the description against every element's
   rendered line in CURRENT SCREEN STATE - fast, free, no LLM call at all.
2. If that's ambiguous (best score below FUZZY_TARGET_THRESHOLD), ask the
   LLM once to pick the correct ref from the list - still text-only, no
   screenshot. This is what gives the resolver its accuracy: two elements
   with similar text but different resource-ids/positions get disambiguated
   by an LLM read of the full list, not a blind guess.
3. If neither finds it, fall back to vision (screenshot + coordinates),
   same ENABLE_VISION_FALLBACK kill switch as everywhere else.
"""

from thefuzz import fuzz

from app.llm.model_client import achat_json
from app.automation.locator_engine import resolve_by_ref, resolve_by_vision

FUZZY_TARGET_THRESHOLD = 70

RESOLVE_SYSTEM_PROMPT = """You are matching a plain-English target
description to one specific element from a list of UI elements currently
on a mobile screen. Respond with ONLY JSON, no reasoning, no <think> tags,
no prose: {"ref": "E3" or null, "reasoning": "short reason"}
Pick the single best-matching ref. If several elements have similar text,
prefer the one whose role/class fits the description (e.g. an EditText for
a "field", a Button for a "button"). If genuinely nothing matches, set ref
to null - do not guess.
"""


def _line_for_ref(state_text: str, ref: str) -> str:
    marker = f"[{ref}]"
    for line in state_text.splitlines():
        if line.strip().startswith(marker):
            return line
    return ""


def _fuzzy_best_ref(description: str, state_text: str, ref_map: dict):
    best_ref, best_score = None, 0
    for ref in ref_map:
        line = _line_for_ref(state_text, ref)
        score = fuzz.token_set_ratio(description.lower(), line.lower())
        if score > best_score:
            best_ref, best_score = ref, score
    return best_ref, best_score


async def aresolve_by_description(driver, description: str, state_text: str, ref_map: dict):
    """Returns a ResolvedTarget or None."""
    if not description:
        return None

    if ref_map:
        ref, score = _fuzzy_best_ref(description, state_text, ref_map)
        if ref and score >= FUZZY_TARGET_THRESHOLD:
            target = resolve_by_ref(ref, ref_map)
            if target:
                return target

        # Tier 2: ask the LLM to pick from the list - still no screenshot.
        try:
            result = await achat_json(
                RESOLVE_SYSTEM_PROMPT,
                f"Target description: {description}\n\nCURRENT SCREEN STATE:\n{state_text}\n\nWhich ref matches?",
            )
            picked_ref = result.get("ref")
            if picked_ref:
                target = resolve_by_ref(picked_ref, ref_map)
                if target:
                    return target
        except Exception:
            pass

    # Tier 3: vision fallback (returns None if disabled or not found).
    return await resolve_by_vision(driver, description)
