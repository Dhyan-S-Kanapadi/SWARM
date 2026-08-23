import json
import os
import re
from datetime import date, timedelta

from backend.agents.llm import allow_llm_fallback, call_llm_json, llm_provider_for_agent
from backend.state import ProjectState
from backend.utils import complete_agent, load_prompt, set_agent_status, write_json

MAX_TOKENS = 4800
MAX_REPAIR_ATTEMPTS = 2
ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
REQUIRED_ARCHITECTURE_FIELDS = {
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


class ArchitectureContractError(ValueError):
    """Raised when Architect output is structurally inconsistent."""


def run_architect(state: ProjectState) -> ProjectState:
    """Generate a build-ready architecture or fail before Builder can use it."""

    set_agent_status(state, "architect", "running")
    try:
        requirements = compact_requirements(state.get("requirements", {}))
        architecture, repairs = _generate_valid_architecture(requirements)
        state["architecture"] = architecture
        state.setdefault("llm_calls", []).append(
            {
                "agent": "architect",
                "provider": llm_provider_for_agent("architect"),
                "status": "repaired" if repairs else "success",
                "repair_attempts": repairs,
            }
        )
        complete_agent(state, "architect")
    except Exception as exc:
        if _allow_architect_fallback():
            state["architecture"] = fallback_architecture(state.get("requirements", {}))
            state.setdefault("llm_calls", []).append(
                {
                    "agent": "architect",
                    "provider": llm_provider_for_agent("architect"),
                    "status": "fallback",
                    "detail": str(exc),
                }
            )
            complete_agent(state, "architect")
        else:
            set_agent_status(state, "architect", "error")
            state["fatal_error"] = True
            raise RuntimeError(
                "Architect did not produce a build-ready architecture after repair attempts: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    write_json(state["run_id"], "architecture.json", state["architecture"])
    return state


def _generate_valid_architecture(requirements: dict) -> tuple[dict, int]:
    system_prompt = load_prompt("architect_prompt.txt")
    candidate = call_llm_json(
        agent_name="architect",
        system_prompt=system_prompt,
        user_content=json.dumps(requirements, separators=(",", ":")),
        temperature=0.25,
        max_tokens=MAX_TOKENS,
    )

    for repair_attempt in range(_repair_attempt_limit() + 1):
        try:
            candidate = complete_known_contract_defaults(candidate)
            validate_architecture_contract(candidate)
            return candidate, repair_attempt
        except ArchitectureContractError as exc:
            if repair_attempt >= _repair_attempt_limit():
                raise
            candidate = call_llm_json(
                agent_name="architect",
                system_prompt=system_prompt,
                user_content=_architecture_repair_request(candidate, str(exc)),
                temperature=0.1,
                max_tokens=MAX_TOKENS,
            )
    raise AssertionError("architecture repair loop ended unexpectedly")


def complete_known_contract_defaults(candidate: dict) -> dict:
    """Fill stable implementation metadata that does not change the product design.

    Some hosted models omit individual ``state_management`` subkeys while
    otherwise returning a complete domain architecture. These defaults describe
    the existing React/Express generation pattern and avoid an unnecessary
    second LLM call solely for generic implementation metadata.
    """

    if not isinstance(candidate, dict):
        return candidate
    completed = dict(candidate)
    schema = completed.get("database_schema")
    if isinstance(schema, dict) and isinstance(schema.get("tables"), list):
        table_map = {}
        for table in schema["tables"]:
            if not isinstance(table, dict):
                continue
            table_name = table.get("name") or table.get("table_name")
            if not isinstance(table_name, str) or not table_name:
                continue
            table_map[table_name] = {
                key: value
                for key, value in table.items()
                if key not in {"name", "table_name"}
            }
        if table_map:
            completed["database_schema"] = table_map

    routes = completed.get("api_routes")
    screens = completed.get("ui_screens")
    if isinstance(routes, list):
        normalized_routes = []
        for route in routes:
            if not isinstance(route, dict):
                normalized_routes.append(route)
                continue
            rules = route.get("validation_rules")
            if rules is None:
                rules = []
            elif isinstance(rules, str):
                rules = [rules]
            elif not isinstance(rules, list):
                rules = [str(rules)]
            normalized_routes.append(
                {
                    **route,
                    "request_body": _normalise_request_body(route.get("request_body")),
                    "validation_rules": rules,
                }
            )
        completed["api_routes"] = normalized_routes
        routes = completed["api_routes"]

        # An auth endpoint is an explicit product requirement, not a reason to
        # speculate. Complete the omitted flag so the deterministic Builder
        # installs its session middleware and UI consistently.
        if "auth" not in completed and any(
            isinstance(route, dict) and str(route.get("path", "")).startswith("/api/auth/")
            for route in routes
        ):
            completed["auth"] = {"required": True}

    if isinstance(routes, list) and isinstance(screens, list):
        route_paths = {
            route.get("path")
            for route in routes
            if isinstance(route, dict) and isinstance(route.get("path"), str)
        }
        read_paths = [
            route["path"]
            for route in routes
            if isinstance(route, dict) and route.get("method", "").upper() == "GET"
            and route.get("path") in route_paths
        ]
        normalized_screens = []
        for screen in screens:
            if not isinstance(screen, dict):
                normalized_screens.append(screen)
                continue
            data_needed = screen.get("data_needed")
            normalized_screens.append(
                {
                    **screen,
                    "data_needed": read_paths if data_needed is None else data_needed,
                }
            )
        completed["ui_screens"] = normalized_screens

    if not isinstance(completed.get("state_management"), dict):
        return completed
    defaults = {
        "frontend_state": ["screen data", "forms", "filters", "locale", "loading", "error"],
        "server_state": "PostgreSQL data accessed through declared API routes",
        "forms": "controlled forms validate fields declared by the architecture",
        "filters": "screen filters map to declared API query parameters",
        "optimistic_updates": "refetch route data after successful mutations",
    }
    completed["state_management"] = {**defaults, **completed["state_management"]}
    return completed


def _normalise_request_body(value):
    """Convert a model's ``{field_one, field_two}`` shorthand to an object."""

    if value is None or isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in {"", "null", "none"}:
        return None
    if not (text.startswith("{") and text.endswith("}")):
        return value
    fields = [item.strip().rstrip("?").replace(" ", "_") for item in text[1:-1].split(",")]
    if not fields or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field) for field in fields):
        return value
    return {field: "string" for field in fields}


