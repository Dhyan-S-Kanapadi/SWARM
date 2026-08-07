"""Public entry point for the deterministic Builder Agent workflow."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.agents.builder_agent.builder_graph import builder_graph, validate_architecture
from backend.agents.builder_agent.project_scaffold import assemble_project


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_REPO_ROOT = Path(__file__).resolve().parents[3]


def run_build(architecture: dict, run_id: str) -> dict[str, str]:
    """Run the fixed Builder graph and return generated files as ``{path: content}``.

    This step does not use an LLM or require ``GROQ_API_KEY``. The graph invokes
    schema application, API generation, UI generation, and optional auth
    scaffolding in a known dependency order.
    """

    if not isinstance(architecture, dict):
        raise ValueError("architecture must be a dictionary")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id may contain only letters, numbers, underscores, and hyphens")
    validate_architecture(architecture)
    load_dotenv(_REPO_ROOT / ".env")

    result = builder_graph.invoke({"architecture": architecture, "run_id": run_id, "code_files": {}})
    schema_result = result.get("schema_result", {})
    schema_errors = schema_result.get("errors", []) if isinstance(schema_result, Mapping) else []
    if schema_errors:
        raise RuntimeError(f"Builder schema application failed: {'; '.join(map(str, schema_errors))}")
    files = _normalise_generated_files(result.get("code_files", {}))
    if not files:
        raise RuntimeError("Builder graph produced no generated files")
    return assemble_project(files, architecture, run_id)


def _normalise_generated_files(generated: Any) -> dict[str, str]:
    if not isinstance(generated, Mapping):
        return {}
    files: dict[str, str] = {}
    for path, content in generated.items():
        if not isinstance(path, str) or not isinstance(content, str) or not content:
            raise RuntimeError("Builder graph returned an invalid generated file mapping")
        files[path] = content
    return files


__all__ = ["run_build"]


if __name__ == "__main__":
    from backend.agents.architect import fallback_architecture

    example_architecture = fallback_architecture({})
    print(json.dumps(run_build(example_architecture, "builder-agent-standalone"), indent=2))
