# AI Mobile Automation (Android)

An AI-driven UI automation agent for native Android apps, built on Appium.
You describe what you want done in plain English; the agent turns that
into an exact, ordered plan, shows it to you, then executes it — nothing
more, nothing less.

This project is **mobile-only**. All web/Selenium-target code has been
removed.

## What changed in this version

**1. Plan-then-act, not react-and-guess.**
Previously the agent asked the model "what's the single next action?"
after every screen change. That reactive loop had no fixed endpoint, so it
could keep proposing actions you never asked for. Now the agent calls the
planner **exactly once**, up front: your instructions are converted into a
strict, ordered list of atomic actions (`planner.py`). The run then
executes precisely that list, in order, and stops — see `agent.py`. If a
step fails, the run stops rather than improvising a "fix."

**2. The agent never launches the app itself.**
Appium already launches the app (via `ANDROID_APP_PACKAGE` /
`ANDROID_APP_ACTIVITY` in `.env`) before any planned step runs. The
planner's system prompt now explicitly says the app is already open and
in the foreground, and instructs it to never create an "open/launch app"
step — even if your instructions start with "open the app."

**3. One LLM provider toggle drives both text and vision.**
`LLM_PROVIDER=groq` or `LLM_PROVIDER=azure` in `.env` — no more separate
text/vision toggles. On `azure`, the same deployment (point it at your
gpt-4.1-mini deployment) is used for both text and vision calls, since
gpt-4.1-mini is multimodal.

**4. Locator/action fixes.**
- The vision-fallback click/type path previously used Selenium
  `ActionChains.move_by_offset`, which is a desktop-mouse concept and
  doesn't reliably drive a touch screen through Appium. It now uses
  UiAutomator2's `mobile: clickGesture` / `mobile: swipeGesture` commands.
- Screen-state extraction (`page_state.py`) now includes each element's
  short resource-id, checked/enabled state, and on-screen position, so the
  fuzzy/LLM resolver can tell apart elements that share similar text.
- A `verify` action and Android-native `select` (tap-to-open-dropdown +
  fuzzy-match-and-tap the option) are supported directly.

**5. Dead/broken code removed.**
`step_runner.py` (a manual step-builder path that referenced functions
that didn't exist in `action_executor.py` and was never wired into the
Streamlit UI), `action_schema.py` (its unused, web/mobile-mixed schema),
and `app/llm/groq_client.py` (an unused duplicate of `model_client.py`)
have all been deleted.

## Architecture

```
streamlit_app.py
  -> planner.aplan(instructions)      # ONE call, produces the full plan
  -> agent.run_plan(planned_steps)    # executes that fixed plan, in order
       -> driver_manager.DriverManager   # starts Appium session (launches app)
       -> popup_handler.dismiss_popups   # clears permission/consent dialogs
       -> page_state.get_state           # fresh on-screen element list
       -> resolver.aresolve_by_description  # fuzzy -> LLM -> vision
       -> action_executor.execute_*       # the actual tap/type/scroll/etc.
       -> verifier.averify                # fuzzy text/field match -> vision
```

`app/llm/model_client.py` is the single place that talks to Groq/Azure —
every other module calls `achat_json` / `achat_vision_json` and doesn't
know or care which provider is behind it.

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your keys, deployment/model
   names, and `ANDROID_APP_PACKAGE` / `ANDROID_APP_ACTIVITY`.
3. Start Appium: `appium` (defaults to `http://127.0.0.1:4723`, matching
   `APPIUM_SERVER_URL`).
4. Connect a device or start an emulator.
5. `streamlit run streamlit_app.py`

## Using it

Type your steps in plain English, e.g.:

> Enter username 'john.doe' in the username field, enter password
> 'secret123' in the password field, tap Login, then verify the dashboard
> is shown.

Click **Plan & Run**. You'll first see the exact plan the agent extracted
(one line per atomic action) — review it before it executes. Then each
step runs, with a screenshot and pass/fail verification, and the run stops
automatically once the plan is complete.

### Supported actions (what the planner can produce)

| Action        | Needs target? | `value` holds                 |
|---------------|:--------------:|--------------------------------|
| `click`       | yes            | —                               |
| `type`        | yes            | text to type                    |
| `select`      | yes            | option text (dropdown/spinner)  |
| `toggle`      | yes            | — (checkbox/switch/radio)       |
| `scroll`      | no             | direction (up/down/left/right)  |
| `wait`        | no             | seconds                         |
| `press_back`  | no             | — (Android hardware Back)       |
| `close_app`   | no             | — (terminates the app)          |
| `verify`      | yes (as a description) | —                     |

## Config reference (`.env`)

See `.env.example` for the full list with defaults. Key ones:

- `LLM_PROVIDER` — `groq` or `azure`, drives both text and vision.
- `ANDROID_APP_PACKAGE` / `ANDROID_APP_ACTIVITY` — the app under test;
  launched automatically by Appium.
- `MAX_STEPS` — safety ceiling on how many steps a single plan may
  contain (not a retry loop — it caps plan length).
- `ENABLE_VISION_FALLBACK` — if `false`, resolution/verification never
  fall back to a screenshot-based vision call; a step that can't be
  resolved from the on-screen element list simply fails instead.
- `POPUP_DISMISS_ENABLED` — auto-dismiss common permission/consent
  dialogs before each step.

## Notes

- `.env` is intentionally **not** included in this delivery — keep using
  your existing one, just add/rename the variables shown in
  `.env.example` (mainly: replace `LLM_PROVIDER`/`VISION_LLM_PROVIDER` and
  any `DEEPSEEK_*` / `PLATFORM` / `TARGET_URL` vars with the new,
  simplified set above).
- `logs/screenshots/` is created automatically at startup for step
  screenshots.
