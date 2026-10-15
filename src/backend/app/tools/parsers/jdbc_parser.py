"""JDBC / Relational Database View Auto-Wrapping Parser.

Parses database connection and table/view specifications, strictly enforcing
read-only query semantics and generating MCP Tool specifications for secure data views.
"""
import re
from typing import Any
from app.errors import AppError

# Disallow mutating keywords anywhere in JDBC view queries
_FORBIDDEN_MUTATIONS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|exec|execute|replace)\b",
    re.IGNORECASE
)


def parse_jdbc_spec(spec_data: dict[str, Any]) -> dict[str, Any]:
    """Parse JDBC table/view specification and produce a safe Read-Only MCP Tool."""
    table_or_view = spec_data.get("table_or_view", "").strip()
    if not table_or_view or not re.match(r"^[a-zA-Z0-9_.]+$", table_or_view):
        raise AppError("JDBC_INVALID_TABLE_NAME", 422)

    db_type = spec_data.get("db_type", "postgresql").lower()
    columns = spec_data.get("columns", [])
    if not isinstance(columns, list) or not columns:
        raise AppError("JDBC_NO_COLUMNS_SPECIFIED", 422)

    properties: dict[str, Any] = {}
    valid_cols: list[str] = []

    for col in columns:
        if isinstance(col, str):
            c_name = col.strip()
            c_type = "string"
        elif isinstance(col, dict):
            c_name = col.get("name", "").strip()
            c_type = col.get("type", "string")
        else:
            continue

        if not re.match(r"^[a-zA-Z0-9_]+$", c_name):
            continue

        valid_cols.append(c_name)
        # Search/filter property for each column
        properties[f"filter_{c_name}"] = {
            "type": "string",
            "description": f"Optional search filter condition for column {c_name} ({c_type})"
        }

    if not valid_cols:
        raise AppError("JDBC_NO_VALID_COLUMNS", 422)

    # Standard pagination
    properties["limit"] = {
        "type": "number",
        "description": "Max rows to retrieve (1 to 100, default 20)"
    }

    custom_query = spec_data.get("custom_sql")
    if custom_query:
        if _FORBIDDEN_MUTATIONS.search(custom_query):
            raise AppError("JDBC_MUTATION_QUERY_FORBIDDEN", 422)
        base_query = custom_query
    else:
        col_list_str = ", ".join(valid_cols)
        base_query = f"SELECT {col_list_str} FROM {table_or_view}"

    tool_id = f"db_view_{table_or_view.replace('.', '_').lower()}"
    description = (
        f"[JDBC / DB View] Read-only virtualized view for '{table_or_view}' ({db_type}).\n"
        f"Columns: {', '.join(valid_cols)}\n"
        f"Base Query: {base_query[:150]}"
    )

    return {
        "tool_id": tool_id,
        "name": f"{table_or_view} 뷰 조회",
        "description": description,
        "category": "database_view",
        "source_type": "jdbc",
        "table_or_view": table_or_view,
        "db_type": db_type,
        "valid_columns": valid_cols,
        "base_query": base_query,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
    }
