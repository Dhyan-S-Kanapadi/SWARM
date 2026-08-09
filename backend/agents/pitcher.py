import json

from backend.agents.llm import allow_fallback_for_idea, call_llm_json, llm_provider_for_agent
from backend.state import ProjectState
from backend.utils import complete_agent, load_prompt, set_agent_status, write_json

MAX_TOKENS = 900


def run_pitcher(state: ProjectState) -> ProjectState:
    set_agent_status(state, "pitcher", "running")
    try:
        prior_outputs = {
            "idea": state.get("idea", ""),
            "problem_statement": (state.get("requirements") or {}).get("problem_statement", ""),
            "target_audience": (state.get("requirements") or {}).get("target_audience", ""),
            "core_features": (state.get("requirements") or {}).get("core_features", [])[:9],
            "localization": (state.get("requirements") or {}).get("localization_requirements", {}),
            "tech_stack": (state.get("architecture") or {}).get("tech_stack", {}),
            "ui_screens": (state.get("architecture") or {}).get("ui_screens", [])[:5],
            "validation": state.get("validation_report", {}),
            "quality": state.get("quality_report", {}),
            "code_files": list(state.get("code_files", {}).keys()),
        }
        state["pitch_deck"] = call_llm_json(
            agent_name="pitcher",
            system_prompt=load_prompt("pitcher_prompt.txt"),
            user_content=json.dumps(prior_outputs, separators=(",", ":")),
            temperature=0.3,
            max_tokens=MAX_TOKENS,
        )
        state.setdefault("llm_calls", []).append({"agent": "pitcher", "provider": llm_provider_for_agent("pitcher"), "status": "success"})
        complete_agent(state, "pitcher")
    except Exception as exc:
        if not allow_fallback_for_idea(state.get("idea", "")):
            set_agent_status(state, "pitcher", "error")
            state["fatal_error"] = True
            raise
        state.setdefault("errors", []).append(f"Pitcher used fallback after LLM error: {exc}")
        state["pitch_deck"] = fallback_pitch(state)
        state.setdefault("llm_calls", []).append({"agent": "pitcher", "provider": llm_provider_for_agent("pitcher"), "status": "fallback"})
        complete_agent(state, "pitcher")

    write_json(state["run_id"], "pitch_deck.json", state["pitch_deck"])
    return state


def fallback_pitch(state: ProjectState) -> dict:
    requirements = state.get("requirements", {})
    idea = state.get("idea", "local business app")
    audience = requirements.get("target_audience", "local business owners")
    problem = requirements.get("problem_statement", f"{audience} need practical software without engineering effort.")
    features = requirements.get("core_features", [])
    return {
        "tagline": "One prompt to a working local-business app.",
        "problem": problem,
        "solution": f"SWARM.AI converts '{idea}' into a runnable MVP with workflows, dashboard, local-language UI, seed data, and validation.",
        "target_market": audience,
        "business_model": ["freemium local builder", "paid export/deployment", "service packages for local businesses"],
        "market_size": "Millions of small businesses need simple internal software but cannot hire developers for every workflow.",
        "competitive_advantage": "SWARM combines product analysis, architecture, internal app generation, validation, and quality scoring in one local-first workflow.",
        "traction_and_roadmap": f"Current MVP generates apps with {len(features)} feature targets, CRUD APIs, localization, tests, preview, and quality gate.",
        "call_to_action": "Use SWARM.AI to help local businesses turn operational problems into working apps in minutes.",
    }
