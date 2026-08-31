"""
Orchestrates the whole run:
  1. Plan ONCE, up front: raw instructions -> ordered list of atomic
     actions (planner.aplan). This does not change once the run starts.
  2. Start the driver (this launches the app under test automatically).
  3. Dismiss popups.
  4. For each planned step, IN ORDER, and nothing else:
       - dismiss popups
       - read a fresh screen state
       - resolve the step's target description to a live element
       - execute the action
       - verify the expected outcome, if any
       - log the result
     If a step can't be resolved or fails to execute, the run STOPS rather
     than improvising an alternative action or trying to "recover" with
     steps nobody asked for - see planner.py's docstring for why.
  5. Quit the driver.

This intentionally does NOT re-ask the model "what should I do next?" after
every step. That reactive pattern is what let the agent wander off and keep
acting after the user's actual instructions were already satisfied. Here,
the plan is fixed before a single action is taken, and the run yields
exactly one log entry per planned step, then a final "finished" entry, then
stops for good.

Async so the LLM calls (network-bound) don't block; blocking Selenium/
Appium driver calls are pushed onto a thread via asyncio.to_thread so they
don't stall the event loop either.
"""

import asyncio

from app.automation.driver_manager import DriverManager
from app.automation.page_state import get_state
from app.automation.planner import PlannedStep
from app.automation.locator_engine import aresolve_target
from app.automation.resolver import aresolve_by_description
from app.automation.action_executor import (
    execute_click, execute_type, execute_select, execute_toggle,
    execute_scroll, execute_press_back, execute_close_app,
)
from app.automation.verifier import averify
from app.automation.popup_handler import dismiss_popups
from app.utils.screenshot import take_screenshot
from config import settings

NO_TARGET_ACTIONS = {"scroll", "wait", "press_back", "close_app"}


async def _resolve(driver, description: str):
    """Fresh screen read + tiered resolution (fuzzy -> LLM -> vision)."""
    state_text, ref_map = await asyncio.to_thread(get_state, driver)
    return await aresolve_by_description(driver, description, state_text, ref_map)


async def run_plan(planned_steps: list[PlannedStep]):
    """Async generator: yields a dict per planned step, e.g.
    {"step": 1, "action": {...}, "verification": {...}, "screenshot": Path, "status": "ok"}
    Executes the fixed plan exactly once, in order, and stops - it never
    re-plans or adds steps beyond what was given to it."""
    dm = DriverManager()
    driver = await asyncio.to_thread(dm.start)

    try:
        await asyncio.to_thread(dismiss_popups, driver)

        for step_num, step in enumerate(planned_steps, 1):
            await asyncio.to_thread(dismiss_popups, driver)

            log = {
                "step": step_num,
                "action": {
                    "action": step.action,
                    "target": step.target,
                    "value": step.value,
                    "expected_outcome": step.expected_outcome,
                },
                "verification": None,
                "screenshot": None,
                "status": "ok",
                "error": None,
            }

            try:
                if step.action == "click":
                    target = await _resolve(driver, step.target)
                    if target is None:
                        raise RuntimeError(f"Could not locate element for: {step.target}")
                    await asyncio.to_thread(execute_click, driver, target)

                elif step.action == "type":
                    target = await _resolve(driver, step.target)
                    if target is None:
                        raise RuntimeError(f"Could not locate element for: {step.target}")
                    await asyncio.to_thread(execute_type, driver, target, step.value or "")

                elif step.action == "select":
                    target = await _resolve(driver, step.target)
                    if target is None:
                        raise RuntimeError(f"Could not locate element for: {step.target}")
                    await asyncio.to_thread(execute_select, driver, target, step.value or "")

                elif step.action == "toggle":
                    target = await _resolve(driver, step.target)
                    if target is None:
                        raise RuntimeError(f"Could not locate element for: {step.target}")
                    await asyncio.to_thread(execute_toggle, driver, target)

                elif step.action == "scroll":
                    await asyncio.to_thread(execute_scroll, driver, step.value or "down")

                elif step.action == "press_back":
                    await asyncio.to_thread(execute_press_back, driver)

                elif step.action == "close_app":
                    await asyncio.to_thread(execute_close_app, driver, settings.android_app_package)

                elif step.action == "wait":
                    try:
                        seconds = float(step.value) if step.value else 2.0
                    except ValueError:
                        seconds = 2.0
                    await asyncio.sleep(seconds)

                elif step.action == "verify":
                    pass  # verification always happens below, using target/expected_outcome

                else:
                    raise RuntimeError(f"Unknown action type: {step.action}")

            except Exception as e:
                log["status"] = "error"
                log["error"] = str(e)
                log["screenshot"] = await asyncio.to_thread(take_screenshot, driver, f"step{step_num}_error")
                yield log
                # Stop the whole run on failure rather than guessing at a
                # recovery step - "only do what we told it to do" cuts both
                # ways: it shouldn't improvise fixes either.
                return

            expected = step.expected_outcome or (step.target if step.action == "verify" else "")
            if expected:
                verification = await averify(driver, expected)
                log["verification"] = verification
            log["screenshot"] = await asyncio.to_thread(take_screenshot, driver, f"step{step_num}")

            yield log

        yield {
            "step": len(planned_steps) + 1,
            "action": {"action": "finish"},
            "verification": None,
            "screenshot": None,
            "status": "finished",
            "error": None,
        }

    finally:
        await asyncio.to_thread(dm.quit)
