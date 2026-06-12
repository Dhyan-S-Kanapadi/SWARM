"""Placeholder Architect agent."""

from __future__ import annotations

from backend.state import ProjectState


def run_architect(state: ProjectState) -> ProjectState:
    """Create placeholder architecture until the LLM-backed agent is added."""
    state["architecture"] = {
        "tech_stack": {
            "frontend": "React + Vite",
            "backend": "Express",
            "database": "local JSON file",
        },
        "api_routes": ["/api/health", "/api/records", "/api/metrics"],
        "database_schema": {
            "records": ["id", "name", "status", "notes", "createdAt"],
        },
        "status": "placeholder",
    }
    return state
