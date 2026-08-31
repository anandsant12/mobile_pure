"""
Turns the current Android screen into a short, LLM-friendly list of
interactive elements, instead of dumping the entire UI hierarchy XML.

Each element gets a short ref tag like [E3] PLUS enough metadata for a
human (or an LLM) to tell it apart from other elements with the same
label - resource-id, class, checkable/checked state, enabled state, and
its on-screen position - so the fuzzy/LLM resolver in resolver.py can pick
the RIGHT one even when several elements share similar text.

Note: unlike a web DOM, only elements CURRENTLY ON SCREEN appear here -
callers are expected to scroll and re-read state if what they need isn't
listed (see planner.py / resolver.py for how that's handled).
"""

import re
from selenium.webdriver.common.by import By

ANDROID_INTERACTIVE_XPATH = (
    "//*[@clickable='true' or @long-clickable='true' or @checkable='true' or "
    "contains(@class,'EditText') or contains(@class,'Button') or contains(@class,'Spinner') or "
    "contains(@class,'CheckBox') or contains(@class,'RadioButton') or contains(@class,'Switch')]"
)

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _short_class(cls: str) -> str:
    """'android.widget.EditText' -> 'EditText' - keeps state text compact."""
    return cls.rsplit(".", 1)[-1] if cls else ""


def _center_from_bounds(bounds: str):
    m = _BOUNDS_RE.match(bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(v) for v in m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def _describe_android_element(el) -> str | None:
    try:
        text = (el.get_attribute("text") or "").strip()[:60]
        desc = (el.get_attribute("content-desc") or "").strip()[:60]
        resource_id = el.get_attribute("resource-id") or ""
        # Short resource-id (drop the package prefix) reads better and is
        # still enough to disambiguate - e.g. "com.sbi.lotusintouch:id/etUser" -> "etUser"
        short_rid = resource_id.rsplit("/", 1)[-1] if resource_id else ""
        cls = _short_class(el.get_attribute("className") or "")
        checkable = (el.get_attribute("checkable") == "true")
        checked = (el.get_attribute("checked") == "true")
        enabled = el.get_attribute("enabled")
        bounds = el.get_attribute("bounds") or ""
        center = _center_from_bounds(bounds)

        label = text or desc or short_rid
        if not label:
            return None

        bits = []
        if short_rid and short_rid != label:
            bits.append(f"id='{short_rid}'")
        if checkable:
            bits.append(f"checkable checked={checked}")
        if enabled == "false":
            bits.append("disabled")
        if center:
            bits.append(f"pos=({center[0]},{center[1]})")
        extra = (" " + " ".join(bits)) if bits else ""

        return f"<{cls}>{label}</{cls}>{extra}"
    except Exception:
        return None


def _screen_header(driver) -> str:
    """Best-effort package/activity header so the resolver/verifier can
    confirm which screen/app is actually on screen right now. Never raises -
    not all Appium sessions expose these the same way."""
    pkg = activity = ""
    try:
        pkg = driver.current_package
    except Exception:
        pass
    try:
        activity = driver.current_activity
    except Exception:
        pass
    if not pkg and not activity:
        return ""
    return f"Package: {pkg}  Activity: {activity}\n"


def get_state(driver, max_elements: int = 60):
    """Returns (state_text, ref_map) where ref_map maps 'E0','E1',... -> element."""
    try:
        elements = driver.find_elements(By.XPATH, ANDROID_INTERACTIVE_XPATH)
    except Exception:
        elements = []

    ref_map = {}
    lines = []
    idx = 0
    for el in elements:
        desc = _describe_android_element(el)
        if not desc:
            continue
        ref = f"E{idx}"
        ref_map[ref] = el
        lines.append(f"[{ref}] {desc}")
        idx += 1
        if idx >= max_elements:
            break

    state_text = (
        f"{_screen_header(driver)}"
        f"Interactive elements (only what's currently on screen - scroll if you "
        f"expect more):\n" + "\n".join(lines)
    )
    return state_text, ref_map
