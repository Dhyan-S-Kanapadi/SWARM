"""Assemble graph-generated source into a complete runnable application."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from backend.agents.builder_agent.database import database_namespace


_CORE_FILES = {
    "server/index.js",
    "src/App.jsx",
    "src/api.js",
    "src/i18n.js",
    "src/styles.css",
}


def assemble_project(
    generated_files: Mapping[str, str], architecture: Mapping[str, Any], run_id: str
) -> dict[str, str]:
    """Add the project shell required by npm, Vite, and SWARM preview."""

    files = dict(generated_files)
    missing = sorted(_CORE_FILES - set(files))
    if missing:
        raise ValueError(f"Builder graph is missing core files: {', '.join(missing)}")

    auth_required = _auth_required(architecture.get("auth"))
    namespace = database_namespace(run_id)
    if auth_required:
        _integrate_auth(files)
    _integrate_database_namespace(files, namespace)

    app_name = _app_name(architecture, run_id)
    files.update(
        {
            "package.json": _package_json(app_name, auth_required),
            "index.html": _index_html(app_name),
            "vite.config.js": _vite_config(),
            "src/main.jsx": _main_jsx(auth_required),
            "server/setup-db.js": _setup_db_js(architecture["database_schema"], namespace),
            "server/app.test.js": _server_test(),
            ".env.example": _env_example(auth_required),
            "docker-compose.yml": _docker_compose(),
            "README.md": _readme(app_name, auth_required),
        }
    )
    return files


def _auth_required(auth_config: Any) -> bool:
    return auth_config is True or (
        isinstance(auth_config, Mapping) and auth_config.get("required") is True
    )


def _integrate_auth(files: dict[str, str]) -> None:
    required_auth_files = {"server/auth.js", "src/Auth.jsx", "src/auth.js", "src/auth.css"}
    missing = sorted(required_auth_files - set(files))
    if missing:
        raise ValueError(f"Authentication was requested but auth files are missing: {', '.join(missing)}")

    server = files["server/index.js"]
    import_marker = 'import pg from "pg";'
    middleware_marker = 'app.use(express.json({ limit: "1mb" }));'
    if import_marker not in server or middleware_marker not in server:
        raise ValueError("Generated server does not expose the expected auth integration points")
    server = server.replace(
        import_marker,
        f'{import_marker}\nimport {{ configureAuth }} from "./auth.js";',
        1,
    )
    server = server.replace(
        middleware_marker,
        f"{middleware_marker}\nawait configureAuth(app, pool);",
        1,
    )
    files["server/index.js"] = server


def _integrate_database_namespace(files: dict[str, str], namespace: str) -> None:
    server = files["server/index.js"]
    pool_marker = "const pool = new Pool({ connectionString: databaseUrl });"
    if pool_marker not in server:
        raise ValueError("Generated server does not expose the expected PostgreSQL pool integration point")
    files["server/index.js"] = server.replace(
        pool_marker,
        f'const pool = new Pool({{ connectionString: databaseUrl, options: "-c search_path={namespace}" }});',
        1,
    )


def _app_name(architecture: Mapping[str, Any], run_id: str) -> str:
    app_shell = architecture.get("app_shell")
    candidate = app_shell.get("app_name") if isinstance(app_shell, Mapping) else None
    raw_name = candidate if isinstance(candidate, str) and candidate.strip() else f"swarm-app-{run_id}"
    slug = re.sub(r"[^a-z0-9-]+", "-", raw_name.lower()).strip("-")
    return slug or "swarm-generated-app"


def _package_json(app_name: str, auth_required: bool) -> str:
    dependencies = {
        "cors": "^2.8.5",
        "express": "^4.21.2",
        "pg": "^8.16.3",
        "react": "^19.0.0",
        "react-dom": "^19.0.0",
    }
    if auth_required:
        dependencies.update({"bcryptjs": "^3.0.2", "express-session": "^1.18.2"})
    package = {
        "name": app_name,
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": 'concurrently "npm run dev:server" "npm run dev:client"',
            "dev:server": "node server/setup-db.js && node server/index.js",
            "dev:client": "vite --host 127.0.0.1",
            "preview:client": "vite preview --host 127.0.0.1 --strictPort",
            "server": "node server/setup-db.js && node server/index.js",
            "db:setup": "node server/setup-db.js",
            "check": "node --check server/index.js && node --check server/setup-db.js && npm run test && npm run build",
            "test": "node --test server/app.test.js",
            "build": "vite build",
        },
        "dependencies": dependencies,
        "devDependencies": {
            "@vitejs/plugin-react": "^5.0.0",
            "concurrently": "^9.2.1",
            "vite": "^7.0.0",
        },
    }
    return json.dumps(package, indent=2) + "\n"


def _index_html(app_name: str) -> str:
    title = app_name.replace("-", " ").title()
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""


def _vite_config() -> str:
    return """import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:3001" },
  },
});
"""


def _main_jsx(auth_required: bool) -> str:
    auth_import = 'import { AuthGate } from "./Auth.jsx";\n' if auth_required else ""
    app = "<AuthGate><App /></AuthGate>" if auth_required else "<App />"
    return f"""import React from "react";
