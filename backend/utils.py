"""Filesystem and persistence utilities for SWARM runs."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_ROOT = Path(os.getenv("SWARM_OUTPUT_DIR", "outputs"))
RUN_SUMMARY_FILE = "summary.json"
GENERATED_APP_DIR = "generated-app"
VALIDATION_FILE = "validation.json"
QUALITY_FILE = "quality.json"
PREVIEW_API_PORT = 3001
PREVIEW_FRONTEND_PORT = 6200
PREVIEW_FILE = "preview.json"
PREVIEW_PROCESSES: dict[str, dict[str, subprocess.Popen[str]]] = {}


def ensure_output_root(root: str | Path | None = None) -> Path:
    """Create and return the output root directory."""
    output_root = Path(root) if root is not None else DEFAULT_OUTPUT_ROOT
    output_root.mkdir(parents=True, exist_ok=True)
    return output_root


def get_run_output_dir(
    run_id: str,
    root: str | Path | None = None,
    create: bool = True,
) -> Path:
    """Return the output directory for a run."""
    output_root = ensure_output_root(root)
    run_dir = _safe_child_path(output_root, run_id)
    if create:
        run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json(path: str | Path, data: Any) -> Path:
    """Write JSON data with stable formatting."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read JSON data, returning default when the file is absent."""
    source = Path(path)
    if not source.exists():
        return default
    return json.loads(source.read_text(encoding="utf-8"))


def strip_markdown_fences(text: str) -> str:
    """Remove a single wrapping Markdown code fence from text."""
    stripped = text.strip()
    fence_match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def extract_json_text(text: str) -> str:
    """Extract the first complete JSON object or array from model output."""
    stripped = strip_markdown_fences(text)
    starts = [index for index in (stripped.find("{"), stripped.find("[")) if index != -1]
    if not starts:
        raise ValueError("No JSON object or array found in text.")

    start = min(starts)
    opening = stripped[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(stripped)):
        char = stripped[index]

        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]

    raise ValueError("JSON text is incomplete.")


def repair_json_text(text: str) -> str:
    """Apply conservative repairs for common LLM JSON formatting mistakes."""
    repaired = extract_json_text(text)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
    return repaired


def parse_json_text(text: str) -> Any:
    """Parse JSON from raw text, fenced Markdown, or prose-wrapped output."""
    json_text = extract_json_text(text)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return json.loads(repair_json_text(json_text))


def write_text(path: str | Path, content: str) -> Path:
    """Write UTF-8 text content."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def read_text(path: str | Path, default: str | None = None) -> str | None:
    """Read UTF-8 text, returning default when the file is absent."""
    source = Path(path)
    if not source.exists():
        return default
    return source.read_text(encoding="utf-8")


def write_run_summary(
    run_id: str,
    summary: dict[str, Any],
    root: str | Path | None = None,
) -> Path:
    """Persist a run summary file."""
    return write_json(get_run_output_dir(run_id, root) / RUN_SUMMARY_FILE, summary)


def load_run_summary(
    run_id: str,
    root: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load a run summary file if it exists."""
    return read_json(get_run_output_dir(run_id, root, create=False) / RUN_SUMMARY_FILE)


def write_code_file(run_dir: str | Path, relative_path: str | Path, content: str) -> Path:
    """Write a generated code file below a run directory."""
    target = _safe_child_path(Path(run_dir), relative_path)
    return write_text(target, content)


def read_code_file(
    run_dir: str | Path,
    relative_path: str | Path,
    default: str | None = None,
) -> str | None:
    """Read a generated code file below a run directory."""
    target = _safe_child_path(Path(run_dir), relative_path)
    return read_text(target, default)


def get_generated_app_dir(run_id: str, root: str | Path | None = None) -> Path:
    """Return the materialized generated app directory for a run."""
    return get_run_output_dir(run_id, root, create=False) / GENERATED_APP_DIR


def materialize_generated_app(
    run_id: str,
    generated_files: dict[str, str],
    root: str | Path | None = None,
) -> Path:
    """Write a generated file map into the generated app directory."""
    run_dir = get_run_output_dir(run_id, root)
    app_dir = run_dir / GENERATED_APP_DIR
    for relative_path, content in generated_files.items():
        write_code_file(app_dir, relative_path, content)
    write_json(run_dir / "generated_files.json", sorted(generated_files.keys()))
    return app_dir


