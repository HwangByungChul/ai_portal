"""Unit & Integration Tests for MCP Tool Auto-Wrapping and Dynamic Environment Routing (T-035)."""
import asyncio
import pytest
from app.errors import AppError
from app.tools.parsers.openapi_parser import parse_openapi_spec
from app.tools.parsers.wsdl_parser import parse_wsdl_spec
from app.tools.parsers.jdbc_parser import parse_jdbc_spec
from app.tools.parsers.packet_parser import (
    parse_packet_spec,
    pack_financial_message,
    unpack_financial_message,
)
from app.tools.dynamic_gateway import DynamicToolGateway
from app.tools.credentials import encrypt_credential, decrypt_credential


def test_credential_encryption_and_decryption():
    """Test AES/HMAC credential vault round-trip."""
    original = {"api_key": "bnk_prod_secret_token_12345", "role": "admin"}
    encrypted = encrypt_credential(original)
    assert isinstance(encrypted, str)
    assert len(encrypted) > 20
    assert "bnk_prod_secret_token_12345" not in encrypted

    decrypted = decrypt_credential(encrypted)
    assert decrypted == original


def test_openapi_auto_wrap_parsing():
    """Test parsing Swagger 2.0 / OpenAPI 3.0 specs into MCP Tool definitions."""
    sample_spec = {
        "openapi": "3.0.0",
        "info": {"title": "BNK Core Banking Loan API", "version": "1.0"},
        "paths": {
            "/api/v1/loan/inquire": {
                "post": {
                    "operationId": "inquire_customer_loan_limit",
                    "summary": "고객 대출 한도 및 금리 조회",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["customer_id", "desired_amount"],
                                    "properties": {
                                        "customer_id": {"type": "string", "description": "고객 식별번호"},
                                        "desired_amount": {"type": "number", "description": "희망 대출금액"},
                                    },
                                }
                            }
                        }
                    },
                }
            }
        },
    }
    tools = parse_openapi_spec(sample_spec)
    assert len(tools) == 1
    t = tools[0]
    assert t["tool_id"] == "inquire_customer_loan_limit"
    assert t["source_type"] == "openapi"
    assert t["method"] == "POST"
    assert t["path"] == "/api/v1/loan/inquire"
    assert "customer_id" in t["input_schema"]["properties"]
    assert "desired_amount" in t["input_schema"]["properties"]
    assert "customer_id" in t["input_schema"]["required"]


def test_wsdl_auto_wrap_parsing():
    """Test parsing WSDL XML into SOAP MCP Tool with automated envelope template."""
    sample_wsdl = """<?xml version="1.0" encoding="utf-8"?>
    <wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                      xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                      xmlns:tns="http://banking.bnk.co.kr/transfer"
                      targetNamespace="http://banking.bnk.co.kr/transfer">
      <wsdl:message name="ExecuteTransferInput">
        <wsdl:part name="SenderAccount" type="xsd:string"/>
        <wsdl:part name="ReceiverAccount" type="xsd:string"/>
        <wsdl:part name="Amount" type="xsd:long"/>
      </wsdl:message>
      <wsdl:portType name="TransferPortType">
        <wsdl:operation name="ExecuteTransfer">
          <wsdl:documentation>실시간 타행 계좌 이체 처리 서비스</wsdl:documentation>
          <wsdl:input message="tns:ExecuteTransferInput"/>
        </wsdl:operation>
      </wsdl:portType>
    </wsdl:definitions>
    """
    tools = parse_wsdl_spec(sample_wsdl)
    assert len(tools) == 1
    t = tools[0]
    assert t["tool_id"] == "soap_executetransfer"
    assert t["source_type"] == "wsdl"
    assert t["operation_name"] == "ExecuteTransfer"
    assert "SenderAccount" in t["input_schema"]["properties"]
    assert "ReceiverAccount" in t["input_schema"]["properties"]
    assert "soap:Envelope" in t["envelope_template"]


def test_jdbc_auto_wrap_parsing_and_security():
    """Test JDBC view wrapping and strict prohibition of DML mutations."""
    valid_spec = {
        "table_or_view": "v_branch_daily_summary",
        "db_type": "postgresql",
        "columns": [
            {"name": "branch_code", "type": "string"},
            {"name": "total_deposit_krw", "type": "number"},
            {"name": "consultation_count", "type": "number"},
        ],
    }
    tool = parse_jdbc_spec(valid_spec)
    assert tool["tool_id"] == "db_view_v_branch_daily_summary"
    assert tool["source_type"] == "jdbc"
    assert "filter_branch_code" in tool["input_schema"]["properties"]
    assert "SELECT branch_code, total_deposit_krw, consultation_count FROM v_branch_daily_summary" in tool["base_query"]

    # Mutation injection attempt must be blocked
    malicious_spec = {
        "table_or_view": "v_branch_daily_summary",
        "columns": ["branch_code"],
        "custom_sql": "SELECT branch_code FROM v_branch_daily_summary; DROP TABLE customers; --",
    }
    with pytest.raises(AppError) as exc_info:
        parse_jdbc_spec(malicious_spec)
    assert exc_info.value.code == "JDBC_MUTATION_QUERY_FORBIDDEN"


