"""
Turns a resolved action into a real Appium/UiAutomator2 interaction. Covers
the full vocabulary planner.py can choose from: click, type, select
(spinner/dropdown), toggle, scroll, press_back, close_app.

Coordinate-based actions (the vision fallback path, target.method=="vision")
use UiAutomator2's "mobile:" gesture commands rather than Selenium
ActionChains - ActionChains.move_by_offset is a web/desktop-mouse concept
and does not reliably drive a touch screen through Appium.
"""

import time

from thefuzz import fuzz

from app.automation.locator_engine import ResolvedTarget


def execute_click(driver, target: ResolvedTarget):
    if target.method == "ref":
        target.element.click()
    else:
        driver.execute_script("mobile: clickGesture", {"x": target.x_px, "y": target.y_px})


def execute_type(driver, target: ResolvedTarget, text: str):
    if target.method == "ref":
        try:
            target.element.clear()
        except Exception:
            pass
        target.element.send_keys(text)
    else:
        driver.execute_script("mobile: clickGesture", {"x": target.x_px, "y": target.y_px})
        active = driver.switch_to.active_element
        try:
            active.clear()
        except Exception:
            pass
        active.send_keys(text)


def execute_toggle(driver, target: ResolvedTarget):
    """Check/uncheck a checkbox/switch, or pick a radio button. Same
    mechanics as a click - kept as a separate name purely for clearer logs."""
    execute_click(driver, target)


def execute_select(driver, target: ResolvedTarget, value: str):
    """Android has no native <select> - dropdowns/spinners open a picker
    when tapped. So: tap to open it, re-read the screen, then fuzzy-match
    the requested option's text among the newly-visible elements and tap
    that. Requires a real element (not a vision-coordinate target)."""
    if target.method != "ref":
        raise RuntimeError(
            "Selecting a dropdown option needs a real element reference, "
            "not a screenshot coordinate - could not resolve the dropdown itself."
        )

    from app.automation.page_state import get_state  # local import: avoids a cycle

    target.element.click()
    time.sleep(0.6)

    state_text, ref_map = get_state(driver)
    best_ref, best_score = None, 0
    for ref, el in ref_map.items():
        marker = f"[{ref}]"
        line = next((ln for ln in state_text.splitlines() if ln.strip().startswith(marker)), "")
        score = fuzz.token_set_ratio(value.lower(), line.lower())
        if score > best_score:
            best_ref, best_score = ref, score

    if best_ref and best_score >= 60:
        ref_map[best_ref].click()
        return

    raise RuntimeError(f"Could not find an option matching '{value}' after opening the dropdown.")


def execute_scroll(driver, direction: str):
    size = driver.get_window_size()
    width, height = size["width"], size["height"]
    args = {
        "left": int(width * 0.1),
        "top": int(height * 0.1),
        "width": int(width * 0.8),
        "height": int(height * 0.8),
        "direction": direction,
        "percent": 0.75,
    }
    driver.execute_script("mobile: swipeGesture", args)


def execute_press_back(driver):
    driver.back()


def execute_close_app(driver, package: str):
    if package:
        driver.terminate_app(package)
    else:
        driver.quit()
