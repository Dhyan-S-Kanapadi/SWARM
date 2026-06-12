"""Analyst agent for requirements generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.agents.llm import GroqJsonError, MissingGroqApiKeyError, complete_json
from backend.state import ProjectState
from backend.utils import get_run_output_dir, read_text, write_json

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "analyst_prompt.txt"


def run_analyst(state: ProjectState) -> ProjectState:
    """Generate requirements and persist them to requirements.json."""
    prompt = state["prompt"]
    requirements = generate_requirements(prompt)

    run_dir = Path(state.get("output_dir") or get_run_output_dir(state["run_id"]))
    write_json(run_dir / "requirements.json", requirements)

    state["output_dir"] = str(run_dir)
    state["requirements"] = requirements
    return state


def generate_requirements(prompt: str) -> dict[str, Any]:
    """Generate requirements with Groq, falling back to deterministic output."""
    analyst_prompt = format_analyst_prompt(prompt)
    try:
        requirements = complete_json(analyst_prompt)
        return normalize_requirements(requirements, prompt, source="groq")
    except (MissingGroqApiKeyError, GroqJsonError) as exc:
        fallback = deterministic_requirements(prompt)
        fallback["metadata"]["source"] = "deterministic_fallback"
        fallback["metadata"]["fallback_reason"] = exc.__class__.__name__
        return fallback


def format_analyst_prompt(prompt: str) -> str:
    """Format the Analyst prompt for the LLM."""
    template = read_text(PROMPT_PATH)
    if not template:
        return f"Analyze this local business app request and return requirements JSON:\n{prompt}"
    return template.replace("{{USER_PROMPT}}", prompt.strip())


def normalize_requirements(
    requirements: dict[str, Any],
    prompt: str,
    *,
    source: str,
) -> dict[str, Any]:
    """Ensure the Analyst output has the fields downstream agents expect."""
    fallback = deterministic_requirements(prompt)
    normalized = {
        "business_problem": requirements.get("business_problem") or fallback["business_problem"],
        "target_users": _string_list(requirements.get("target_users"), fallback["target_users"]),
        "core_workflows": _string_list(requirements.get("core_workflows"), fallback["core_workflows"]),
        "data_entities": _string_list(requirements.get("data_entities"), fallback["data_entities"]),
        "features": _string_list(requirements.get("features"), fallback["features"]),
        "dashboard_metrics": _string_list(
            requirements.get("dashboard_metrics"),
            fallback["dashboard_metrics"],
        ),
        "localization": requirements.get("localization") or fallback["localization"],
        "constraints": _string_list(requirements.get("constraints"), fallback["constraints"]),
        "acceptance_criteria": _string_list(
            requirements.get("acceptance_criteria"),
            fallback["acceptance_criteria"],
        ),
        "metadata": {
            "source": source,
            "original_prompt": prompt,
        },
    }
    return normalized


def deterministic_requirements(prompt: str) -> dict[str, Any]:
    """Create stable baseline requirements without an LLM."""
    business_type = _infer_business_type(prompt)
    record_label = _record_label_for_business(business_type)
    queue_label = "appointments" if business_type in {"salon", "clinic", "fitness studio"} else "orders"

    return {
        "business_problem": prompt.strip(),
        "target_users": ["business owner", "staff"],
        "core_workflows": [
            f"capture and update {record_label}",
            f"manage {queue_label}",
            "search and filter active records",
            "review daily operational summary",
        ],
        "data_entities": [
            record_label,
            "customers",
            "services",
            "staff notes",
        ],
        "features": [
            "dashboard metrics",
            f"CRUD management for {record_label}",
            "status tracking",
            "search and filtering",
            "seed data for demo use",
        ],
        "dashboard_metrics": [
            f"total {record_label}",
            f"open {queue_label}",
            "completed today",
            "follow ups due",
        ],
        "localization": {
            "language_ready": True,
            "notes": "Use simple labels that can be translated for local staff.",
        },
        "constraints": [
            "generated app must run locally",
            "use React frontend",
            "use Express backend",
            "store data in local JSON files",
            "builder must be deterministic and internal",
        ],
        "acceptance_criteria": [
            "owner can create, update, search, and filter records",
            "dashboard displays current operational metrics",
            "app includes seed data and runnable scripts",
            "generated code avoids external app-builder dependencies",
        ],
        "metadata": {
            "source": "deterministic",
            "original_prompt": prompt,
            "business_type": business_type,
        },
    }


def _infer_business_type(prompt: str) -> str:
    normalized = prompt.lower()
    if any(term in normalized for term in ("salon", "saloon", "beauty", "spa", "hair", "barber", "makeup")):
        return "salon"
    if "bakery" in normalized or "cake" in normalized:
        return "bakery"
    if any(term in normalized for term in ("clinic", "doctor", "patient", "medical")):
        return "clinic"
    if any(term in normalized for term in ("fitness", "gym", "studio", "trainer")):
        return "fitness studio"
    if any(term in normalized for term in ("tuition", "class", "student", "coaching")):
        return "tuition center"
    return "local business"


def _record_label_for_business(business_type: str) -> str:
    labels = {
        "bakery": "orders",
        "salon": "appointments",
        "clinic": "patient visits",
        "fitness studio": "memberships",
        "tuition center": "student enrollments",
    }
    return labels.get(business_type, "business records")


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback
