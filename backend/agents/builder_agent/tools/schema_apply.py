"""Apply an Architect database schema to PostgreSQL.

The Architect's schema describes tables as ``{table_name: {fields, indexes,
relationships, seed_records}}``. Field declarations are intentionally simple,
for example ``"integer primary key"``, ``"string required"``, or
``"enum new|confirmed"``. Relationships may use ``field`` plus ``references``
(``"accounts.id"``), or ``field`` plus ``table`` and ``column``. The compact
``column`` plus ``table`` form means that column references the target table's
``id`` column.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - exercised only without dependencies installed
    psycopg = None
    sql = None


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TYPE_MAP = {
    "serial": "SERIAL",
    "bigserial": "BIGSERIAL",
    "varchar": "TEXT",
    "integer": "INTEGER",
    "int": "INTEGER",
    "bigint": "BIGINT",
    "number": "NUMERIC",
    "float": "DOUBLE PRECISION",
    "decimal": "NUMERIC",
    "string": "TEXT",
    "text": "TEXT",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMPTZ",
    "timestamp": "TIMESTAMPTZ",
    "uuid": "UUID",
    "json": "JSONB",
}


def apply_database_schema(
    database_schema: Mapping[str, Any], database_url: str | None = None
) -> dict[str, Any]:
    """Create the supplied schema and seed it, returning a structured outcome.

    ``DATABASE_URL`` is used when ``database_url`` is omitted. All DDL and seed
    inserts run in one transaction. A failure rolls back the transaction and is
    reported in the returned ``errors`` list rather than being raised.
    """

    result: dict[str, Any] = {"tables_created": [], "errors": [], "sql": []}
    if psycopg is None or sql is None:
        result["errors"].append("psycopg is not installed. Install project requirements first.")
        return result

    if not isinstance(database_schema, Mapping) or not database_schema:
        result["errors"].append("database_schema must be a non-empty dictionary of tables.")
        return result

    connection_url = database_url or os.getenv("DATABASE_URL")
    if not connection_url:
        result["errors"].append("DATABASE_URL is not set.")
        return result

    try:
        statements, seed_rows = _build_schema_statements(database_schema)
    except (TypeError, ValueError) as exc:
        result["errors"].append(f"Invalid database_schema: {exc}")
        return result

    try:
        with psycopg.connect(connection_url) as connection:
            with connection.cursor() as cursor:
                table_existed: dict[str, bool] = {}
                for table_name, statement in statements:
                    if table_name not in table_existed:
                        cursor.execute(
                            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_tables "
                            "WHERE schemaname = current_schema() AND tablename = %s)",
                            (table_name,),
                        )
                        table_existed[table_name] = bool(cursor.fetchone()[0])
                    cursor.execute(statement)
                    result["sql"].append(statement.as_string(connection))
                    if not table_existed[table_name] and table_name not in result["tables_created"]:
                        result["tables_created"].append(table_name)

                for table_name, record in seed_rows:
                    seed_statement, values = _build_seed_statement(table_name, record)
                    cursor.execute(seed_statement, values)
                    result["sql"].append(seed_statement.as_string(connection))
    except Exception as exc:  # Database connectivity and SQL failures are returned to the caller.
        result["tables_created"] = []
        result["errors"].append(f"PostgreSQL schema application failed: {type(exc).__name__}: {exc}")

    return result


def _build_schema_statements(
    database_schema: Mapping[str, Any]
) -> tuple[list[tuple[str, Any]], list[tuple[str, Mapping[str, Any]]]]:
    table_statements: list[tuple[str, Any]] = []
    index_statements: list[tuple[str, Any]] = []
    relationship_statements: list[tuple[str, Any]] = []
    seed_rows: list[tuple[str, Mapping[str, Any]]] = []

    for table_name, table_spec in database_schema.items():
        _validate_identifier(table_name, "table name")
        if not isinstance(table_spec, Mapping):
            raise ValueError(f"table '{table_name}' must be a dictionary")

        fields = table_spec.get("fields")
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError(f"table '{table_name}' must define a non-empty fields dictionary")

        column_definitions = [
            sql.SQL("{} {}").format(sql.Identifier(field_name), sql.SQL(_field_sql(field_name, declaration)))
            for field_name, declaration in fields.items()
        ]
        table_statements.append(
            (
                table_name,
                sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                    sql.Identifier(table_name), sql.SQL(", ").join(column_definitions)
                ),
            )
        )

        for index_specification in table_spec.get("indexes", []):
            index_field, unique = _index_parts(index_specification, table_name)
            if index_field not in fields:
                raise ValueError(f"index field '{index_field}' is not defined on table '{table_name}'")
            index_name = _index_name(table_name, index_field)
            index_statements.append(
                (
                    table_name,
                    sql.SQL("CREATE {}INDEX IF NOT EXISTS {} ON {} ({})").format(
                        sql.SQL("UNIQUE ") if unique else sql.SQL(""),
                        sql.Identifier(index_name), sql.Identifier(table_name), sql.Identifier(index_field)
                    ),
                )
            )

        relationships = table_spec.get("relationships", [])
        # Architect may include a descriptive relationship map while expressing
        # the executable foreign keys inline in the field declaration.
        if isinstance(relationships, Mapping):
            relationships = []
        for relationship in relationships:
            local_field, referenced_table, referenced_field = _relationship_parts(table_name, relationship)
            if local_field not in fields:
                raise ValueError(f"relationship field '{local_field}' is not defined on table '{table_name}'")
            constraint_name = _foreign_key_name(table_name, local_field)
            relationship_statements.append(
                (
                    table_name,
                    sql.SQL(
                        "DO $$ BEGIN ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) "
                        "REFERENCES {} ({}); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                    ).format(
                        sql.Identifier(table_name),
                        sql.Identifier(constraint_name),
                        sql.Identifier(local_field),
                        sql.Identifier(referenced_table),
                        sql.Identifier(referenced_field),
                    ),
                )
            )

        records = table_spec.get("seed_records", [])
        if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
            raise ValueError(f"seed_records for table '{table_name}' must be a list")
        for record in records:
            if not isinstance(record, Mapping):
                raise ValueError(f"seed record for table '{table_name}' must be a dictionary")
            unknown_fields = set(record) - set(fields)
            if unknown_fields:
                raise ValueError(
                    f"seed record for table '{table_name}' has unknown fields: {', '.join(sorted(unknown_fields))}"
                )
            seed_rows.append((table_name, record))

    # Tables must all exist before foreign-key constraints are applied, regardless
    # of their order in the architecture object.
    return table_statements + index_statements + relationship_statements, seed_rows


def _field_sql(field_name: str, declaration: Any) -> str:
    _validate_identifier(field_name, "field name")
    if not isinstance(declaration, str) or not declaration.strip():
        raise ValueError(f"field '{field_name}' must have a non-empty string declaration")

    normalized = declaration.strip().lower()
    if normalized.startswith("enum "):
        values = [value.strip() for value in normalized.removeprefix("enum ").split("|") if value.strip()]
        if not values:
            raise ValueError(f"enum field '{field_name}' must list at least one value")
        escaped_values = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
        return f'TEXT CHECK ("{field_name}" IN ({escaped_values}))' + _constraints(normalized)

    varchar = re.search(r"\b(?:varchar|character varying)\s*\(\s*(\d+)\s*\)", normalized)
    base_type = next((key for key in _TYPE_MAP if re.search(rf"\b{re.escape(key)}\b", normalized)), None)
    if base_type is None:
        raise ValueError(f"field '{field_name}' has unsupported type declaration '{declaration}'")
    column_type = f"VARCHAR({varchar.group(1)})" if varchar else _TYPE_MAP[base_type]
    default = _default_clause(normalized)
    references = _references_clause(normalized)
    check = _check_clause(normalized)
    return column_type + _constraints(normalized) + default + references + check


def _constraints(declaration: str) -> str:
    constraints = ""
    if "primary key" in declaration:
        constraints += " PRIMARY KEY"
    if "required" in declaration or "not null" in declaration:
        constraints += " NOT NULL"
    if "unique" in declaration:
        constraints += " UNIQUE"
    return constraints


def _default_clause(declaration: str) -> str:
    match = re.search(r"\bdefault\s+(.+?)(?=\s+(?:references|on\s+delete|check)\b|$)", declaration)
    if not match:
        return ""
    value = match.group(1).strip()
    if value in {"current_date", "current_timestamp", "true", "false"} or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value):
        return f" DEFAULT {value.upper() if value.startswith('current_') else value.upper() if value in {'true', 'false'} else value}"
    if re.fullmatch(r"'[^']*'", value):
        return f" DEFAULT {value}"
    raise ValueError(f"unsupported default value '{value}'")


def _references_clause(declaration: str) -> str:
    match = re.search(r"\breferences\s+([a-z_][a-z0-9_]*)\s*\(\s*([a-z_][a-z0-9_]*)\s*\)(\s+on\s+delete\s+(?:restrict|cascade|set null))?", declaration)
    if not match:
        return ""
    table_name, field_name, on_delete = match.groups()
    _validate_identifier(table_name, "referenced table")
    _validate_identifier(field_name, "referenced field")
    return f" REFERENCES {table_name}({field_name}){on_delete.upper() if on_delete else ''}"


def _check_clause(declaration: str) -> str:
    match = re.search(r"\bcheck\s*(\([a-z_][a-z0-9_]*\s+in\s+\([^)]*\)\))", declaration)
    if not match:
        return ""
    expression = match.group(1)
    return f" CHECK {expression}"


def _index_parts(index_specification: Any, table_name: str) -> tuple[str, bool]:
    if not isinstance(index_specification, str) or not index_specification.strip():
        raise ValueError(f"index for table '{table_name}' must be a field name or INDEX(field)/UNIQUE(field)")
    specification = index_specification.strip()
    match = re.fullmatch(r"(?:(UNIQUE|INDEX)\s*\(\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\)?", specification, re.IGNORECASE)
    if not match:
        raise ValueError(f"unsupported index declaration '{index_specification}' on table '{table_name}'")
    kind, field_name = match.groups()
    _validate_identifier(field_name, f"index field for table '{table_name}'")
    return field_name, (kind or "").upper() == "UNIQUE"


def _relationship_parts(table_name: str, relationship: Any) -> tuple[str, str, str]:
    if not isinstance(relationship, Mapping):
        raise ValueError(f"relationship for table '{table_name}' must be a dictionary")

    local_field = relationship.get("field") or relationship.get("local_field")
    references = relationship.get("references")
    if references:
        local_field = local_field or relationship.get("column")
        if not isinstance(references, str) or references.count(".") != 1:
            raise ValueError(f"relationship references for table '{table_name}' must be 'table.field'")
        referenced_table, referenced_field = references.split(".", maxsplit=1)
    else:
        referenced_table = relationship.get("table") or relationship.get("referenced_table")
        if local_field:
            referenced_field = relationship.get("referenced_field") or relationship.get("target_field") or relationship.get("column") or "id"
        else:
            local_field = relationship.get("column")
            referenced_field = relationship.get("referenced_field") or relationship.get("target_field") or "id"

    if not all(isinstance(value, str) and value for value in (local_field, referenced_table, referenced_field)):
        raise ValueError(f"relationship for table '{table_name}' needs field and referenced table/field")
    _validate_identifier(local_field, "relationship field")
    _validate_identifier(referenced_table, "referenced table")
    _validate_identifier(referenced_field, "referenced field")
    return local_field, referenced_table, referenced_field


def _build_seed_statement(table_name: str, record: Mapping[str, Any]) -> tuple[Any, list[Any]]:
    if not record:
        raise ValueError(f"seed record for table '{table_name}' cannot be empty")
    columns = list(record)
    for column in columns:
        _validate_identifier(column, "seed field")
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    return statement, [record[column] for column in columns]


def _validate_identifier(identifier: Any, description: str) -> None:
    if not isinstance(identifier, str) or not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"{description} '{identifier}' is not a valid SQL identifier")


def _index_name(table_name: str, field_name: str) -> str:
    return f"idx_{table_name}_{field_name}"[:63]


def _foreign_key_name(table_name: str, field_name: str) -> str:
    return f"fk_{table_name}_{field_name}"[:63]


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    example_schema = {
        "customers": {
            "fields": {"id": "integer primary key", "name": "string required"},
            "indexes": ["name"],
            "relationships": [],
            "seed_records": [{"id": 1, "name": "Ada Lovelace"}],
        },
        "orders": {
            "fields": {"id": "integer primary key", "customer_id": "integer required", "total": "number"},
            "indexes": ["customer_id"],
            "relationships": [{"field": "customer_id", "references": "customers.id"}],
            "seed_records": [{"id": 1, "customer_id": 1, "total": 42.50}],
        },
    }
    print(json.dumps(apply_database_schema(example_schema), indent=2, default=str))