def test_financial_packet_auto_wrap_and_pack_unpack():
    """Test financial packet layout parsing and byte serialization/deserialization."""
    packet_spec = {
        "packet_code": "BNK-FEP-0100",
        "packet_name": "계좌 실명 조회 전문",
        "protocol": "tcp_socket",
        "fields": [
            {"field_id": "INST_CODE", "name": "참가기관코드", "type": "string", "length": 3},
            {"field_id": "ACCOUNT_NO", "name": "계좌번호", "type": "string", "length": 16},
            {"field_id": "TX_AMOUNT", "name": "거래금액", "type": "number", "length": 10},
        ],
    }
    tool = parse_packet_spec(packet_spec)
    assert tool["tool_id"] == "packet_bnk-fep-0100"
    assert tool["total_length"] == 29
    assert len(tool["layout_meta"]) == 3

    # Pack values to fixed-length bytes (3 + 16 + 10 = 29 bytes)
    input_data = {
        "INST_CODE": "032",
        "ACCOUNT_NO": "110-1234-5678",
        "TX_AMOUNT": 50000,
    }
    packed = pack_financial_message(tool["layout_meta"], input_data)
    assert len(packed) == 29

    # Unpack back to dictionary
    unpacked = unpack_financial_message(tool["layout_meta"], packed)
    assert unpacked["INST_CODE"] == "032"
    assert unpacked["ACCOUNT_NO"] == "110-1234-5678"
    assert unpacked["TX_AMOUNT"] == 50000


def test_dynamic_environment_routing_draft_vs_approved():
    """Test dynamic routing: Draft agents route to Dev, Approved agents route to Prd."""
    gw = DynamicToolGateway()
    gw.register_tool(
        tool_id="test_credit_checker",
        name="신용평점 조회",
        description="고객 신용도 평가 시스템 조회",
        source_type="openapi",
        input_schema={
            "type": "object",
            "required": ["ssn_hash"],
            "properties": {"ssn_hash": {"type": "string"}},
        },
        dev_profile={
            "protocol_type": "rest_http",
            "base_endpoint_url": "https://dev-gateway.bank.internal/credit/check",
            "active": True,
        },
        prd_profile={
            "protocol_type": "rest_http",
            "base_endpoint_url": "https://prd-gateway.bank.internal/credit/check",
            "active": True,
        },
    )

    async def run_checks():
        # 1. Draft agent call -> MUST route to Development endpoint
        res_draft = await gw.invoke_routed(
            tool_id="test_credit_checker",
            arguments={"ssn_hash": "hash_sample_001"},
            publication_status="draft",
            client_request_id="req-test-draft-001",
        )
        assert res_draft["routed_env"] == "development"
        assert res_draft["routed_endpoint"] == "https://dev-gateway.bank.internal/credit/check"

        # 2. Approved published agent call -> MUST route to Production endpoint
        res_prd = await gw.invoke_routed(
            tool_id="test_credit_checker",
            arguments={"ssn_hash": "hash_sample_001"},
            publication_status="approved_published",
            client_request_id="req-test-prd-001",
        )
        assert res_prd["routed_env"] == "production"
        assert res_prd["routed_endpoint"] == "https://prd-gateway.bank.internal/credit/check"

    asyncio.run(run_checks())


def test_tool_argument_safety_and_idempotency():
    """Test security injection blocking and idempotency conflict checking."""
    gw = DynamicToolGateway()
    gw.register_tool(
        tool_id="safety_check_tool",
        name="안전 검사 도구",
        description="테스트용 도구",
        source_type="openapi",
        input_schema={"type": "object", "properties": {"keyword": {"type": "string"}}},
    )

    async def run_checks():
        # Path traversal injection attempt must be blocked with 422
        with pytest.raises(AppError) as exc_traversal:
            await gw.invoke_routed(
                tool_id="safety_check_tool",
                arguments={"keyword": "../../etc/passwd"},
                publication_status="draft",
            )
        assert exc_traversal.value.code == "TOOL_ARGUMENTS_INVALID"

        # SQL injection keyword attempt must be blocked with 422
        with pytest.raises(AppError) as exc_sql:
            await gw.invoke_routed(
                tool_id="safety_check_tool",
                arguments={"keyword": "test'; DROP TABLE users; --"},
                publication_status="draft",
            )
        assert exc_sql.value.code == "TOOL_ARGUMENTS_INVALID"

        # Idempotency conflict test
        cid = "client-req-uuid-999"
        await gw.invoke_routed(
            tool_id="safety_check_tool",
            arguments={"keyword": "valid_token_A"},
            client_request_id=cid,
        )
        # Re-sending different arguments with the same client_request_id must raise 409 REVISION_CONFLICT
        with pytest.raises(AppError) as exc_conflict:
            await gw.invoke_routed(
                tool_id="safety_check_tool",
                arguments={"keyword": "different_token_B"},
                client_request_id=cid,
            )
        assert exc_conflict.value.code == "REVISION_CONFLICT"

    asyncio.run(run_checks())
