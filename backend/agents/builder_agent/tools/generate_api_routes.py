"""Generate an Express/PostgreSQL API server from an Architect route contract.

The returned mapping uses the same ``{relative_path: file_content}`` shape as
the deterministic Builder LangGraph. It intentionally generates
only ``server/index.js``; the eventual project package manifest must include the
Node ``pg`` dependency before the generated application is installed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from textwrap import dedent
from typing import Any


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def generate_api_routes(
    api_routes: Sequence[Mapping[str, Any]], database_schema: Mapping[str, Any]
) -> dict[str, str]:
    """Generate a PostgreSQL-backed ``server/index.js`` from Architect output.

    Raises ``ValueError`` for an incomplete or ambiguous route/schema contract so
    a future builder agent can stop and report the architecture issue instead of
    emitting a server connected to the wrong table.
    """

    tables = _normalise_tables(database_schema)
    routes = _normalise_routes(api_routes, tables)
    content = _SERVER_TEMPLATE.replace("__TABLES__", json.dumps(tables, indent=2))
    content = content.replace("__ROUTES__", json.dumps(routes, indent=2))
    return {"server/index.js": dedent(content).strip() + "\n"}


def _normalise_tables(database_schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(database_schema, Mapping) or not database_schema:
        raise ValueError("database_schema must be a non-empty dictionary of tables")

    tables: dict[str, dict[str, Any]] = {}
    for table_name, table_spec in database_schema.items():
        _validate_identifier(table_name, "table name")
        if not isinstance(table_spec, Mapping):
            raise ValueError(f"table '{table_name}' must be a dictionary")
        fields = table_spec.get("fields")
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError(f"table '{table_name}' must define a non-empty fields dictionary")

        columns: dict[str, dict[str, Any]] = {}
        primary_key: str | None = None
        for field_name, declaration in fields.items():
            _validate_identifier(field_name, f"field name for table '{table_name}'")
            if not isinstance(declaration, str) or not declaration.strip():
                raise ValueError(f"field '{field_name}' on table '{table_name}' needs a string declaration")
            normalized = declaration.lower()
            columns[field_name] = {
                "required": "required" in normalized or "not null" in normalized,
                "enum": _enum_values(normalized),
                "text": any(word in normalized for word in ("string", "text", "uuid", "varchar", "character varying")),
            }
            if "primary key" in normalized:
                if primary_key:
                    raise ValueError(f"table '{table_name}' defines more than one primary key")
                primary_key = field_name

        tables[table_name] = {
            "columns": columns,
            "primaryKey": primary_key or ("id" if "id" in columns else None),
        }
    return tables


def _normalise_routes(
    api_routes: Sequence[Mapping[str, Any]], tables: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(api_routes, Sequence) or isinstance(api_routes, (str, bytes)):
        raise ValueError("api_routes must be a list")

    normalised: list[dict[str, Any]] = []
    for route in api_routes:
        if not isinstance(route, Mapping):
            raise ValueError("each api route must be a dictionary")
        required_keys = {"method", "path", "description", "request_body", "response_shape", "validation_rules"}
        missing = sorted(required_keys - set(route))
        if missing:
            raise ValueError(f"api route is missing required keys: {', '.join(missing)}")

        method = str(route["method"]).upper()
        path = route["path"]
        if method not in _SUPPORTED_METHODS:
            raise ValueError(f"unsupported HTTP method '{method}'")
        if not isinstance(path, str) or not path.startswith("/api/"):
            raise ValueError(f"route path '{path}' must start with /api/")
        if not isinstance(route["request_body"], (Mapping, type(None))):
            raise ValueError(f"request_body for '{path}' must be an object or null")
        if not isinstance(route["validation_rules"], list):
            raise ValueError(f"validation_rules for '{path}' must be a list")

        operation = _route_operation(method, path, route["description"])
        table_name = None if operation in {"health", "auth_login", "settings_locales"} else _resolve_table(path, tables)
        if operation in {"update", "delete", "get_one"} and not tables[table_name]["primaryKey"]:
            raise ValueError(f"route '{method} {path}' needs a table with a primary key")

        body_fields = list(route["request_body"] or {})
        if table_name:
            unknown_fields = set(body_fields) - set(tables[table_name]["columns"])
            if unknown_fields:
                raise ValueError(
                    f"route '{method} {path}' references fields not on '{table_name}': {', '.join(sorted(unknown_fields))}"
                )

        normalised.append(
            {
                "method": method,
                "path": path,
                "description": str(route["description"]),
                "operation": operation,
                "table": table_name,
                "bodyFields": body_fields,
                "derivedFields": _derived_fields(route["validation_rules"], tables.get(table_name, {}).get("columns", {})),
                "validationRules": [str(rule) for rule in route["validation_rules"]],
                "responseShape": route["response_shape"],
            }
        )
    if not any(route["method"] == "GET" and route["path"] == "/api/health" for route in normalised):
        normalised.insert(
            0,
            {
                "method": "GET",
                "path": "/api/health",
                "description": "Generated application health check",
                "operation": "health",
                "table": None,
                "bodyFields": [],
                "derivedFields": {},
                "validationRules": [],
                "responseShape": {"ok": True},
            },
        )
    return normalised


def _derived_fields(rules: Sequence[Any], columns: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Translate deterministic date arithmetic rules into API defaults.

    Architect commonly describes a calculated due date as ``due_date =
    loan_date+14``. The client should not have to invent that field, so the
    generated server calculates it before inserting the row.
    """

    derived: dict[str, dict[str, Any]] = {}
    for rule in rules:
        match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*(\d+)\b", str(rule))
        if not match:
            continue
        field, source, days = match.groups()
        if field in columns and source in columns:
            derived[field] = {"source": source, "days": int(days)}
    return derived


