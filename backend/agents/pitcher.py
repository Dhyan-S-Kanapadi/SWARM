"""Pitcher agent for generated app summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.agents.llm import GroqJsonError, MissingGroqApiKeyError, complete_json
from backend.state import ProjectState
from backend.utils import get_run_output_dir, read_text, write_json

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "pitcher_prompt.txt"


def run_pitcher(state: ProjectState) -> ProjectState:
    """Generate a pitch deck and persist it to pitch_deck.json."""
    pitch_deck = generate_pitch_deck(
        state["prompt"],
        state.get("requirements", {}),
        state.get("architecture", {}),
        state.get("generated_files", {}),
    )

    run_dir = Path(state.get("output_dir") or get_run_output_dir(state["run_id"]))
    write_json(run_dir / "pitch_deck.json", pitch_deck)

    state["output_dir"] = str(run_dir)
    state["pitch_deck"] = pitch_deck
    return state


def generate_pitch_deck(
    prompt: str,
    requirements: dict[str, Any],
    architecture: dict[str, Any],
    generated_files: dict[str, str],
) -> dict[str, Any]:
    """Generate a pitch deck with Groq, falling back to deterministic output."""
    pitcher_prompt = format_pitcher_prompt(prompt, requirements, architecture, generated_files)
    try:
        pitch_deck = complete_json(pitcher_prompt)
        return normalize_pitch_deck(
            pitch_deck,
            prompt,
            requirements,
            architecture,
            generated_files,
            source="groq",
        )
    except (MissingGroqApiKeyError, GroqJsonError) as exc:
        fallback = deterministic_pitch_deck(prompt, requirements, architecture, generated_files)
        fallback["metadata"]["source"] = "deterministic_fallback"
        fallback["metadata"]["fallback_reason"] = exc.__class__.__name__
        return fallback


def format_pitcher_prompt(
    prompt: str,
    requirements: dict[str, Any],
    architecture: dict[str, Any],
    generated_files: dict[str, str],
) -> str:
    """Format the Pitcher prompt with compact artifact summaries."""
    template = read_text(PROMPT_PATH)
    payload = json.dumps(
        {
            "prompt": prompt,
            "requirements": _compact(requirements),
            "architecture": _compact(architecture),
            "generated_file_paths": sorted(generated_files.keys()),
        },
        indent=2,
        sort_keys=True,
    )
    if not template:
        return f"Create a JSON pitch deck for this generated app:\n{payload}"
    return template.replace("{{ARTIFACT_SUMMARY_JSON}}", payload)


def normalize_pitch_deck(
    pitch_deck: dict[str, Any],
    prompt: str,
    requirements: dict[str, Any],
    architecture: dict[str, Any],
    generated_files: dict[str, str],
    *,
    source: str,
) -> dict[str, Any]:
    """Ensure the pitch deck has stable top-level fields."""
    fallback = deterministic_pitch_deck(prompt, requirements, architecture, generated_files)
    return {
        "title": str(pitch_deck.get("title") or fallback["title"]),
        "summary": str(pitch_deck.get("summary") or fallback["summary"]),
        "problem": str(pitch_deck.get("problem") or fallback["problem"]),
        "solution": str(pitch_deck.get("solution") or fallback["solution"]),
        "target_users": _string_list(pitch_deck.get("target_users"), fallback["target_users"]),
        "key_features": _string_list(pitch_deck.get("key_features"), fallback["key_features"]),
        "demo_flow": _string_list(pitch_deck.get("demo_flow"), fallback["demo_flow"]),
        "technical_notes": _string_list(pitch_deck.get("technical_notes"), fallback["technical_notes"]),
        "next_steps": _string_list(pitch_deck.get("next_steps"), fallback["next_steps"]),
        "metadata": {
            "source": source,
            "generated_file_count": len(generated_files),
        },
    }


def deterministic_pitch_deck(
    prompt: str,
    requirements: dict[str, Any],
    architecture: dict[str, Any],
    generated_files: dict[str, str],
) -> dict[str, Any]:
    """Create a stable pitch deck from workflow artifacts."""
    business_problem = requirements.get("business_problem") or prompt
    target_users = _string_list(requirements.get("target_users"), ["business owner", "staff"])
    features = _string_list(
        requirements.get("features"),
        ["dashboard metrics", "CRUD records", "search and filtering", "local JSON storage"],
    )
    workflows = _string_list(
        requirements.get("core_workflows"),
        ["open the dashboard", "add a record", "filter work", "update status"],
    )
    tech_stack = architecture.get("tech_stack", {})
    api_routes = architecture.get("api_routes", [])

    return {
        "title": "SWARM Generated Local Business App",
        "summary": (
            "SWARM.AI turned one plain-language local business workflow problem into "
            "a runnable React and Express management app with local JSON persistence."
        ),
        "problem": business_problem,
        "solution": (
            "A generated app that gives staff a dashboard, record management, "
            "search/filter controls, status tracking, seed data, and runnable checks."
        ),
        "target_users": target_users,
        "key_features": features,
        "demo_flow": [
            "Launch the generated Express API and Vite frontend",
            "Review dashboard metrics",
            *workflows[:4],
            "Run generated app checks and build",
        ],
        "technical_notes": [
            f"Frontend: {tech_stack.get('frontend', 'React + Vite')}",
            f"Backend: {tech_stack.get('backend', 'Express')}",
            f"Database: {tech_stack.get('database', 'local JSON file')}",
            f"API routes planned: {len(api_routes)}",
            f"Generated files: {len(generated_files)}",
            "Builder is internal and deterministic",
        ],
        "next_steps": [
            "Validate generated app quality",
            "Launch a live preview",
            "Review generated code and demo flow",
            "Package the generated app for download",
        ],
        "metadata": {
            "source": "deterministic",
            "generated_file_count": len(generated_files),
        },
    }


def _compact(value: Any, limit: int = 1200) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_compact(item, limit) for item in value[:10]]
    if isinstance(value, dict):
        return {str(key): _compact(item, limit) for key, item in list(value.items())[:18]}
    return value


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback
