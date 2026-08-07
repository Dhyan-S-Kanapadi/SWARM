"""PostgreSQL namespace helpers shared by Builder orchestration and output."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import sql


def database_namespace(run_id: str) -> str:
    """Return a stable, valid PostgreSQL schema name for one SWARM run."""

    normalized = re.sub(r"[^a-z0-9_]", "_", run_id.lower())
    return f"swarm_{normalized}"[:63]


def ensure_database_namespace(database_url: str, namespace: str) -> None:
    """Create a run namespace before schema_apply connects with search_path."""

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(namespace)))


def database_url_for_namespace(database_url: str, namespace: str) -> str:
    """Add a libpq search_path option without discarding existing URL options."""

    parts = urlsplit(database_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "options"]
    query.append(("options", f"-c search_path={namespace}"))
    encoded_query = urlencode(query, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, encoded_query, parts.fragment))


__all__ = ["database_namespace", "database_url_for_namespace", "ensure_database_namespace"]
