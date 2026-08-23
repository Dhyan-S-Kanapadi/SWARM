"""Top-level Builder node adapter for SWARM's LangGraph workflow."""

from __future__ import annotations

import json

from backend.agents.builder_agent.agent import run_build
from backend.state import ProjectState
from backend.utils import complete_agent, output_dir, set_agent_status, write_code_files, write_text


def format_builder_context(state: ProjectState) -> str:
    """Persist the deterministic Builder inputs for MCP consumers and debugging."""

    return json.dumps(
        {
            "idea": state.get("idea", ""),
            "requirements": state.get("requirements", {}),
            "architecture": state.get("architecture", {}),
            "orchestration": (
                "langgraph:validate_architecture->schema_apply->workspace_prepare->"
                "openhands_author_source->validate_generated_app"
            ),
        },
        indent=2,
        sort_keys=True,
    )


def run_builder(state: ProjectState) -> ProjectState:
    """Run the nested deterministic Builder LangGraph without changing state contracts."""

    set_agent_status(state, "builder", "running")
    state["builder_prompt"] = format_builder_context(state)
    write_text(state["run_id"], "builder_prompt.txt", state["builder_prompt"])

    try:
        state["code_files"] = run_build(
            state["architecture"],
            state["run_id"],
            state.get("requirements", {}),
            state.get("idea", ""),
        )
        build_diagnostics = _read_openhands_build(state["run_id"])
        state["openhands_build"] = build_diagnostics
        if build_diagnostics.get("mode") == "deterministic_fallback":
            state.setdefault("errors", []).append(
                f"Builder used deterministic fallback: {build_diagnostics.get('fallback_reason', 'unknown reason')}"
            )
            state.setdefault("llm_calls", []).append(
                {"agent": "builder", "provider": "langgraph", "status": "fallback"}
            )
        else:
            state.setdefault("llm_calls", []).append(
                {
                    "agent": "builder",
                    "provider": build_diagnostics.get("provider", "openhands"),
                    "status": "success",
                }
            )
    except Exception:
        set_agent_status(state, "builder", "error")
        state["fatal_error"] = True
        raise

    write_code_files(state["run_id"], state["code_files"])
    complete_agent(state, "builder")
    return state


def _read_openhands_build(run_id: str) -> dict:
    path = output_dir(run_id) / "openhands_build.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
