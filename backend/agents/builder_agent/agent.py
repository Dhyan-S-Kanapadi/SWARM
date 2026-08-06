"""OpenHands-powered Builder Agent assembly.

Custom tools follow the OpenHands SDK v1.40 Action -> Executor -> Observation
model. The only public entry point is :func:`run_build`, which returns the
same flat file mapping used by the legacy Builder implementation.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from dotenv import load_dotenv
from pydantic import Field

from openhands.sdk import (
    Action,
    Agent,
    AgentContext,
    Conversation,
    LLM,
    Observation,
    Tool,
    ToolDefinition,
    register_tool,
)
from openhands.sdk.tool import ToolAnnotations, ToolExecutor

from backend.agents.builder_agent.prompt import SYSTEM_MESSAGE_SUFFIX
from backend.agents.builder_agent.tools.generate_api_routes import generate_api_routes
from backend.agents.builder_agent.tools.generate_ui_screens import generate_ui_screens
from backend.agents.builder_agent.tools.scaffold_auth import scaffold_auth
from backend.agents.builder_agent.tools.schema_apply import apply_database_schema


_REPO_ROOT = Path(__file__).resolve().parents[3]
_OUTPUT_ROOT = _REPO_ROOT / "backend" / "outputs"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
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


class SchemaApplyAction(Action):
    """Input for applying the architecture's database schema."""

    database_schema: dict[str, Any] = Field(description="Database schema from the architecture object.")
    database_url: str | None = Field(default=None, description="Optional PostgreSQL URL; defaults to DATABASE_URL.")


class GenerateApiRoutesAction(Action):
    """Input for generating the Express/PostgreSQL API server."""

    api_routes: list[dict[str, Any]] = Field(description="API route definitions from the architecture object.")
    database_schema: dict[str, Any] = Field(description="Database schema used to map routes to tables.")


class GenerateUiScreensAction(Action):
    """Input for generating React screens from the architecture contract."""

    ui_screens: list[dict[str, Any]] = Field(description="UI screen definitions from the architecture object.")
    api_routes: list[dict[str, Any]] = Field(description="API route definitions used by the UI screens.")


class ScaffoldAuthAction(Action):
    """Input for conditionally scaffolding authentication."""

    auth_config: bool | dict[str, Any] | None = Field(
        default=None,
        description="Architecture auth configuration. Use false or null when authentication is not required.",
    )
    api_routes: list[dict[str, Any]] = Field(default_factory=list, description="API routes used to derive protected paths.")


class BuilderToolObservation(Observation):
    """Structured success or error result returned by every Builder Agent tool."""

    result: dict[str, Any] = Field(description="Structured tool result, including generated files where applicable.")


class _FunctionExecutor(ToolExecutor):
    """Execute one deterministic Builder function and record generated files."""

    def __init__(self, function: Callable[..., Any]) -> None:
        self._function = function

    def __call__(self, action: Action, conversation=None) -> BuilderToolObservation:  # type: ignore[override]
        try:
            result = self._invoke(action)
            if isinstance(result, dict) and all(isinstance(value, str) for value in result.values()):
                _record_generated_files(conversation, result)
                payload: dict[str, Any] = {"files": result}
            elif isinstance(result, Mapping):
                payload = dict(result)
            else:
                payload = {"value": result}
            return BuilderToolObservation.from_text(json.dumps(payload, indent=2, default=str), result=payload)
        except Exception as exc:  # Tool failures must be observations so the agent can recover or report them.
            payload = {"errors": [f"{type(exc).__name__}: {exc}"]}
            return BuilderToolObservation.from_text(
                json.dumps(payload, indent=2), is_error=True, result=payload
            )

    def _invoke(self, action: Action) -> Any:
        if isinstance(action, SchemaApplyAction):
            return self._function(action.database_schema, action.database_url)
        if isinstance(action, GenerateApiRoutesAction):
            return self._function(action.api_routes, action.database_schema)
        if isinstance(action, GenerateUiScreensAction):
            return self._function(action.ui_screens, action.api_routes)
        if isinstance(action, ScaffoldAuthAction):
            return self._function(action.auth_config, action.api_routes)
        raise TypeError(f"Unsupported Builder Agent action: {type(action).__name__}")


class _BuilderTool(ToolDefinition[Action, BuilderToolObservation]):
    """Base ToolDefinition for a deterministic Builder Agent function."""

    action_model: ClassVar[type[Action]]
    description_text: ClassVar[str]
    function: ClassVar[Callable[..., Any]]
    annotations_value: ClassVar[ToolAnnotations]

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["_BuilderTool"]:  # noqa: ARG003
        if params:
            raise ValueError(f"{cls.__name__} does not accept initialization parameters")
        return [
            cls(
                action_type=cls.action_model,
                observation_type=BuilderToolObservation,
                description=cls.description_text,
                annotations=cls.annotations_value,
                executor=_FunctionExecutor(cls.function),
            )
        ]


class SchemaApplyTool(_BuilderTool):
    action_model = SchemaApplyAction
    function = apply_database_schema
    description_text = "Apply the architecture database_schema to PostgreSQL and insert seed records."
    annotations_value = ToolAnnotations(title="schema_apply", destructiveHint=True, idempotentHint=True, openWorldHint=False)


