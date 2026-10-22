"""Contract tests for JDBCConnector."""
import pytest
from app.errors import AppError
from app.tools.connectors.jdbc_connector import JDBCConnector


@pytest.mark.anyio
async def test_jdbc_connector_success():
    mock_rows = [
        {"customer_id": 101, "customer_name": "홍길동", "tier": "VIP"},
    ]

    def mock_executor(query: str, params: list):
        assert "SELECT * FROM v_customer_summary WHERE customer_id = %s" in query
        assert params == [101]
        return mock_rows

    connector = JDBCConnector(executor_func=mock_executor)
    tool_meta = {
        "view_name": "v_customer_summary",
        "allowed_columns": ["customer_id", "tier"],
    }
    arguments = {"customer_id": 101}

    result = await connector.execute(
        endpoint_url="postgresql://mock",
        credential_ref=None,
        tool_meta=tool_meta,
        arguments=arguments,
    )

    assert result.status == "success"
    assert result.body["count"] == 1
    assert result.body["rows"][0]["customer_name"] == "홍길동"
    assert result.retryable is False


def test_jdbc_connector_sql_injection_blocked():
    connector = JDBCConnector()
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(
            {"view_name": "v_users; DROP TABLE users;--"},
            {},
        )
    assert exc_info.value.code in {"TOOL_ARGUMENTS_INVALID", "TOOL_INPUT_BLOCKED"}

    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(
            {"view_name": "v_users"},
            {"name": "' OR '1'='1' -- DROP TABLE"},
        )
    assert exc_info.value.code == "TOOL_INPUT_BLOCKED"


def test_jdbc_connector_disallowed_column():
    connector = JDBCConnector()
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(
            {"view_name": "v_users", "allowed_columns": ["id"]},
            {"secret_column": "value"},
        )
    assert exc_info.value.code == "TOOL_ARGUMENTS_INVALID"
