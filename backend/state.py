from typing import Any, TypedDict

AGENT_ORDER = ("analyst", "architect", "builder", "pitcher")
AgentStatus = str


class ProjectState(TypedDict, total=False):
    idea: str
    requirements: dict[str, Any]
    architecture: dict[str, Any]
    builder_prompt: str
    code_files: dict[str, str]
    pitch_deck: dict[str, Any]
    llm_calls: list[dict[str, Any]]
    fatal_error: bool
    current_agent: str
    agent_statuses: dict[str, AgentStatus]
    errors: list[str]
    run_id: str
    done: bool
    created_at: str
    updated_at: str


def initial_agent_statuses() -> dict[str, AgentStatus]:
    return {agent: "pending" for agent in AGENT_ORDER}