def collect_artifact_summary(
    run_id: str,
    state: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a compact summary of run artifacts."""
    run_dir = get_run_output_dir(run_id, root, create=False)
    app_dir = run_dir / GENERATED_APP_DIR
    generated_paths = _list_relative_files(app_dir) if app_dir.exists() else []

    summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "generated_app_dir": str(app_dir) if app_dir.exists() else None,
        "requirements": _artifact_file(run_dir / "requirements.json"),
        "architecture": _artifact_file(run_dir / "architecture.json"),
        "pitch_deck": _artifact_file(run_dir / "pitch_deck.json"),
        "summary": _artifact_file(run_dir / RUN_SUMMARY_FILE),
        "generated_files": generated_paths,
        "generated_file_count": len(generated_paths),
        "validation": read_json(run_dir / VALIDATION_FILE, default=None),
        "quality": read_json(run_dir / QUALITY_FILE, default=None),
    }
    if state:
        summary["status"] = state.get("status")
        summary["prompt"] = state.get("prompt")
    return summary


def zip_generated_app(run_id: str, root: str | Path | None = None) -> Path:
    """Create a zip archive for the materialized generated app."""
    run_dir = get_run_output_dir(run_id, root, create=False)
    app_dir = run_dir / GENERATED_APP_DIR
    if not app_dir.exists():
        raise FileNotFoundError(f"Generated app not found for run {run_id}.")

    zip_path = run_dir / "generated-app.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(path for path in app_dir.rglob("*") if path.is_file()):
            if _skip_zip_path(file_path):
                continue
            archive.write(file_path, file_path.relative_to(app_dir).as_posix())
    return zip_path


def validate_generated_app(
    run_id: str,
    root: str | Path | None = None,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Run generated app validation commands and persist their results."""
    run_dir = get_run_output_dir(run_id, root, create=False)
    app_dir = run_dir / GENERATED_APP_DIR
    if not app_dir.exists():
        result = {
            "run_id": run_id,
            "status": "failed",
            "app_dir": str(app_dir),
            "commands": [],
            "error": "Generated app directory does not exist.",
        }
        write_json(run_dir / VALIDATION_FILE, result)
        return result

    commands = [
        ["npm", "install"],
        ["npm", "run", "check"],
        ["npm", "run", "test"],
        ["npm", "run", "build"],
    ]
    results = [_run_command(command, app_dir, timeout_seconds) for command in commands]
    status = "passed" if all(item["returncode"] == 0 for item in results) else "failed"
    result = {
        "run_id": run_id,
        "status": status,
        "app_dir": str(app_dir),
        "commands": results,
    }
    write_json(run_dir / VALIDATION_FILE, result)
    return result


def score_generated_app_quality(
    run_id: str,
    state: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Score generated app quality using deterministic rubric checks."""
    run_dir = get_run_output_dir(run_id, root, create=False)
    app_dir = run_dir / GENERATED_APP_DIR
    requirements = read_json(run_dir / "requirements.json", default={})
    architecture = read_json(run_dir / "architecture.json", default={})
    pitch_deck = read_json(run_dir / "pitch_deck.json", default={})
    validation = read_json(run_dir / VALIDATION_FILE, default={})
    generated_files = _list_relative_files(app_dir) if app_dir.exists() else []

    scores = {
        "project_completeness": _score_project_completeness(generated_files),
        "dynamic_workflows": _score_dynamic_workflows(app_dir),
        "requirement_coverage": _score_requirement_coverage(requirements, architecture, pitch_deck),
        "localization_readiness": _score_localization_readiness(app_dir, requirements),
        "runnable_quality": 20 if validation.get("status") == "passed" else 8,
        "demo_polish": _score_demo_polish(app_dir, pitch_deck),
    }
    total = sum(scores.values())
    result = {
        "run_id": run_id,
        "score": total,
        "target": 90,
        "passed": total >= 90,
        "scores": scores,
        "validation_status": validation.get("status"),
        "generated_file_count": len(generated_files),
        "status": state.get("status") if state else None,
    }
    write_json(run_dir / QUALITY_FILE, result)
    return result


def prepare_preview_app(
    run_id: str,
    generated_files: dict[str, str] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Ensure the generated app exists for preview."""
    app_dir = get_generated_app_dir(run_id, root)
    if not app_dir.exists() and generated_files:
        app_dir = materialize_generated_app(run_id, generated_files, root)

    result = {
        "run_id": run_id,
        "status": "prepared" if app_dir.exists() else "missing",
        "app_dir": str(app_dir),
        "package_json": str(app_dir / "package.json"),
        "package_json_exists": (app_dir / "package.json").exists(),
    }
    _write_preview_status(run_id, result, root)
    return result


def install_preview_dependencies(
    run_id: str,
    root: str | Path | None = None,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Install generated app dependencies for preview."""
    app_dir = get_generated_app_dir(run_id, root)
    if not app_dir.exists():
        return _write_preview_status(
            run_id,
            {"run_id": run_id, "status": "missing", "error": "Generated app directory does not exist."},
            root,
        )

    command_result = _run_command(["npm", "install"], app_dir, timeout_seconds)
    status = "installed" if command_result["returncode"] == 0 else "install_failed"
    result = {
        "run_id": run_id,
        "status": status,
        "app_dir": str(app_dir),
        "install": command_result,
    }
    return _write_preview_status(run_id, result, root)


def start_preview(
    run_id: str,
    root: str | Path | None = None,
    api_port: int = PREVIEW_API_PORT,
    frontend_port: int = PREVIEW_FRONTEND_PORT,
) -> dict[str, Any]:
    """Start generated Express API and Vite frontend preview processes."""
    app_dir = get_generated_app_dir(run_id, root)
    if not app_dir.exists():
        return _write_preview_status(
            run_id,
            {"run_id": run_id, "status": "missing", "error": "Generated app directory does not exist."},
            root,
        )

    stop_preview(run_id, root)
    run_dir = get_run_output_dir(run_id, root, create=False)
    log_dir = run_dir / "preview-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    api_process = _start_preview_process(
        ["npm", "run", "server"],
        app_dir,
        log_dir / "api.log",
        {"PORT": str(api_port)},
    )
    frontend_process = _start_preview_process(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port)],
        app_dir,
        log_dir / "frontend.log",
        {"VITE_API_BASE": f"http://127.0.0.1:{api_port}"},
    )

    PREVIEW_PROCESSES[run_id] = {"api": api_process, "frontend": frontend_process}
    time.sleep(1)
    return get_preview_status(run_id, root)


def launch_preview(
    run_id: str,
    generated_files: dict[str, str] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare, install, and start generated app preview."""
    prepared = prepare_preview_app(run_id, generated_files, root)
    if prepared["status"] != "prepared":
        return prepared

    installed = install_preview_dependencies(run_id, root)
    if installed["status"] != "installed":
        return installed

    return start_preview(run_id, root)


def stop_preview(run_id: str, root: str | Path | None = None) -> dict[str, Any]:
    """Stop preview processes for a run."""
    processes = PREVIEW_PROCESSES.pop(run_id, {})
    stopped: dict[str, Any] = {}
    for name, process in processes.items():
        stopped[name] = _stop_process(process)

    status = get_preview_status(run_id, root)
    result = {
        **status,
        "status": "stopped",
        "stopped": stopped,
    }
    return _write_preview_status(run_id, result, root)


def get_preview_status(run_id: str, root: str | Path | None = None) -> dict[str, Any]:
    """Return current preview status and URLs."""
    app_dir = get_generated_app_dir(run_id, root)
    processes = PREVIEW_PROCESSES.get(run_id, {})
    api = _process_status(processes.get("api"))
    frontend = _process_status(processes.get("frontend"))
    running = api.get("running", False) and frontend.get("running", False)
    result = {
        "run_id": run_id,
        "status": "running" if running else "stopped",
        "app_dir": str(app_dir),
        "prepared": app_dir.exists(),
        "installed": (app_dir / "node_modules").exists(),
        "frontend_url": f"http://127.0.0.1:{PREVIEW_FRONTEND_PORT}",
        "api_url": f"http://127.0.0.1:{PREVIEW_API_PORT}",
        "api_health_url": f"http://127.0.0.1:{PREVIEW_API_PORT}/api/health",
        "api_metrics_url": f"http://127.0.0.1:{PREVIEW_API_PORT}/api/metrics",
        "processes": {
            "api": api,
            "frontend": frontend,
        },
    }
    return _write_preview_status(run_id, result, root)


def _run_command(command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    executable = shutil.which(command[0]) or command[0]
    resolved_command = [executable, *command[1:]]
    try:
        completed = subprocess.run(
            resolved_command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "error": f"Command timed out after {timeout_seconds} seconds.",
        }


def _start_preview_process(
    command: list[str],
    cwd: Path,
    log_path: Path,
    env_overrides: dict[str, str],
) -> subprocess.Popen[str]:
    executable = shutil.which(command[0]) or command[0]
    resolved_command = [executable, *command[1:]]
    env = {**os.environ, **env_overrides}
    log_file = log_path.open("a", encoding="utf-8")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        resolved_command,
        cwd=cwd,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        shell=False,
        creationflags=creationflags,
    )


def _stop_process(process: subprocess.Popen[str]) -> dict[str, Any]:
    if process.poll() is not None:
        return {"pid": process.pid, "returncode": process.returncode, "was_running": False}

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    else:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    return {"pid": process.pid, "returncode": process.poll(), "was_running": True}


def _process_status(process: subprocess.Popen[str] | None) -> dict[str, Any]:
    if process is None:
        return {"running": False, "pid": None, "returncode": None}
    return {
        "running": process.poll() is None,
        "pid": process.pid,
        "returncode": process.poll(),
    }


def _write_preview_status(
    run_id: str,
    status: dict[str, Any],
    root: str | Path | None = None,
) -> dict[str, Any]:
    run_dir = get_run_output_dir(run_id, root)
    write_json(run_dir / PREVIEW_FILE, status)
    return status


def _artifact_file(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def _list_relative_files(root: Path) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and "node_modules" not in path.relative_to(root).parts
        and "dist" not in path.relative_to(root).parts
    ]


def _skip_zip_path(path: Path) -> bool:
    return "node_modules" in path.parts or "dist" in path.parts


def _read_app_file(app_dir: Path, relative_path: str) -> str:
    return read_text(app_dir / relative_path, default="") or ""


def _score_project_completeness(generated_files: list[str]) -> int:
    required = {
        "package.json",
        "index.html",
        "vite.config.js",
        "README.md",
        "server/index.js",
        "server/dataStore.js",
        "server/app.test.js",
        "server/seed-data.json",
        "src/main.jsx",
        "src/api.js",
        "src/i18n.js",
        "src/App.jsx",
        "src/styles.css",
    }
    present = required.intersection(generated_files)
    return round(20 * (len(present) / len(required)))


def _score_dynamic_workflows(app_dir: Path) -> int:
    combined = "\n".join(
        [
            _read_app_file(app_dir, "server/index.js"),
            _read_app_file(app_dir, "server/dataStore.js"),
            _read_app_file(app_dir, "src/App.jsx"),
        ]
    )
    markers = ["createRecord", "updateRecord", "deleteRecord", "search", "status", "metrics"]
    return min(20, 4 * sum(1 for marker in markers if marker in combined))


def _score_requirement_coverage(
    requirements: dict[str, Any],
    architecture: dict[str, Any],
    pitch_deck: dict[str, Any],
) -> int:
    checks = [
        bool(requirements.get("core_workflows")),
        bool(requirements.get("features")),
        bool(requirements.get("dashboard_metrics")),
        bool(architecture.get("api_routes")),
        bool(architecture.get("database_schema")),
        bool(pitch_deck.get("key_features")),
    ]
    return min(15, round(15 * (sum(checks) / len(checks))))


def _score_localization_readiness(app_dir: Path, requirements: dict[str, Any]) -> int:
    i18n = _read_app_file(app_dir, "src/i18n.js")
    localization = requirements.get("localization", {})
    checks = [
        "labels" in i18n,
        "recordLabel" in i18n,
        "queueLabel" in i18n,
        bool(localization.get("language_ready")),
    ]
    return min(10, round(10 * (sum(checks) / len(checks))))


def _score_demo_polish(app_dir: Path, pitch_deck: dict[str, Any]) -> int:
    app = _read_app_file(app_dir, "src/App.jsx")
    styles = _read_app_file(app_dir, "src/styles.css")
    seed = read_json(app_dir / "server" / "seed-data.json", default=[])
    checks = [
        "metrics-grid" in app,
        "empty" in app.lower() or "No records" in app,
        "error" in app.lower(),
        bool(seed),
        bool(pitch_deck.get("demo_flow")),
        "@media" in styles,
    ]
    return min(15, round(15 * (sum(checks) / len(checks))))


def _safe_child_path(parent: Path, child: str | Path) -> Path:
    """Resolve child below parent and reject traversal outside parent."""
    parent_resolved = parent.resolve()
    target = (parent / child).resolve()

    try:
        target.relative_to(parent_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes allowed directory: {child}") from exc

    return target
