"""
Best-effort automatic popup/permission-dialog dismissal.

Called before every planned step (and right after the driver starts), so
the agent never has to reason about "close this popup first" - by the time
it looks at the screen, common popups are already gone. This is
intentionally NOT LLM-based: it's a fast, cheap, deterministic pass using
plain locators, so it never eats into the planned step budget or invents
extra "steps" of its own.
"""

from selenium.webdriver.common.by import By
from config import settings

DISMISS_LABELS = {
    "accept all", "accept", "agree", "i agree", "allow", "allow all",
    "allow while using app", "while using the app", "got it", "ok", "okay",
    "close", "dismiss", "no thanks", "not now", "continue", "×", "x",
    "i understand", "understood",
}

ANDROID_CANDIDATE_XPATH = "//*[@clickable='true']"


def _matches_dismiss_label(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in DISMISS_LABELS


def dismiss_popups(driver, max_dismissals: int = 3) -> int:
    """Try to close up to `max_dismissals` popups. Returns how many were closed.
    Never raises - a failed dismissal attempt should never break the run."""
    if not settings.popup_dismiss_enabled:
        return 0

    closed = 0
    try:
        # Android runtime-permission dialogs are OS-level, not part of the
        # app's own UI tree - try the alert-style dismissal first (harmless
        # if there's no alert; with ANDROID_AUTO_GRANT_PERMISSIONS=true these
        # mostly won't appear at all since the driver pre-grants permissions
        # at session start).
        try:
            driver.execute_script("mobile: acceptAlert")
            closed += 1
        except Exception:
            pass

        for _ in range(max_dismissals):
            try:
                candidates = driver.find_elements(By.XPATH, ANDROID_CANDIDATE_XPATH)
            except Exception:
                break

            clicked_this_pass = False
            for el in candidates:
                try:
                    label = el.get_attribute("text") or el.get_attribute("content-desc") or ""
                    if _matches_dismiss_label(label):
                        el.click()
                        closed += 1
                        clicked_this_pass = True
                        break
                except Exception:
                    continue

            if not clicked_this_pass:
                break
    except Exception:
        pass

    return closed
