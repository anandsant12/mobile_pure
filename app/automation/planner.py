"""
Takes the raw plain-English steps the user wrote and turns them into an
ordered list of atomic mobile actions, each with a target description and
(where applicable) an expected outcome for the verifier to check.

This runs EXACTLY ONCE per run, up front - it does NOT re-plan step by
step. That is the deliberate fix for the "agent keeps doing things I never
asked for" problem: instead of asking the model "what's the single next
action?" after every screen change (which gives it room to invent extra
steps, retry loops, or wander), we ask it once for the FULL ordered plan,
then agent.py executes exactly that plan and nothing else. See
agent.py for the execution side.
"""

from dataclasses import dataclass
from typing import List, Optional

from app.llm.model_client import achat_json
from config import settings

SYSTEM_PROMPT = """You are a mobile test automation planner. You convert a
human-written, plain-English test case into a strict ordered list of atomic
actions that a mobile automation agent can execute one at a time, against a
native Android app.

CRITICAL CONTEXT - read this before planning:
- The target app is ALREADY RUNNING AND IN THE FOREGROUND before any planned
  step executes. The automation framework launches it automatically (via
  Appium, using the app package/activity configured outside of this
  conversation) BEFORE your plan ever starts running.
- Because of that: NEVER include a step to open, launch, navigate to, or
  select the app. If the input text says things like "open the app" or
  "launch the app" at the start, treat that as already done and do NOT
  create an action for it - start your plan with the first real on-screen
  interaction (e.g. entering a username, tapping a button that is already
  visible on the app's first screen).
- Do not invent steps that were not implied by the input. If a step is
  ambiguous, make the most reasonable assumption a QA engineer would make -
  but do not add extra verification, extra navigation, or "helpful" actions
  the user did not ask for, and do not continue automating anything past
  the last step implied by the input.

Each action must be ONE of:
- "click": tap a button/link/icon/checkbox-adjacent-label.
- "type": enter text into an input field. Requires "value" with the exact
  text to type.
- "select": choose an option from a dropdown/spinner. Requires "value" with
  the option's visible text.
- "toggle": check/uncheck a checkbox, switch, or radio button.
- "scroll": scroll the screen. Requires "value" = one of up/down/left/right.
  No "target" needed.
- "wait": pause for N seconds. ONLY use this when the input explicitly asks
  for a delay/pause (e.g. "wait 5 seconds", "close after 5 seconds").
  Requires "value" = the number of seconds. No "target" needed.
- "press_back": the Android hardware/system Back action (not an in-app Back
  button - use "click" for those). No "target" needed.
- "close_app": close/exit/terminate the app. Use when the input explicitly
  says to close, exit, or terminate the app. No "target" needed. If the
  input says to close AFTER some delay, emit a "wait" step first, then this.
- "verify": confirm something is true/visible without interacting with
  anything. "target" describes what should be true/visible. Only use this
  when the input explicitly asks to check/verify/confirm something.

Rules:
- "target" must describe the element the way a human would see it on screen
  (visible text, label, or role) - never resource-ids, XPath, or coordinates.
  Required for click/type/select/toggle/verify; must be null for
  scroll/wait/press_back/close_app.
- "value" holds: the exact text for "type", the option text for "select",
  the direction for "scroll", the number of seconds for "wait", and is null
  for every other action.
- Every action that changes screen state (click, type, select, toggle)
  SHOULD include "expected_outcome": a short description of what should be
  true after the action, if it's genuinely inferable from the input. Use
  null if there's nothing meaningfully checkable.
- Break compound instructions into separate atomic steps.

Respond ONLY with JSON in this exact shape, no markdown fences, no prose:
{
  "steps": [
    {
      "action": "type",
      "target": "username field",
      "value": "john.doe",
      "expected_outcome": "username field shows john.doe"
    }
  ]
}
"""


@dataclass
class PlannedStep:
    action: str
    target: Optional[str]
    value: Optional[str]
    expected_outcome: Optional[str]


VALID_ACTIONS = {
    "click", "type", "select", "toggle", "scroll",
    "wait", "press_back", "close_app", "verify",
}


async def aplan(raw_instructions: str) -> List[PlannedStep]:
    result = await achat_json(
        SYSTEM_PROMPT,
        f"Test steps (plain English):\n{raw_instructions}",
    )
    steps = []
    for s in result.get("steps", []):
        action = s.get("action")
        if action not in VALID_ACTIONS:
            continue
        steps.append(PlannedStep(
            action=action,
            target=s.get("target"),
            value=s.get("value"),
            expected_outcome=s.get("expected_outcome"),
        ))

    if len(steps) > settings.max_steps:
        steps = steps[: settings.max_steps]

    return steps
