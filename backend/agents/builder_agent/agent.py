"""Public entry points for Builder Agent workflows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.agents.builder_agent.builder_graph import builder_graph, validate_architecture
from backend.agents.builder_agent.database import (
    database_namespace,
    database_url_for_namespace,
    ensure_database_namespace,
)
from backend.agents.builder_agent.project_scaffold import assemble_project
from backend.agents.builder_agent.tools.schema_apply import apply_database_schema
from backend.utils import clean_process_output, output_dir, write_json


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLACEHOLDER_KEYS = {"", "your_openrouter_api_key", "your_api_key_here", "replace_me"}
_EXCLUDED_PARTS = {
    ".git",
    ".openhands_persistence",
    ".swarm-preview",
    "coverage",
    "dist",
    "node_modules",
}
_SOURCE_SUFFIXES = {".css", ".html", ".js", ".jsx", ".json", ".md", ".mjs", ".ts", ".tsx"}
_DEFAULT_OPENHANDS_TIMEOUT_SECONDS = 120
_DEFAULT_OPENHANDS_MAX_ITERATIONS = 30
_DEFAULT_VALIDATION_TIMEOUT_SECONDS = 180


def run_build(
    architecture: dict,
    run_id: str,
    requirements: dict[str, Any] | None = None,
    idea: str = "",
) -> dict[str, str]:
    """Build an app with OpenHands as the primary source author.

    The public Builder contract remains ``{relative_path: content}``. OpenHands
    diagnostics are written to ``openhands_build.json`` so callers can see when
    the deterministic generator was used as an explicit fallback.
    """

    _validate_build_inputs(architecture, run_id)
    load_dotenv(_REPO_ROOT / ".env")
    _prepare_openhands_home(run_id)

    diagnostics: dict[str, Any] = {
        "mode": "openhands_primary",
        "run_id": run_id,
        "schema_result": _apply_schema_phase(architecture, run_id),
        "workspace": "",
        "validation": {},
    }
    _raise_for_schema_errors(diagnostics["schema_result"])

    config = _openhands_config()
    if config is None:
        return _deterministic_fallback(
            architecture,
            run_id,
            diagnostics,
            "OpenHands is enabled but no usable OPENHANDS_MODEL and OPENHANDS_API_KEY are configured",
        )

    workspace = _prepare_openhands_workspace(run_id, architecture, requirements or {}, idea)
    diagnostics["workspace"] = str(workspace)
    before = _project_fingerprint(workspace)
    try:
        result = _run_openhands_authoring(config, workspace, architecture, requirements or {}, idea, run_id)
        after = _project_fingerprint(workspace)
        if before == after:
            raise RuntimeError(
                "OpenHands completed without creating or modifying application source files"
            )
        files = _read_workspace_files(workspace)
        _require_generated_project(files)
        validation = _validate_workspace(workspace)
        diagnostics.update(
            {
                "mode": "openhands_primary",
                "model": config["model"],
                "provider": _provider_name(config["model"]),
                "source_files_changed": True,
                "final_message": result.get("final_message", ""),
                "validation": validation,
            }
        )
        _raise_for_validation_errors(validation)
        write_json(run_id, "openhands_build.json", _redact_diagnostics(diagnostics))
        return files
    except Exception as exc:
        diagnostics["error"] = f"{type(exc).__name__}: {exc}"
        if _deterministic_fallback_enabled():
            return _deterministic_fallback(architecture, run_id, diagnostics, diagnostics["error"])
        write_json(run_id, "openhands_build.json", _redact_diagnostics(diagnostics))
        raise


def run_deterministic_build(architecture: dict, run_id: str) -> dict[str, str]:
    """Run the legacy fixed graph and return generated files as ``{path: content}``."""

    _validate_build_inputs(architecture, run_id)
    result = builder_graph.invoke({"architecture": architecture, "run_id": run_id, "code_files": {}})
    schema_result = result.get("schema_result", {})
    schema_errors = schema_result.get("errors", []) if isinstance(schema_result, Mapping) else []
    if schema_errors:
        raise RuntimeError(f"Builder schema application failed: {'; '.join(map(str, schema_errors))}")
    files = _normalise_generated_files(result.get("code_files", {}))
    if not files:
        raise RuntimeError("Builder graph produced no generated files")
    return assemble_project(files, architecture, run_id)


def _validate_build_inputs(architecture: dict, run_id: str) -> None:
    if not isinstance(architecture, dict):
        raise ValueError("architecture must be a dictionary")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id may contain only letters, numbers, underscores, and hyphens")
    validate_architecture(architecture)


def _apply_schema_phase(architecture: dict, run_id: str) -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return apply_database_schema(architecture["database_schema"])

    namespace = database_namespace(run_id)
    try:
        ensure_database_namespace(database_url, namespace)
    except Exception as exc:
        return {
            "tables_created": [],
            "errors": [f"PostgreSQL namespace setup failed: {type(exc).__name__}: {exc}"],
            "sql": [],
        }
    return apply_database_schema(
        architecture["database_schema"], database_url_for_namespace(database_url, namespace)
    )


def _raise_for_schema_errors(schema_result: Any) -> None:
    errors = schema_result.get("errors", []) if isinstance(schema_result, Mapping) else []
    if errors:
        raise RuntimeError(f"Builder schema application failed: {'; '.join(map(str, errors))}")


def _openhands_config() -> dict[str, str] | None:
    if not _openhands_enabled():
        return None
    api_key = _clean_key(os.getenv("OPENHANDS_API_KEY") or os.getenv("OPENHANDS_SMOKE_API_KEY") or "")
    model = (os.getenv("OPENHANDS_MODEL") or os.getenv("OPENHANDS_SMOKE_MODEL") or "").strip()
    if not api_key or not model:
        return None
    return {
        "model": model,
        "api_key": api_key,
        "base_url": os.getenv("OPENHANDS_BASE_URL") or os.getenv("OPENHANDS_SMOKE_BASE_URL") or "",
    }


def _prepare_openhands_workspace(
    run_id: str, architecture: dict, requirements: dict[str, Any], idea: str
) -> Path:
    workspace = output_dir(run_id) / "openhands_workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "architecture.json").write_text(
        json.dumps(architecture, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    (workspace / "requirements.json").write_text(
        json.dumps(requirements, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    (workspace / "TASK.md").write_text(_task_markdown(architecture, requirements, idea), encoding="utf-8")
    return workspace


def _run_openhands_authoring(
    config: dict[str, str],
    workspace: Path,
    architecture: dict,
    requirements: dict[str, Any],
    idea: str,
    run_id: str,
) -> dict[str, Any]:
    from openhands.sdk import LLM, Conversation
    from openhands.tools.preset.default import get_default_agent

    llm = LLM(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"] or None,
        max_output_tokens=_positive_int_env("OPENHANDS_BUILDER_MAX_OUTPUT_TOKENS", 2500),
        timeout=_positive_int_env("OPENHANDS_BUILDER_TIMEOUT_SECONDS", _DEFAULT_OPENHANDS_TIMEOUT_SECONDS),
        num_retries=0,
        reasoning_effort="none",
    )
    agent = get_default_agent(llm=llm, cli_mode=True)
    conversation = Conversation(
        agent=agent,
        workspace=str(workspace),
        persistence_dir=str(output_dir(run_id) / "openhands_persistence"),
        max_iteration_per_run=_positive_int_env(
            "OPENHANDS_BUILDER_MAX_ITERATIONS", _DEFAULT_OPENHANDS_MAX_ITERATIONS
        ),
        visualizer=None,
    )
    try:
        conversation.send_message(_openhands_task(architecture, requirements, idea))
        conversation.run()
        final_message = _final_agent_message(conversation)
    finally:
        conversation.close()
    return {"final_message": final_message}


def _openhands_task(architecture: dict, requirements: dict[str, Any], idea: str) -> str:
    return (
        "You are the primary code author for SWARM. Build the app in this empty workspace using actual source files, "
        "not a prose answer. Create a complete React + Vite frontend and Express + PostgreSQL backend unless the "
        "architecture explicitly says otherwise. Use architecture.json and requirements.json as the source of truth. "
        "You must create package.json, index.html, src/main.jsx, src/App.jsx, src/styles.css, server/index.js, "
        "server/setup-db.js, a README, and any helpers needed. Implement the named screens, fields, API routes, "
        "CRUD/search/edit/delete behavior, seed data, and localization plan. Keep all writes inside this workspace. "
        "The workspace terminal is Windows PowerShell. Prefer the file_editor tool for source files. Do not use Bash "
        "syntax such as `mkdir -p`, `&&`, or `cat <<`. When a terminal directory command is necessary, use "
        "`New-Item -ItemType Directory -Force` and PowerShell command separators. "
        "After writing source files, run npm install if needed and run the available check/test/build commands. "
        "Finish by reporting the files changed and commands run.\n\n"
        f"REQUESTED PRODUCT:\n{idea}\n\n"
        f"REQUIREMENTS:\n{json.dumps(requirements, indent=2, ensure_ascii=True)}\n\n"
        f"ARCHITECTURE:\n{json.dumps(architecture, indent=2, ensure_ascii=True)}"
    )


def _task_markdown(architecture: dict, requirements: dict[str, Any], idea: str) -> str:
    features = requirements.get("core_features", []) if isinstance(requirements, Mapping) else []
    return (
        "# SWARM Builder Task\n\n"
        f"Product prompt: {idea}\n\n"
        "Create the app source files in this workspace. The required architecture and requirements are in "
        "`architecture.json` and `requirements.json`.\n\n"
        f"Required screens: {', '.join(_names(architecture.get('ui_screens', [])))}\n\n"
        f"Required API routes: {', '.join(_route_names(architecture.get('api_routes', [])))}\n\n"
        f"Core features: {', '.join(map(str, features))}\n"
    )


def _validate_workspace(workspace: Path) -> dict[str, Any]:
    package_path = workspace / "package.json"
    if not package_path.exists():
        return {
            "status": "failed",
            "checks": [
                {
                    "name": "package.json",
                    "command": "read package.json",
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "OpenHands did not create package.json",
                }
            ],
        }

    package = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package.get("scripts") or {}
    checks: list[dict[str, Any]] = []
    timeout = _positive_int_env("OPENHANDS_VALIDATION_TIMEOUT_SECONDS", _DEFAULT_VALIDATION_TIMEOUT_SECONDS)
    if not (workspace / "node_modules").exists():
        checks.append(_run_command(workspace, "install", ["npm.cmd", "install"], timeout))
    for script_name in ("check", "test", "build"):
        if script_name in scripts:
            checks.append(_run_command(workspace, script_name, ["npm.cmd", "run", script_name], timeout))
    checks.extend(_runtime_probes(workspace, scripts))
    return {
        "status": "passed" if checks and all(check["returncode"] == 0 for check in checks) else "failed",
        "checks": checks,
    }


def _runtime_probes(workspace: Path, scripts: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not os.getenv("DATABASE_URL", "").strip():
        return [_skipped_probe("runtime_probe", "DATABASE_URL is unavailable")]

    server_script = "server" if "server" in scripts else "dev:server" if "dev:server" in scripts else ""
    if not server_script:
        return [_skipped_probe("runtime_probe", "npm server/dev:server script is unavailable")]

    timeout = _positive_int_env("OPENHANDS_RUNTIME_PROBE_SECONDS", 20)
    checks = [
        _probe_process(
            workspace,
            "api_probe",
            ["npm.cmd", "run", server_script],
            "http://127.0.0.1:3001/api/health",
            timeout,
        )
    ]

    client_script = "preview:client" if "preview:client" in scripts else "preview" if "preview" in scripts else ""
    if client_script:
        checks.append(
            _probe_process(
                workspace,
                "ui_probe",
                ["npm.cmd", "run", client_script],
                "http://127.0.0.1:4173/",
                timeout,
            )
        )
    else:
        checks.append(_skipped_probe("ui_probe", "npm preview/preview:client script is unavailable"))
    return checks


def _probe_process(
    root: Path, name: str, command: list[str], url: str, timeout_seconds: int
) -> dict[str, Any]:
    started_at = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while time.monotonic() - started_at < timeout_seconds:
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if 200 <= response.status < 500:
                        return _finish_probe(process, name, command, 0, f"Probed {url}: HTTP {response.status}", "")
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.5)
        return _finish_probe(process, name, command, 1, "", f"Could not probe {url} within {timeout_seconds} seconds")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def _finish_probe(
    process: subprocess.Popen,
    name: str,
    command: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    captured_stdout, captured_stderr = process.communicate(timeout=1) if process.poll() is not None else ("", "")
    return {
        "name": name,
        "command": " ".join(command),
        "returncode": returncode,
        "stdout": clean_process_output(stdout + "\n" + (captured_stdout or ""))[-5000:],
        "stderr": clean_process_output(stderr + "\n" + (captured_stderr or ""))[-5000:],
    }


def _skipped_probe(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "command": "",
        "returncode": 0,
        "stdout": "",
        "stderr": f"Skipped {name}: {reason}.",
        "duration_seconds": 0,
        "skipped": True,
    }


def _run_command(root: Path, name: str, command: list[str], timeout_seconds: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": result.returncode,
            "stdout": clean_process_output(result.stdout)[-5000:],
            "stderr": clean_process_output(result.stderr)[-5000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": 124,
            "stdout": clean_process_output(exc.stdout or "")[-5000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"Command timed out after {timeout_seconds} seconds",
        }


def _raise_for_validation_errors(validation: Mapping[str, Any]) -> None:
    if validation.get("status") == "passed":
        return
    failed = [
        f"{check.get('name')}: {check.get('stderr') or check.get('stdout') or check.get('returncode')}"
        for check in validation.get("checks", [])
        if check.get("returncode") != 0
    ]
    raise RuntimeError("OpenHands generated app validation failed: " + "; ".join(failed[:3]))


def _read_workspace_files(workspace: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace)
        if _EXCLUDED_PARTS.intersection(relative.parts):
            continue
        if relative.as_posix() in {"architecture.json", "requirements.json", "TASK.md"}:
            continue
        if path.suffix.lower() not in _SOURCE_SUFFIXES and path.name not in {".env.example"}:
            continue
        files[relative.as_posix()] = path.read_text(encoding="utf-8")
    return files


def _require_generated_project(files: Mapping[str, str]) -> None:
    required = {"package.json", "index.html", "src/main.jsx", "src/App.jsx", "server/index.js"}
    missing = sorted(required - set(files))
    if missing:
        raise RuntimeError(f"OpenHands did not create required source files: {', '.join(missing)}")


def _deterministic_fallback(
    architecture: dict,
    run_id: str,
    diagnostics: dict[str, Any],
    reason: str,
) -> dict[str, str]:
    files = run_deterministic_build(architecture, run_id)
    diagnostics.update(
        {
            "mode": "deterministic_fallback",
            "fallback_reason": reason,
            "source_files_changed": False,
            "validation": {"status": "not_run_for_fallback", "checks": []},
        }
    )
    write_json(run_id, "openhands_build.json", _redact_diagnostics(diagnostics))
    return files


def _deterministic_fallback_enabled() -> bool:
    return os.getenv("OPENHANDS_DETERMINISTIC_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _project_fingerprint(workspace: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace)
        if _EXCLUDED_PARTS.intersection(relative.parts):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _normalise_generated_files(generated: Any) -> dict[str, str]:
    if not isinstance(generated, Mapping):
        return {}
    files: dict[str, str] = {}
    for path, content in generated.items():
        if not isinstance(path, str) or not isinstance(content, str) or not content:
            raise RuntimeError("Builder graph returned an invalid generated file mapping")
        files[path] = content
    return files


def _final_agent_message(conversation: Any) -> str:
    from openhands.sdk.event import MessageEvent

    for event in reversed(list(conversation.state.events)):
        if isinstance(event, MessageEvent) and event.source == "agent":
            parts = [content.text for content in event.llm_message.content if hasattr(content, "text")]
            return "\n".join(parts).strip()
    return ""


def _clean_key(value: str) -> str:
    key = value.strip().strip('"').strip("'")
    return "" if key.lower() in _PLACEHOLDER_KEYS else key


def _provider_name(model: str) -> str:
    return model.split("/", maxsplit=1)[0] if "/" in model else "unknown"


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _openhands_enabled() -> bool:
    return os.getenv("OPENHANDS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _prepare_openhands_home(run_id: str) -> None:
    home = output_dir(run_id) / "openhands_home"
    (home / "AppData" / "Roaming").mkdir(parents=True, exist_ok=True)
    (home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ["APPDATA"] = str(home / "AppData" / "Roaming")
    os.environ["LOCALAPPDATA"] = str(home / "AppData" / "Local")
    os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")


def _redact_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(diagnostics, ensure_ascii=True)
    for key_name in ("OPENHANDS_API_KEY", "OPENHANDS_SMOKE_API_KEY"):
        secret = _clean_key(os.getenv(key_name, ""))
        if secret:
            encoded = encoded.replace(secret, "[redacted]")
    return json.loads(encoded)


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item.get("name", "")) for item in items if isinstance(item, Mapping) and item.get("name")]


def _route_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    routes = []
    for item in items:
        if isinstance(item, Mapping):
            routes.append(f"{item.get('method', '')} {item.get('path', '')}".strip())
    return [route for route in routes if route]


__all__ = ["run_build", "run_deterministic_build"]


if __name__ == "__main__":
    from backend.agents.architect import fallback_architecture

    example_architecture = fallback_architecture({})
    print(json.dumps(run_build(example_architecture, "builder-agent-standalone"), indent=2))