import {{ createRoot }} from "react-dom/client";
import App from "./App.jsx";
{auth_import}import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {app}
  </React.StrictMode>,
);
"""


def _server_test() -> str:
    return """import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("generated project contains PostgreSQL API and React entry points", async () => {
  const server = await readFile(new URL("./index.js", import.meta.url), "utf8");
  const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const main = await readFile(new URL("../src/main.jsx", import.meta.url), "utf8");
  const setup = await readFile(new URL("./setup-db.js", import.meta.url), "utf8");

  assert.match(server, /new Pool/);
  assert.match(server, /app[.]listen/);
  assert.match(app, /export default function App/);
  assert.match(main, /createRoot/);
  assert.match(setup, /CREATE TABLE IF NOT EXISTS/);
});
"""


def _setup_db_js(database_schema: Any, namespace: str) -> str:
    if not isinstance(database_schema, Mapping) or not database_schema:
        raise ValueError("database_schema must be a non-empty mapping")
    encoded_schema = json.dumps(database_schema, indent=2)
    template = r'''import pg from "pg";

const { Pool } = pg;
const databaseUrl = process.env.DATABASE_URL;
const schema = __DATABASE_SCHEMA__;
const namespace = "__DATABASE_NAMESPACE__";
const identifierPattern = /^[A-Za-z_][A-Za-z0-9_]*$/;
const typeMap = {
  serial: "SERIAL",
  bigserial: "BIGSERIAL",
  varchar: "TEXT",
  integer: "INTEGER",
  int: "INTEGER",
  bigint: "BIGINT",
  number: "NUMERIC",
  float: "DOUBLE PRECISION",
  decimal: "NUMERIC",
  string: "TEXT",
  text: "TEXT",
  boolean: "BOOLEAN",
  bool: "BOOLEAN",
  date: "DATE",
  datetime: "TIMESTAMPTZ",
  timestamp: "TIMESTAMPTZ",
  uuid: "UUID",
  json: "JSONB",
};

if (!databaseUrl) throw new Error("DATABASE_URL must be set before setting up PostgreSQL.");

function quoteIdentifier(value) {
  if (!identifierPattern.test(value)) throw new Error(`Invalid SQL identifier: ${value}`);
  return `"${value}"`;
}

function fieldSql(fieldName, declaration) {
  const normalized = String(declaration).trim().toLowerCase();
  let sqlType;
  if (normalized.startsWith("enum ")) {
    const values = normalized.slice(5).split("|").map((value) => value.trim()).filter(Boolean);
    if (!values.length) throw new Error(`Enum field ${fieldName} has no values`);
    const choices = values.map((value) => `'${value.replaceAll("'", "''")}'`).join(", ");
    sqlType = `TEXT CHECK (${quoteIdentifier(fieldName)} IN (${choices}))`;
  } else {
    const varchar = normalized.match(/\b(?:varchar|character varying)\s*\(\s*(\d+)\s*\)/);
    const type = Object.keys(typeMap).find((candidate) => new RegExp(`\\b${candidate}\\b`).test(normalized));
    if (!type) throw new Error(`Unsupported field declaration for ${fieldName}: ${declaration}`);
    sqlType = varchar ? `VARCHAR(${varchar[1]})` : typeMap[type];
  }
  if (normalized.includes("primary key")) sqlType += " PRIMARY KEY";
  if (normalized.includes("required") || normalized.includes("not null")) sqlType += " NOT NULL";
  if (normalized.includes("unique")) sqlType += " UNIQUE";
  const defaultMatch = normalized.match(/\bdefault\s+(.+?)(?=\s+(?:references|on\s+delete|check)\b|$)/);
  if (defaultMatch) {
    const value = defaultMatch[1].trim();
    if (!/^(current_date|current_timestamp|true|false|[-+]?\d+(?:\.\d+)?|'[^']*')$/.test(value)) {
      throw new Error(`Unsupported default for ${fieldName}: ${value}`);
    }
    sqlType += ` DEFAULT ${value.toUpperCase()}`;
  }
  const referenceMatch = normalized.match(/\breferences\s+([a-z_][a-z0-9_]*)\s*\(\s*([a-z_][a-z0-9_]*)\s*\)(\s+on\s+delete\s+(?:restrict|cascade|set null))?/);
  if (referenceMatch) {
    const [, tableName, referencedField, onDelete = ""] = referenceMatch;
    sqlType += ` REFERENCES ${quoteIdentifier(tableName)}(${quoteIdentifier(referencedField)})${onDelete.toUpperCase()}`;
  }
  const checkMatch = normalized.match(/\bcheck\s*(\([a-z_][a-z0-9_]*\s+in\s+\([^)]*\)\))/);
  if (checkMatch) sqlType += ` CHECK ${checkMatch[1]}`;
  return sqlType;
}

function indexParts(specification, tableName) {
  const match = String(specification).trim().match(/(?:(UNIQUE|INDEX)\s*\(\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\)?$/i);
  if (!match) throw new Error(`Unsupported index declaration for ${tableName}: ${specification}`);
  const [, kind = "", fieldName] = match;
  quoteIdentifier(fieldName);
  return { fieldName, unique: kind.toUpperCase() === "UNIQUE" };
}

function relationshipParts(relationship) {
  let localField = relationship.field || relationship.local_field;
  let referencedTable;
  let referencedField;
  if (relationship.references) {
    localField ||= relationship.column;
    [referencedTable, referencedField] = relationship.references.split(".");
  } else {
    referencedTable = relationship.table || relationship.referenced_table;
    if (localField) {
      referencedField = relationship.referenced_field || relationship.target_field || relationship.column || "id";
    } else {
      localField = relationship.column;
      referencedField = relationship.referenced_field || relationship.target_field || "id";
    }
  }
  for (const value of [localField, referencedTable, referencedField]) quoteIdentifier(value);
  return { localField, referencedTable, referencedField };
}

async function setupDatabase() {
  const pool = new Pool({ connectionString: databaseUrl });
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(`CREATE SCHEMA IF NOT EXISTS ${quoteIdentifier(namespace)}`);
    await client.query(`SET LOCAL search_path TO ${quoteIdentifier(namespace)}`);
    for (const [tableName, table] of Object.entries(schema)) {
      const columns = Object.entries(table.fields).map(
        ([fieldName, declaration]) => `${quoteIdentifier(fieldName)} ${fieldSql(fieldName, declaration)}`,
      );
      await client.query(`CREATE TABLE IF NOT EXISTS ${quoteIdentifier(tableName)} (${columns.join(", ")})`);
    }
    for (const [tableName, table] of Object.entries(schema)) {
      for (const indexSpecification of table.indexes || []) {
        const { fieldName, unique } = indexParts(indexSpecification, tableName);
        const indexName = `idx_${tableName}_${fieldName}`.slice(0, 63);
        await client.query(
          `CREATE ${unique ? "UNIQUE " : ""}INDEX IF NOT EXISTS ${quoteIdentifier(indexName)} ON ${quoteIdentifier(tableName)} (${quoteIdentifier(fieldName)})`,
        );
      }
      const relationships = Array.isArray(table.relationships) ? table.relationships : [];
      for (const relationship of relationships) {
        const { localField, referencedTable, referencedField } = relationshipParts(relationship);
        const constraintName = `fk_${tableName}_${localField}`.slice(0, 63);
        await client.query(`DO $$ BEGIN ALTER TABLE ${quoteIdentifier(tableName)} ADD CONSTRAINT ${quoteIdentifier(constraintName)} FOREIGN KEY (${quoteIdentifier(localField)}) REFERENCES ${quoteIdentifier(referencedTable)} (${quoteIdentifier(referencedField)}); EXCEPTION WHEN duplicate_object THEN NULL; END $$`);
      }
      for (const record of table.seed_records || []) {
        const columns = Object.keys(record);
        if (!columns.length) continue;
        const placeholders = columns.map((_, index) => `$${index + 1}`);
        await client.query(
          `INSERT INTO ${quoteIdentifier(tableName)} (${columns.map(quoteIdentifier).join(", ")}) VALUES (${placeholders.join(", ")}) ON CONFLICT DO NOTHING`,
          columns.map((column) => record[column]),
        );
      }
    }
    await client.query("COMMIT");
    console.log("PostgreSQL schema is ready.");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
    await pool.end();
  }
}

setupDatabase().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
'''
    return template.replace("__DATABASE_SCHEMA__", encoded_schema).replace(
        "__DATABASE_NAMESPACE__", namespace
    )


def _env_example(auth_required: bool) -> str:
    lines = ["DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/swarm_generated"]
    if auth_required:
        lines.append("SESSION_SECRET=replace-with-a-long-random-secret")
    return "\n".join(lines) + "\n"


def _docker_compose() -> str:
    return """services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: swarm_generated
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d swarm_generated"]
      interval: 2s
      timeout: 3s
      retries: 20
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
"""


def _readme(app_name: str, auth_required: bool) -> str:
    auth_note = "Set SESSION_SECRET as shown in .env.example.\n" if auth_required else ""
    return f"""# {app_name}

Architecture-driven React, Express, and PostgreSQL application generated by SWARM.

## Run locally

1. Start PostgreSQL: `docker compose up -d postgres`
2. Set `DATABASE_URL` from `.env.example` in your shell.
3. Run `npm install`.
4. Run `npm run dev`. The server command applies the schema and seed records before starting.

{auth_note}The frontend runs on `http://127.0.0.1:5173` and the API on `http://127.0.0.1:3001`.

## Verify

Run `npm run check` to execute the generated server test and production frontend build.
"""


__all__ = ["assemble_project"]
