import asyncio
import streamlit as st
from config import settings
from app.automation.planner import aplan
from app.automation.agent import run_plan

st.set_page_config(page_title="AI Mobile Automation", layout="wide")

st.title("AI-driven Mobile Automation")
st.caption(
    "Describe the steps in plain English. The agent PLANS the whole "
    "sequence first, shows you the plan, then executes exactly that plan - "
    "one time, in order - and stops. It will not invent extra steps or "
    "keep going once the plan is done."
)

with st.sidebar:
    st.header("Config (from .env)")
    st.text(f"LLM provider: {settings.llm_provider}")
    if settings.llm_provider == "groq":
        st.text(f"Text model: {settings.groq_model}")
        st.text(f"Vision model: {settings.groq_vision_model}")
    else:
        st.text(f"Azure deployment (text+vision): {settings.azure_openai_deployment}")
    st.text(f"App package: {settings.android_app_package}")
    st.text(f"App activity: {settings.android_app_activity}")
    st.text(f"Vision fallback: {'on' if settings.enable_vision_fallback else 'off (text-only locators)'}")
    st.text(f"Popup auto-dismiss: {'on' if settings.popup_dismiss_enabled else 'off'}")
    st.text(f"Max steps per plan: {settings.max_steps}")
    st.caption("Change these in your .env file, then restart the app.")

if "agent_running" not in st.session_state:
    st.session_state.agent_running = False

goal = st.text_area(
    "What should the agent do?",
    placeholder="e.g. Enter username 'john.doe' in the username field, enter "
                "password 'secret123' in the password field, tap Login, then "
                "verify the dashboard is shown.",
    height=100,
)

run_clicked = st.button(
    "Plan & Run",
    type="primary",
    disabled=not goal.strip() or st.session_state.agent_running,
)


def _render_plan(planned_steps):
    with st.expander(f"📋 Plan ({len(planned_steps)} step(s)) — this is exactly what will run", expanded=True):
        for i, s in enumerate(planned_steps, 1):
            line = f"**{i}. {s.action}**"
            if s.target:
                line += f" → \"{s.target}\""
            if s.value:
                line += f" = \"{s.value}\""
            st.markdown(line)
            if s.expected_outcome:
                st.caption(f"expects: {s.expected_outcome}")


def _render_step(log_container, log):
    step = log["step"]
    action = log["action"]
    status = log["status"]

    icon = {"ok": "🟢", "finished": "✅", "error": "⚠️"}.get(status, "•")
    with log_container:
        if status == "finished":
            st.success("Plan complete. Agent has stopped - no further actions will run.")
            return

        label = action.get("action")
        if action.get("target"):
            label += f" → \"{action['target']}\""
        with st.expander(f"{icon} Step {step}: {label}", expanded=(status != "ok")):
            st.json(action)

            if log.get("verification"):
                v = log["verification"]
                vt = "✅ Passed" if v["passed"] else "❌ Failed"
                st.write(f"**Verification ({v['method']}, score={v['score']}):** {vt}")
                st.caption(v["reasoning"])

            if log.get("error"):
                st.error(log["error"])

            if log.get("screenshot"):
                st.image(str(log["screenshot"]), width=400)

        if status == "error":
            st.error("Agent stopped — this step could not be completed.")


def _plan_and_run(goal: str, plan_container, log_container):
    """Plans once, shows the plan, then drives the fixed-plan execution to
    completion in one dedicated event loop. Guaranteed to run the plan
    exactly once per call - no re-planning, no repeat runs."""

    async def _drive():
        planned_steps = await aplan(goal)
        if not planned_steps:
            with plan_container:
                st.warning("The planner could not turn this into any actionable steps. Try rephrasing.")
            return
        with plan_container:
            _render_plan(planned_steps)
        async for log in run_plan(planned_steps):
            _render_step(log_container, log)

    asyncio.run(_drive())


if run_clicked:
    st.session_state.agent_running = True
    plan_container = st.container()
    log_container = st.container()
    with st.spinner("Planning, then running..."):
        try:
            _plan_and_run(goal, plan_container, log_container)
        finally:
            st.session_state.agent_running = False
