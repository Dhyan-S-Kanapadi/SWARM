"""Placeholder Analyst agent."""

from __future__ import annotations

from backend.state import ProjectState


def run_analyst(state: ProjectState) -> ProjectState:
    """Create placeholder requirements until the LLM-backed agent is added."""
    prompt = state["prompt"]
    state["requirements"] = {
        "source_prompt": prompt,
        "business_problem": prompt,
        "users": ["business owner", "staff"],
        "workflows": ["capture records", "track status", "review summary"],
        "status": "placeholder",
    }
    return state
