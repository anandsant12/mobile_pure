"""
Hybrid element resolution.

Path 1 (preferred, fast, reliable, no LLM vision call at all): a real
element from page_state.get_state()'s ref_map - a plain dict lookup, done.

Path 2 (fallback, slower, only used when the ref can't be resolved AND
settings.enable_vision_fallback is True): take a screenshot, ask the vision
model for normalized (0-1) coordinates, convert to real device pixels, and
tap/type by coordinate via an Appium gesture (see action_executor.py).
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

from app.llm.model_client import achat_vision_json
from app.utils.screenshot import take_screenshot, screenshot_to_b64
from config import settings

VISION_SYSTEM_PROMPT = """You are looking at a screenshot of a mobile app
screen. Find the single UI element described by the user and return ONLY
JSON, no reasoning, no <think> tags, no explanation outside the JSON:
{"found": true|false, "x": 0.0-1.0, "y": 0.0-1.0, "reasoning": "short reason"}
x and y are the NORMALIZED center coordinates of the element (0,0 = top-left,
1,1 = bottom-right). If you cannot find it, set found=false and x/y to 0.
"""


@dataclass
class ResolvedTarget:
    method: str  # "ref" or "vision"
    element = None
    x_px: Optional[int] = None
    y_px: Optional[int] = None


def resolve_by_ref(ref: str, ref_map: dict) -> Optional[ResolvedTarget]:
    el = ref_map.get(ref)
    if el is None:
        return None
    target = ResolvedTarget(method="ref")
    target.element = el
    return target


async def resolve_by_vision(driver, description: str) -> Optional[ResolvedTarget]:
    if not settings.enable_vision_fallback:
        return None

    screenshot_path = await asyncio.to_thread(take_screenshot, driver, "locator_fallback")
    b64 = await asyncio.to_thread(screenshot_to_b64, screenshot_path)
    size = await asyncio.to_thread(driver.get_window_size)
    width, height = size["width"], size["height"]

    result = await achat_vision_json(
        VISION_SYSTEM_PROMPT,
        f"Find this element: {description}",
        b64,
    )

    if not result.get("found"):
        return None

    x_px = int(float(result["x"]) * width)
    y_px = int(float(result["y"]) * height)
    return ResolvedTarget(method="vision", x_px=x_px, y_px=y_px)


async def aresolve_target(driver, ref: Optional[str], ref_map: dict, description: str) -> Optional[ResolvedTarget]:
    """Fast path first (no LLM call). Only calls vision if that fails AND vision fallback is enabled."""
    if ref:
        target = resolve_by_ref(ref, ref_map)
        if target:
            return target
    return await resolve_by_vision(driver, description)
