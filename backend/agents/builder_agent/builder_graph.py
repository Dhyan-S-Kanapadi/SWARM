"""Deterministic Builder Agent orchestration with LangGraph."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.agents.builder_agent.tools.generate_api_routes import generate_api_routes
from backend.agents.builder_agent.tools.generate_ui_screens import generate_ui_screens
from backend.agents.builder_agent.tools.scaffold_auth import scaffold_auth
from backend.agents.builder_agent.tools.schema_apply import apply_database_schema


_REQUIRED_ARCHITECTURE_FIELDS = {
    "tech_stack",
    "app_shell",
    "database_schema",
    "api_routes",
    "ui_screens",
    "project_modules",
    "state_management",
    "localization_plan",
    "automation_jobs",
    "validation_plan",
    "folder_structure",
    "build_constraints",
}


class BuilderGraphState(TypedDict, total=False):
    """State passed through the fixed Builder Agent generation sequence."""

    architecture: dict[str, Any]
    run_id: str
    code_files: dict[str, str]
    schema_result: dict[str, Any]


def build_builder_graph():
    """Create the fixed schema -> API -> UI -> auth Builder workflow."""

    graph = StateGraph(BuilderGraphState)
    graph.add_node("schema_apply", _schema_apply_node)
    graph.add_node("generate_api_routes", _generate_api_routes_node)
    graph.add_node("generate_ui_screens", _generate_ui_screens_node)
    graph.add_node("scaffold_auth", _scaffold_auth_node)

    graph.set_entry_point("schema_apply")
    graph.add_edge("schema_apply", "generate_api_routes")
    graph.add_edge("generate_api_routes", "generate_ui_screens")
    graph.add_edge("generate_ui_screens", "scaffold_auth")
    graph.add_edge("scaffold_auth", END)
    return graph.compile()


def validate_architecture(architecture: Mapping[str, Any]) -> None:
    """Validate the Architect object required by the deterministic nodes."""

    missing = sorted(key for key in _REQUIRED_ARCHITECTURE_FIELDS if key not in architecture)
    if missing:
        raise ValueError(f"architecture is missing required fields: {', '.join(missing)}")
    if not isinstance(architecture["database_schema"], dict):
        raise ValueError("architecture.database_schema must be a dictionary")
    if not isinstance(architecture["api_routes"], list):
        raise ValueError("architecture.api_routes must be a list")
    if not isinstance(architecture["ui_screens"], list):
        raise ValueError("architecture.ui_screens must be a list")


def _schema_apply_node(state: BuilderGraphState) -> dict[str, Any]:
    architecture = state["architecture"]
    return {"schema_result": apply_database_schema(architecture["database_schema"])}


def _generate_api_routes_node(state: BuilderGraphState) -> dict[str, dict[str, str]]:
    architecture = state["architecture"]
    return {
        "code_files": {
            **state.get("code_files", {}),
            **generate_api_routes(architecture["api_routes"], architecture["database_schema"]),
        }
    }


def _generate_ui_screens_node(state: BuilderGraphState) -> dict[str, dict[str, str]]:
    architecture = state["architecture"]
    return {
        "code_files": {
            **state.get("code_files", {}),
            **generate_ui_screens(architecture["ui_screens"], architecture["api_routes"]),
        }
    }


def _scaffold_auth_node(state: BuilderGraphState) -> dict[str, dict[str, str]]:
    architecture = state["architecture"]
    auth_config = architecture.get("auth")
    auth_required = auth_config is True or (
        isinstance(auth_config, Mapping) and auth_config.get("required") is True
    )
    auth_files = scaffold_auth(auth_config, architecture["api_routes"]) if auth_required else {}
    return {"code_files": {**state.get("code_files", {}), **auth_files}}


builder_graph = build_builder_graph()
