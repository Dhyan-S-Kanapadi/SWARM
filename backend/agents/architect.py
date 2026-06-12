"""Architect agent for app architecture generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.agents.llm import GroqJsonError, MissingGroqApiKeyError, complete_json
from backend.state import ProjectState
from backend.utils import get_run_output_dir, read_text, write_json

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "architect_prompt.txt"


def run_architect(state: ProjectState) -> ProjectState:
    """Generate app architecture and persist it to architecture.json."""
    requirements = state.get("requirements", {})
    architecture = generate_architecture(state["prompt"], requirements)

    run_dir = Path(state.get("output_dir") or get_run_output_dir(state["run_id"]))
    write_json(run_dir / "architecture.json", architecture)

    state["output_dir"] = str(run_dir)
    state["architecture"] = architecture
    return state


def generate_architecture(prompt: str, requirements: dict[str, Any]) -> dict[str, Any]:
    """Generate architecture with Groq, falling back to deterministic output."""
    architect_prompt = format_architect_prompt(prompt, requirements)
    try:
        architecture = complete_json(architect_prompt)
        return normalize_architecture(architecture, prompt, requirements, source="groq")
    except (MissingGroqApiKeyError, GroqJsonError) as exc:
        fallback = deterministic_architecture(prompt, requirements)
        fallback["metadata"]["source"] = "deterministic_fallback"
        fallback["metadata"]["fallback_reason"] = exc.__class__.__name__
        return fallback


def format_architect_prompt(prompt: str, requirements: dict[str, Any]) -> str:
    """Format the Architect prompt with compact requirements JSON."""
    template = read_text(PROMPT_PATH)
    compact_requirements = json.dumps(
        compact_requirements_for_architect(requirements),
        indent=2,
        sort_keys=True,
    )
    if not template:
        return (
            "Design a generated local-business management app architecture.\n"
            f"User prompt:\n{prompt}\n\nRequirements:\n{compact_requirements}"
        )
    return template.replace("{{USER_PROMPT}}", prompt.strip()).replace(
        "{{REQUIREMENTS_JSON}}",
        compact_requirements,
    )


def compact_requirements_for_architect(requirements: dict[str, Any]) -> dict[str, Any]:
    """Keep only the requirements fields needed for architecture decisions."""
    keys = (
        "business_problem",
        "target_users",
        "core_workflows",
        "data_entities",
        "features",
        "dashboard_metrics",
        "localization",
        "constraints",
        "acceptance_criteria",
        "metadata",
    )
    compact = {key: requirements.get(key) for key in keys if key in requirements}
    return _truncate_nested(compact)


def normalize_architecture(
    architecture: dict[str, Any],
    prompt: str,
    requirements: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    """Ensure architecture includes required downstream fields."""
    fallback = deterministic_architecture(prompt, requirements)
    normalized = {
        "tech_stack": _dict_or_fallback(architecture.get("tech_stack"), fallback["tech_stack"]),
        "api_routes": _list_or_fallback(architecture.get("api_routes"), fallback["api_routes"]),
        "database_schema": _dict_or_fallback(
            architecture.get("database_schema"),
            fallback["database_schema"],
        ),
        "screens": _list_or_fallback(architecture.get("screens"), fallback["screens"]),
        "workflows": _list_or_fallback(architecture.get("workflows"), fallback["workflows"]),
        "validation": _list_or_fallback(architecture.get("validation"), fallback["validation"]),
        "metadata": {
            "source": source,
            "original_prompt": prompt,
            "requirements_source": requirements.get("metadata", {}).get("source"),
        },
    }
    return normalized


def deterministic_architecture(prompt: str, requirements: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic architecture from Analyst requirements."""
    entities = _string_list(requirements.get("data_entities"), ["business records"])
    metrics = _string_list(requirements.get("dashboard_metrics"), ["total records", "open items"])
    workflows = _string_list(
        requirements.get("core_workflows"),
        ["create records", "track status", "review dashboard"],
    )
    primary_entity = _slug(entities[0])

    return {
        "tech_stack": {
            "frontend": "React + Vite",
            "backend": "Express",
            "database": "local JSON file",
            "testing": "Node test runner",
        },
        "api_routes": [
            {"method": "GET", "path": "/api/health", "purpose": "health check"},
            {"method": "GET", "path": "/api/metrics", "purpose": "dashboard metrics"},
            {"method": "GET", "path": f"/api/{primary_entity}", "purpose": f"list {entities[0]}"},
            {"method": "POST", "path": f"/api/{primary_entity}", "purpose": f"create {entities[0]}"},
            {"method": "PUT", "path": f"/api/{primary_entity}/:id", "purpose": f"update {entities[0]}"},
            {"method": "DELETE", "path": f"/api/{primary_entity}/:id", "purpose": f"delete {entities[0]}"},
        ],
        "database_schema": {
            primary_entity: {
                "fields": [
                    {"name": "id", "type": "string"},
                    {"name": "name", "type": "string"},
                    {"name": "status", "type": "string"},
                    {"name": "service", "type": "string"},
                    {"name": "notes", "type": "string"},
                    {"name": "createdAt", "type": "datetime"},
                    {"name": "updatedAt", "type": "datetime"},
                ],
                "storage": f"server/data/{primary_entity}.json",
            },
            "metadata": {
                "fields": [
                    {"name": "lastSeededAt", "type": "datetime"},
                    {"name": "businessProblem", "type": "string"},
                ],
                "storage": "server/data/metadata.json",
            },
        },
        "screens": [
            {"name": "Dashboard", "purpose": f"show metrics: {', '.join(metrics[:4])}"},
            {"name": "Records", "purpose": f"CRUD, search, and filter {entities[0]}"},
            {"name": "Details", "purpose": "edit status, service details, and staff notes"},
        ],
        "workflows": workflows,
        "validation": [
            "npm run test",
            "npm run build",
            "manual API health check",
        ],
        "metadata": {
            "source": "deterministic",
            "original_prompt": prompt,
            "requirements_source": requirements.get("metadata", {}).get("source"),
        },
    }


def _truncate_nested(value: Any, limit: int = 1200) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_truncate_nested(item, limit) for item in value[:12]]
    if isinstance(value, dict):
        return {str(key): _truncate_nested(item, limit) for key, item in list(value.items())[:20]}
    return value


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback


def _list_or_fallback(value: Any, fallback: list[Any]) -> list[Any]:
    return value if isinstance(value, list) and value else fallback


def _dict_or_fallback(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    return value if isinstance(value, dict) and value else fallback


def _slug(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value)
    parts = [part for part in slug.split("-") if part]
    return "-".join(parts) or "records"