def _route_operation(method: str, path: str, description: Any) -> str:
    description_text = str(description).lower()
    if path == "/api/health" or "health check" in description_text:
        return "health"
    if path == "/api/auth/login" and method == "POST":
        return "auth_login"
    if path == "/api/settings/locales" and method == "GET":
        return "settings_locales"
    if path.rstrip("/").endswith("/overdue") and method == "GET":
        return "list_overdue"
    if path.rstrip("/").endswith("/return") and method in {"PUT", "PATCH"}:
        return "return_record"
    if path.rstrip("/").endswith("/read") and method in {"PUT", "PATCH"}:
        return "mark_read"
    if "metric" in path.lower() or "metric" in description_text:
        return "metrics"
    has_id = ":" in path
    if method == "GET":
        return "get_one" if has_id else "list"
    if method == "POST":
        return "create"
    if method in {"PUT", "PATCH"}:
        return "update"
    return "delete"


def _resolve_table(path: str, tables: Mapping[str, Mapping[str, Any]]) -> str:
    if len(tables) == 1:
        return next(iter(tables))

    segments = [segment for segment in path.lower().split("/") if segment and segment != "api" and not segment.startswith(":")]
    candidates = [
        table_name
        for table_name in tables
        if any(_table_matches_resource(table_name, segment) for segment in segments)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"cannot map route '{path}' to a database table")
    raise ValueError(f"route '{path}' maps ambiguously to tables: {', '.join(candidates)}")


def _table_matches_resource(table_name: str, resource: str) -> bool:
    table_parts = table_name.lower().split("_")
    table_forms = {_singular(table_name.lower()), table_name.lower(), _singular(table_parts[-1]), table_parts[-1]}
    resource_forms = {resource, _singular(resource)}
    return bool(table_forms & resource_forms)


def _singular(value: str) -> str:
    return value[:-1] if value.endswith("s") else value


def _enum_values(declaration: str) -> list[str]:
    if not declaration.strip().startswith("enum "):
        return []
    return [value.strip() for value in declaration.strip()[5:].split("|") if value.strip()]