def _architecture_repair_request(candidate: dict, error: str) -> str:
    """Request a contract repair without duplicating the original requirements.

    The candidate already contains the proposed architecture. Re-sending requirements
    can push a repair request over smaller hosted-model TPM limits.
    """

    return json.dumps(
        {
            "task": "Repair the previous architecture. Return only the complete JSON object required by the system prompt.",
            "validation_error": error,
            "required_top_level_keys": sorted(REQUIRED_ARCHITECTURE_FIELDS),
            "previous_architecture": candidate,
        },
        separators=(",", ":"),
    )


def _repair_attempt_limit() -> int:
    try:
        return max(0, int(os.getenv("SWARM_ARCHITECT_REPAIR_ATTEMPTS", str(MAX_REPAIR_ATTEMPTS))))
    except ValueError:
        return MAX_REPAIR_ATTEMPTS


def _allow_architect_fallback() -> bool:
    """Permit the demo architecture only when explicitly requested for development."""

    return (
        allow_llm_fallback()
        and os.getenv("SWARM_ALLOW_ARCHITECT_CONTRACT_FALLBACK", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )


def compact_requirements(requirements: dict) -> dict:
    return {
        "problem_statement": _shorten(requirements.get("problem_statement", "")),
        "target_audience": _shorten(requirements.get("target_audience", "")),
        "local_context": requirements.get("local_context", {}),
        "core_features": _short_list(requirements.get("core_features", []), 8),
        "business_rules": _short_list(requirements.get("business_rules", []), 8),
        "automation_requirements": _short_objects(requirements.get("automation_requirements", []), 5),
        "localization_requirements": requirements.get("localization_requirements", {}),
        "data_entities": _short_objects(requirements.get("data_entities", []), 5),
        "workflow_map": _short_objects(requirements.get("workflow_map", []), 5),
        "seed_data": _short_list(requirements.get("seed_data", []), 6),
        "acceptance_criteria": _short_list(requirements.get("acceptance_criteria", []), 6),
    }


def _short_list(items, limit: int) -> list:
    if not isinstance(items, list):
        return []
    return [_shorten(item) for item in items[:limit]]


def _short_objects(items, limit: int) -> list:
    if not isinstance(items, list):
        return []
    compacted = []
    for item in items[:limit]:
        if isinstance(item, dict):
            compacted.append({key: _shorten(value) for key, value in item.items()})
        else:
            compacted.append(_shorten(item))
    return compacted


def _shorten(value, limit: int = 180):
    if isinstance(value, list):
        return [_shorten(item, limit) for item in value[:6]]
    if isinstance(value, dict):
        return {key: _shorten(item, limit) for key, item in value.items()}
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def fallback_architecture(requirements: dict) -> dict:
    app_name = "swarm-localops"
    return {
        "tech_stack": {
            "frontend": "React with Vite",
            "backend": "Node.js with Express",
            "database": "PostgreSQL persistence with seed data",
            "styling": "Plain CSS responsive dashboard",
            "testing": "Node test runner plus vite build",
            "local_run_strategy": "npm install, npm run dev, npm run check, npm run test, npm run build",
        },
        "app_shell": {
            "app_name": app_name,
            "navigation": ["Dashboard", "Records", "Form", "Language switcher"],
            "primary_dashboard_widgets": ["total records", "open records", "upcoming records", "revenue"],
            "empty_states": ["No records match filters", "Loading records", "Validation error"],
            "responsive_requirements": "Single-column mobile layout and two-column desktop layout",
        },
        "database_schema": {
            "work_items": {
                "fields": {
                    "id": "integer primary key",
                    "customerName": "string required",
                    "phone": "string",
                    "title": "string required",
                    "category": "string",
                    "status": "enum new|confirmed|in_progress|completed",
                    "priority": "enum low|medium|high",
                    "dueDate": "date required",
                    "amount": "number",
                    "notes": "string",
                    "language": "string",
                },
                "indexes": ["status", "dueDate", "customerName"],
                "relationships": [],
                "seed_records": fallback_seed_records(requirements),
            }
        },
        "api_routes": [
            {
                "method": "GET",
                "path": "/api/health",
                "description": "Health check",
                "request_body": None,
                "response_shape": {"ok": True},
                "validation_rules": [],
            },
            {
                "method": "GET",
                "path": "/api/items",
                "description": "List, search, and filter records",
                "request_body": None,
                "response_shape": [{"id": "number", "customerName": "string"}],
                "validation_rules": ["status query is optional", "search query is optional"],
            },
            {
                "method": "POST",
                "path": "/api/items",
                "description": "Create record",
                "request_body": {"customerName": "string", "title": "string", "dueDate": "date", "status": "string"},
                "response_shape": {"id": "number"},
                "validation_rules": ["customerName required", "title required", "dueDate required", "valid status"],
            },
            {
                "method": "PUT",
                "path": "/api/items/:id",
                "description": "Update record",
                "request_body": {"status": "string"},
                "response_shape": {"id": "number"},
                "validation_rules": ["record must exist", "valid status"],
            },
            {
                "method": "DELETE",
                "path": "/api/items/:id",
                "description": "Delete record",
                "request_body": None,
                "response_shape": None,
                "validation_rules": ["id must exist or no-op"],
            },
            {
                "method": "GET",
                "path": "/api/metrics",
                "description": "Dashboard metrics",
                "request_body": None,
                "response_shape": {"total": "number", "open": "number", "upcoming": "number", "revenue": "number"},
                "validation_rules": [],
            },
        ],
        "ui_screens": [
            {
                "name": "Dashboard",
                "route": "/",
                "purpose": "Show metrics and operational status",
                "data_needed": ["/api/metrics", "/api/items"],
                "primary_actions": ["filter", "search", "reset demo data"],
                "states": ["loading", "error", "empty", "ready"],
            },
            {
                "name": "Record form",
                "route": "/",
                "purpose": "Create and edit work records",
                "data_needed": ["/api/items"],
                "primary_actions": ["create", "edit", "delete"],
                "states": ["validation error", "saving", "ready"],
            },
        ],
        "project_modules": [
            {"name": "server", "responsibility": "Express API and persistence", "files": ["server/index.js", "server/dataStore.js"]},
            {"name": "frontend", "responsibility": "React dashboard and CRUD UI", "files": ["src/App.jsx", "src/api.js", "src/i18n.js"]},
            {"name": "tests", "responsibility": "Data workflow test", "files": ["server/app.test.js"]},
        ],
        "state_management": {
            "frontend_state": ["items", "metrics", "form", "filters", "locale", "loading", "error"],
            "server_state": "local JSON file resettable from seed-data.json",
            "forms": "controlled React form with required fields",
            "filters": "search and status query params",
            "optimistic_updates": "reload after mutation for reliability",
        },
        "localization_plan": {
            "language_files": ["src/i18n.js"],
            "default_locale": "en",
            "locale_switching": "dropdown in topbar",
            "translated_surfaces": ["labels", "buttons", "empty states", "navigation"],
            "formatting_rules": "Intl DateTimeFormat and NumberFormat for India",
        },
        "automation_jobs": [
            {
                "name": "metric calculation",
                "schedule_or_trigger": "on metrics API request",
                "logic": "aggregate total/open/completed/upcoming/revenue from records",
                "user_visible_result": "dashboard widgets update",
            }
        ],
        "validation_plan": [
            {"scenario": "create record", "steps": ["fill form", "save"], "expected_result": "record appears in list"},
            {"scenario": "filter records", "steps": ["select status"], "expected_result": "only matching records show"},
            {"scenario": "language switch", "steps": ["choose Hindi or Kannada"], "expected_result": "labels translate"},
        ],
        "folder_structure": "package.json\nindex.html\nserver/\n  index.js\n  dataStore.js\n  seed-data.json\n  app.test.js\nsrc/\n  main.jsx\n  App.jsx\n  api.js\n  i18n.js\n  styles.css\nREADME.md",
        "build_constraints": ["no paid APIs", "local-first", "must pass npm run check/test/build", "responsive UI"],
    }


def validate_architecture_contract(architecture: dict) -> None:
    """Reject incomplete or cross-field-inconsistent Architect output."""

    if not isinstance(architecture, dict):
        raise ArchitectureContractError("architecture must be a dictionary")
    missing = sorted(REQUIRED_ARCHITECTURE_FIELDS - set(architecture))
    unexpected = sorted(set(architecture) - REQUIRED_ARCHITECTURE_FIELDS - {"auth"})
    if missing:
        raise ArchitectureContractError(f"architecture is missing required fields: {', '.join(missing)}")
    if unexpected:
        raise ArchitectureContractError(f"architecture has unsupported fields: {', '.join(unexpected)}")

    _require_object_keys(architecture, "tech_stack", {"frontend", "backend", "database", "styling", "testing", "local_run_strategy"})
    _require_object_keys(
        architecture,
        "app_shell",
        {"app_name", "navigation", "primary_dashboard_widgets", "empty_states", "responsive_requirements"},
    )
    _require_object_keys(
        architecture,
        "state_management",
        {"frontend_state", "server_state", "forms", "filters", "optimistic_updates"},
    )
    _require_object_keys(
        architecture,
        "localization_plan",
        {"language_files", "default_locale", "locale_switching", "translated_surfaces", "formatting_rules"},
    )
    for key in ("project_modules", "automation_jobs", "validation_plan", "build_constraints"):
        if not isinstance(architecture[key], list):
            raise ArchitectureContractError(f"architecture.{key} must be a list")
    if not isinstance(architecture["folder_structure"], str) or not architecture["folder_structure"].strip():
        raise ArchitectureContractError("architecture.folder_structure must be a non-empty string")

    database_schema = architecture["database_schema"]
    if not isinstance(database_schema, dict) or not database_schema:
        raise ArchitectureContractError("database_schema must define at least one table")
    for table_name, table in database_schema.items():
        if not isinstance(table, dict) or not isinstance(table.get("fields"), dict) or not table["fields"]:
            raise ArchitectureContractError(f"table {table_name} must define fields")
        fields = set(table["fields"])
        seed_records = table.get("seed_records", [])
        if not isinstance(seed_records, list):
            raise ArchitectureContractError(f"table {table_name} seed_records must be a list")
        for record in seed_records:
            if not isinstance(record, dict):
                raise ArchitectureContractError(f"table {table_name} seed records must be objects")
            unknown = sorted(set(record) - fields)
            if unknown:
                raise ArchitectureContractError(
                    f"table {table_name} seed record has unknown fields: {', '.join(unknown)}"
                )

    if not isinstance(architecture["api_routes"], list) or not architecture["api_routes"]:
        raise ArchitectureContractError("api_routes must be a non-empty list")
    route_paths = set()
    route_endpoints = set()
    for route in architecture["api_routes"]:
        if not isinstance(route, dict):
            raise ArchitectureContractError("api_routes entries must be objects")
        route_missing = {"method", "path", "description", "request_body", "response_shape", "validation_rules"} - set(route)
        if route_missing:
            raise ArchitectureContractError(f"api route is missing fields: {', '.join(sorted(route_missing))}")
        method = route["method"]
        path = route["path"]
        if not isinstance(method, str) or method.upper() not in ALLOWED_HTTP_METHODS:
            raise ArchitectureContractError(f"api route has unsupported method: {method!r}")
        if method != method.upper():
            raise ArchitectureContractError(f"api route method must be uppercase: {method!r}")
        if not isinstance(path, str) or not path.startswith("/api/") or any(char.isspace() for char in path):
            raise ArchitectureContractError("api route paths must start with /api/")
        endpoint = (method, path)
        if endpoint in route_endpoints:
            raise ArchitectureContractError(f"api route is duplicated: {method} {path}")
        route_endpoints.add(endpoint)
        if not isinstance(route["description"], str) or not route["description"].strip():
            raise ArchitectureContractError(f"api route {method} {path} must have a description")
        if route["request_body"] is not None and not isinstance(route["request_body"], dict):
            raise ArchitectureContractError(f"api route {method} {path} request_body must be an object or null")
        rules = route["validation_rules"]
        if not isinstance(rules, list) or not all(isinstance(rule, str) for rule in rules):
            raise ArchitectureContractError(f"api route {method} {path} validation_rules must be a list of strings")
        route_paths.add(path)

    auth_config = architecture.get("auth")
    auth_route_declared = any(path.startswith("/api/auth/") for path in route_paths)
    auth_required = auth_config is True or (
        isinstance(auth_config, dict) and auth_config.get("required") is True
    )
    if auth_config is not None and not isinstance(auth_config, (bool, dict)):
        raise ArchitectureContractError("architecture.auth must be a boolean or object")
    if auth_route_declared and not auth_required:
        raise ArchitectureContractError("auth API routes require auth.required to be true")

    if not isinstance(architecture["ui_screens"], list) or not architecture["ui_screens"]:
        raise ArchitectureContractError("ui_screens must be a non-empty list")
    for screen in architecture["ui_screens"]:
        if not isinstance(screen, dict):
            raise ArchitectureContractError("ui_screens entries must be objects")
        screen_missing = {"name", "route", "purpose", "data_needed", "primary_actions", "states"} - set(screen)
        if screen_missing:
            raise ArchitectureContractError(f"ui screen is missing fields: {', '.join(sorted(screen_missing))}")
        if not isinstance(screen["name"], str) or not screen["name"].strip():
            raise ArchitectureContractError("ui screen name must be a non-empty string")
        if not isinstance(screen["route"], str) or not screen["route"].startswith("/"):
            raise ArchitectureContractError(f"screen {screen['name']} route must start with /")
        data_needed = screen["data_needed"]
        if not isinstance(data_needed, list) or not data_needed or not all(isinstance(path, str) for path in data_needed):
            raise ArchitectureContractError(f"screen {screen['name']} data_needed must be a non-empty list of API paths")
        if not isinstance(screen["primary_actions"], list) or not isinstance(screen["states"], list):
            raise ArchitectureContractError(f"screen {screen['name']} actions and states must be lists")
        for path in data_needed:
            if path not in route_paths:
                raise ArchitectureContractError(
                    f"screen {screen.get('name', '(unnamed)')} needs missing API route {path}"
                )


def _require_object_keys(architecture: dict, name: str, required_keys: set[str]) -> None:
    value = architecture.get(name)
    if not isinstance(value, dict):
        raise ArchitectureContractError(f"architecture.{name} must be an object")
    missing = sorted(required_keys - set(value))
    if missing:
        raise ArchitectureContractError(f"architecture.{name} is missing fields: {', '.join(missing)}")


def fallback_seed_records(requirements: dict) -> list[dict]:
    """Translate Analyst seed examples into rows matching fallback work_items."""

    raw_seeds = requirements.get("seed_data", [])
    if not isinstance(raw_seeds, list):
        return []

    candidates: list[tuple[str, dict]] = []
    for seed in raw_seeds:
        if isinstance(seed, str):
            candidates.append(("Demo", {"title": seed}))
            continue
        if not isinstance(seed, dict):
            continue
        nested_records = seed.get("records")
        if isinstance(nested_records, list):
            entity = str(seed.get("entity") or "Demo")
            candidates.extend((entity, record) for record in nested_records if isinstance(record, dict))
        else:
            candidates.append((str(seed.get("entity") or "Demo"), seed))

    due_date = (date.today() + timedelta(days=7)).isoformat()
    records = []
    for index, (entity, candidate) in enumerate(candidates[:8], start=1):
        raw_status = str(candidate.get("status") or "new").lower()
        status = raw_status if raw_status in {"new", "confirmed", "in_progress", "completed"} else "new"
        customer_name = (
            candidate.get("customerName")
            or candidate.get("full_name")
            or candidate.get("name")
            or f"Demo {entity} {index}"
        )
        title = candidate.get("title") or candidate.get("name") or f"{entity} record"
        candidate_due_date = candidate.get("dueDate") or candidate.get("start_time") or due_date
        records.append(
            {
                "id": index,
                "customerName": str(customer_name),
                "phone": str(candidate.get("phone") or ""),
                "title": str(title),
                "category": entity.lower(),
                "status": status,
                "priority": "medium",
                "dueDate": str(candidate_due_date)[:10],
                "amount": candidate.get("amount") or candidate.get("price") or 0,
                "notes": str(candidate.get("notes") or "Generated demo record"),
                "language": str(candidate.get("preferred_language") or "en"),
            }
        )
    return records