class GenerateApiRoutesTool(_BuilderTool):
    action_model = GenerateApiRoutesAction
    function = generate_api_routes
    description_text = "Generate a PostgreSQL-backed Express server/index.js from API routes and database schema."
    annotations_value = ToolAnnotations(title="generate_api_routes", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class GenerateUiScreensTool(_BuilderTool):
    action_model = GenerateUiScreensAction
    function = generate_ui_screens
    description_text = "Generate architecture-driven React screen files from ui_screens and API routes."
    annotations_value = ToolAnnotations(title="generate_ui_screens", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class ScaffoldAuthTool(_BuilderTool):
    action_model = ScaffoldAuthAction
    function = scaffold_auth
    description_text = "Conditionally generate session-auth backend and frontend files. Return no files when authentication is not required."
    annotations_value = ToolAnnotations(title="scaffold_auth", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


for _tool in (SchemaApplyTool, GenerateApiRoutesTool, GenerateUiScreensTool, ScaffoldAuthTool):
    register_tool(_tool.name, _tool)


def _create_agent(llm: LLM) -> Agent:
    """Create the configured OpenHands agent with only Builder-specific tools."""

    return Agent(
        llm=llm,
        tools=[
            Tool(name=SchemaApplyTool.name),
            Tool(name=GenerateApiRoutesTool.name),
            Tool(name=GenerateUiScreensTool.name),
            Tool(name=ScaffoldAuthTool.name),
        ],
        include_default_tools=["FinishTool"],
        agent_context=AgentContext(skills=[], system_message_suffix=SYSTEM_MESSAGE_SUFFIX),
        system_prompt_kwargs={"cli_mode": True},
    )


def run_build(architecture: dict, run_id: str) -> dict[str, str]:
    """Run the Builder Agent and return all generated files as ``{path: content}``.

    The agent calls the four wrapped tools in dependency order. File-generating
    tool observations are saved to conversation state and returned in the legacy
    Builder's flat mapping contract. A failed conversation is allowed to fail
    loudly rather than being mistaken for a successful generated application.
    """

    if not isinstance(architecture, dict):
        raise ValueError("architecture must be a dictionary")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id may contain only letters, numbers, underscores, and hyphens")
    _validate_architecture(architecture)

    load_dotenv(_REPO_ROOT / ".env")
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required to run the OpenHands Builder Agent")

    model = _openhands_model_name(os.getenv("OPENHANDS_BUILDER_MODEL") or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
    llm = LLM(
        model=model,
        api_key=api_key,
        max_output_tokens=1200,
        num_retries=1,
        retry_min_wait=5,
        force_string_serializer=True,
    )
    workspace = _OUTPUT_ROOT / run_id / "builder_agent_workspace"
    persistence_dir = workspace / ".openhands_persistence"
    workspace.mkdir(parents=True, exist_ok=True)
    persistence_dir.mkdir(parents=True, exist_ok=True)

    conversation = Conversation(
        agent=_create_agent(llm),
        workspace=str(workspace),
        persistence_dir=str(persistence_dir),
        visualizer=None,
    )
    try:
        conversation.send_message(_build_task(architecture))
        conversation.run()
        generated = conversation.state.agent_state.get("builder_files", {})
    finally:
        conversation.close()

    files = _normalise_generated_files(generated)
    if not files:
        raise RuntimeError("Builder Agent produced no generated files")
    return files


def _record_generated_files(conversation: Any, files: Mapping[str, str]) -> None:
    if conversation is None:
        return
    state = conversation.state
    current = dict(state.agent_state.get("builder_files", {}))
    current.update(files)
    state.agent_state = {**state.agent_state, "builder_files": current}


def _validate_architecture(architecture: Mapping[str, Any]) -> None:
    missing = sorted(key for key in _REQUIRED_ARCHITECTURE_FIELDS if key not in architecture)
    if missing:
        raise ValueError(f"architecture is missing required fields: {', '.join(missing)}")
    if not isinstance(architecture["database_schema"], dict):
        raise ValueError("architecture.database_schema must be a dictionary")
    if not isinstance(architecture["api_routes"], list):
        raise ValueError("architecture.api_routes must be a list")
    if not isinstance(architecture["ui_screens"], list):
        raise ValueError("architecture.ui_screens must be a list")


def _build_task(architecture: Mapping[str, Any]) -> str:
    return (
        "Build the supplied architecture. Call schema_apply first with database_schema, then "
        "generate_api_routes with api_routes and database_schema, then generate_ui_screens "
        "with ui_screens and api_routes. Call scaffold_auth only when architecture.auth "
        "explicitly sets required to true. Finish after reporting the generated file paths.\n\n"
        f"Architecture:\n{json.dumps(architecture, indent=2)}"
    )


def _normalise_generated_files(generated: Any) -> dict[str, str]:
    if not isinstance(generated, Mapping):
        return {}
    files: dict[str, str] = {}
    for path, content in generated.items():
        if not isinstance(path, str) or not isinstance(content, str) or not content:
            raise RuntimeError("Builder Agent returned an invalid generated file mapping")
        files[path] = content
    return files


def _openhands_model_name(model: str) -> str:
    return model if "/" in model and model.startswith("groq/") else f"groq/{model}"


__all__ = ["run_build"]


if __name__ == "__main__":
    from backend.agents.architect import fallback_architecture

    example_architecture = fallback_architecture({})
    print(json.dumps(run_build(example_architecture, "builder-agent-standalone"), indent=2))
