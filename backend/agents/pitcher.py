"""Placeholder Pitcher agent."""

from __future__ import annotations

from backend.state import ProjectState


def run_pitcher(state: ProjectState) -> ProjectState:
    """Create a placeholder pitch summary."""
    state["pitch_deck"] = {
        "title": "SWARM Generated Local Business App",
        "summary": "A runnable management app will be generated from the business workflow prompt.",
        "highlights": ["dashboard", "CRUD records", "local JSON data"],
        "status": "placeholder",
    }
    return state