def _validate_identifier(value: Any, description: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{description} '{value}' is not a valid SQL identifier")


_SERVER_TEMPLATE = r'''
import cors from "cors";
import express from "express";
import pg from "pg";

const { Pool } = pg;
const app = express();
const port = Number(process.env.PORT || 3001);
const databaseUrl = process.env.DATABASE_URL;
const tables = __TABLES__;
const routes = __ROUTES__;

if (!databaseUrl) {
  throw new Error("DATABASE_URL must be set before starting the generated API server.");
}

const pool = new Pool({ connectionString: databaseUrl });

app.use(cors());
app.use(express.json({ limit: "1mb" }));

function quoteIdentifier(identifier) {
  return `"${identifier.replace(/"/g, '""')}"`;
}

function sendDatabaseError(error, res) {
  console.error(error);
  res.status(500).json({ error: "Database operation failed" });
}

function validatePayload(route, table, payload) {
  if (!payload || Array.isArray(payload) || typeof payload !== "object") {
    return "Request body must be a JSON object";
  }

  const allowedFields = new Set(route.bodyFields);
  const unexpected = Object.keys(payload).filter((field) => !allowedFields.has(field));
  if (unexpected.length) {
    return `Unexpected fields: ${unexpected.join(", ")}`;
  }

  for (const field of route.bodyFields) {
    const requiredBySchema = table.columns[field].required;
    const requiredByRoute = route.validationRules.some((rule) =>
      rule.toLowerCase().includes(`${field.toLowerCase()} required`)
    );
    if ((requiredBySchema || requiredByRoute) && (payload[field] === undefined || payload[field] === null || payload[field] === "")) {
      return `${field} is required`;
    }
    const allowedValues = table.columns[field].enum;
    if (payload[field] !== undefined && allowedValues.length && !allowedValues.includes(String(payload[field]))) {
      return `${field} must be one of: ${allowedValues.join(", ")}`;
    }
  }
  return null;
}

async function listRows(route, req, res) {
  const table = tables[route.table];
  const clauses = [];
  const values = [];
  const textColumns = Object.entries(table.columns)
    .filter(([, definition]) => definition.text)
    .map(([column]) => quoteIdentifier(column));

  for (const [key, value] of Object.entries(req.query)) {
    if (key === "search" && textColumns.length) {
      values.push(`%${String(value).toLowerCase()}%`);
      const placeholder = `$${values.length}`;
      clauses.push(`(${textColumns.map((column) => `LOWER(CAST(${column} AS TEXT)) LIKE ${placeholder}`).join(" OR ")})`);
    } else if (Object.hasOwn(table.columns, key) && value !== "all") {
      values.push(value);
      clauses.push(`${quoteIdentifier(key)} = $${values.length}`);
    }
  }

  const orderColumn = table.columns.dueDate ? "dueDate" : table.primaryKey;
  const where = clauses.length ? ` WHERE ${clauses.join(" AND ")}` : "";
  const orderBy = orderColumn ? ` ORDER BY ${quoteIdentifier(orderColumn)}` : "";
  const result = await pool.query(`SELECT * FROM ${quoteIdentifier(route.table)}${where}${orderBy}`, values);
  res.json(result.rows);
}

async function getOne(route, req, res) {
  const table = tables[route.table];
  const result = await pool.query(
    `SELECT * FROM ${quoteIdentifier(route.table)} WHERE ${quoteIdentifier(table.primaryKey)} = $1`,
    [req.params.id]
  );
  if (!result.rowCount) return res.status(404).json({ error: "Record not found" });
  return res.json(result.rows[0]);
}

async function createRow(route, req, res) {
  const table = tables[route.table];
  const validationError = validatePayload(route, table, req.body);
  if (validationError) return res.status(400).json({ error: validationError });

  const payload = { ...req.body };
  for (const [field, definition] of Object.entries(route.derivedFields || {})) {
    if (payload[field] === undefined) {
      const base = payload[definition.source] ? new Date(payload[definition.source]) : new Date();
      if (Number.isNaN(base.getTime())) return res.status(400).json({ error: `${definition.source} must be a valid date` });
      base.setUTCDate(base.getUTCDate() + definition.days);
      payload[field] = base.toISOString().slice(0, 10);
    }
  }
  if (table.primaryKey && payload[table.primaryKey] === undefined) {
    const nextId = await pool.query(
      `SELECT COALESCE(MAX(${quoteIdentifier(table.primaryKey)}), 0) + 1 AS value FROM ${quoteIdentifier(route.table)}`
    );
    payload[table.primaryKey] = nextId.rows[0].value;
  }
  const columns = Object.keys(payload);
  if (!columns.length) return res.status(400).json({ error: "At least one field is required" });
  const values = columns.map((column) => payload[column]);
  const placeholders = columns.map((_, index) => `$${index + 1}`);
  const result = await pool.query(
    `INSERT INTO ${quoteIdentifier(route.table)} (${columns.map(quoteIdentifier).join(", ")}) VALUES (${placeholders.join(", ")}) RETURNING *`,
    values
  );
  return res.status(201).json(result.rows[0]);
}

async function updateRow(route, req, res) {
  const table = tables[route.table];
  const validationError = validatePayload(route, table, req.body);
  if (validationError) return res.status(400).json({ error: validationError });
  const columns = Object.keys(req.body).filter((column) => column !== table.primaryKey);
  if (!columns.length) return res.status(400).json({ error: "At least one updatable field is required" });
  const values = columns.map((column) => req.body[column]);
  values.push(req.params.id);
  const assignments = columns.map((column, index) => `${quoteIdentifier(column)} = $${index + 1}`);
  const result = await pool.query(
    `UPDATE ${quoteIdentifier(route.table)} SET ${assignments.join(", ")} WHERE ${quoteIdentifier(table.primaryKey)} = $${values.length} RETURNING *`,
    values
  );
  if (!result.rowCount) return res.status(404).json({ error: "Record not found" });
  return res.json(result.rows[0]);
}

async function deleteRow(route, req, res) {
  const table = tables[route.table];
  await pool.query(`DELETE FROM ${quoteIdentifier(route.table)} WHERE ${quoteIdentifier(table.primaryKey)} = $1`, [req.params.id]);
  return res.status(204).end();
}

async function getMetrics(route, _req, res) {
  const table = tables[route.table];
  const columns = table.columns;
  const select = ["COUNT(*)::int AS total"];
  if (columns.status) {
    select.push("COUNT(*) FILTER (WHERE status <> 'completed')::int AS open");
    select.push("COUNT(*) FILTER (WHERE status = 'completed')::int AS completed");
  }
  if (columns.dueDate) {
    select.push('COUNT(*) FILTER (WHERE "dueDate" >= CURRENT_DATE)::int AS upcoming');
  }
  if (columns.amount) {
    select.push('COALESCE(SUM("amount"), 0)::float AS revenue');
  }
  const result = await pool.query(`SELECT ${select.join(", ")} FROM ${quoteIdentifier(route.table)}`);
  return res.json(result.rows[0]);
}

async function listOverdue(route, _req, res) {
  const table = tables[route.table];
  if (!table.columns.overdue || !table.columns.returned) {
    return res.status(501).json({ error: "The overdue route requires overdue and returned columns" });
  }
  const result = await pool.query(
    `SELECT * FROM ${quoteIdentifier(route.table)} WHERE "overdue" = TRUE AND "returned" = FALSE ORDER BY ${quoteIdentifier(table.primaryKey)}`
  );
  return res.json(result.rows);
}

async function setBooleanFlag(route, req, res, field) {
  const table = tables[route.table];
  if (!table.primaryKey || !table.columns[field]) {
    return res.status(501).json({ error: `The route requires a ${field} column and primary key` });
  }
  const result = await pool.query(
    `UPDATE ${quoteIdentifier(route.table)} SET ${quoteIdentifier(field)} = TRUE WHERE ${quoteIdentifier(table.primaryKey)} = $1 RETURNING *`,
    [req.params.id]
  );
  if (!result.rowCount) return res.status(404).json({ error: "Record not found" });
  return res.json(result.rows[0]);
}

for (const route of routes) {
  app[route.method.toLowerCase()](route.path, async (req, res) => {
    try {
      if (route.operation === "health") return res.json({ ok: true, service: "SWARM generated app" });
      if (route.operation === "list") return await listRows(route, req, res);
      if (route.operation === "get_one") return await getOne(route, req, res);
      if (route.operation === "create") return await createRow(route, req, res);
      if (route.operation === "update") return await updateRow(route, req, res);
      if (route.operation === "delete") return await deleteRow(route, req, res);
      if (route.operation === "metrics") return await getMetrics(route, req, res);
      if (route.operation === "list_overdue") return await listOverdue(route, req, res);
      if (route.operation === "return_record") return await setBooleanFlag(route, req, res, "returned");
      if (route.operation === "mark_read") return await setBooleanFlag(route, req, res, "read");
      if (route.operation === "settings_locales") return res.json({ supported: ["en", "hi", "kn"], current: "en" });
      if (route.operation === "auth_login") return res.status(501).json({ error: "Authentication requires scaffold_auth configuration" });
      return res.status(501).json({ error: "Route operation is not implemented" });
    } catch (error) {
      return sendDatabaseError(error, res);
    }
  });
}

app.listen(port, () => {
  console.log(`Generated app API running on http://127.0.0.1:${port}`);
});
'''


if __name__ == "__main__":
    example_schema = {
        "work_items": {
            "fields": {
                "id": "integer primary key",
                "title": "string required",
                "status": "enum new|confirmed|completed",
                "amount": "number",
            }
        }
    }
    example_routes = [
        {"method": "GET", "path": "/api/health", "description": "Health check", "request_body": None, "response_shape": {"ok": True}, "validation_rules": []},
        {"method": "GET", "path": "/api/items", "description": "List items", "request_body": None, "response_shape": [], "validation_rules": []},
        {"method": "POST", "path": "/api/items", "description": "Create item", "request_body": {"title": "string", "status": "string"}, "response_shape": {"id": "number"}, "validation_rules": ["title required", "valid status"]},
    ]
    print(generate_api_routes(example_routes, example_schema)["server/index.js"])
