"""Acceptance Tests for DP20-22 (Standard Tools & MCP Gateway) & DP23 (Workflow DAG Runner)."""
import pytest
from app.tools.registry import GLOBAL_TOOL_REGISTRY
from app.workflows.models import WorkflowDefinition, WorkflowNode, WorkflowEdge
from app.workflows.runner import GLOBAL_WORKFLOW_RUNNER
from app.errors import AppError

@pytest.mark.anyio
async def test_dp21_standard_tool_invocation_and_catalog():
    """C01: 표준 읽기 도구 조회 및 안전 실행 검증."""
    tools = GLOBAL_TOOL_REGISTRY.list_public()
    tool_ids = [t["tool_id"] for t in tools]
    assert "financial_product_lookup" in tool_ids
    assert "kb_rule_query" in tool_ids
    assert "data_view_reader" in tool_ids

    # 1. Financial product query
    res_fin = await GLOBAL_TOOL_REGISTRY.invoke("financial_product_lookup", {"category": "deposit"})
    assert res_fin["status"] == "success"
    assert res_fin["result"]["matched_count"] >= 1
    assert any(item["name"] == "BNK 디지털 정기예금" for item in res_fin["result"]["items"])

    # 2. Regulation query
    res_rule = await GLOBAL_TOOL_REGISTRY.invoke("kb_rule_query", {"keyword": "암호화"})
    assert res_rule["status"] == "success"
    assert res_rule["result"]["found"] >= 1


@pytest.mark.anyio
async def test_dp21_unregistered_and_invalid_tool_invocation():
    """C02: 미등록 도구 404 및 필수 인자 누락 422 거부 검증."""
    # Unknown tool
    with pytest.raises(AppError) as exc_404:
        await GLOBAL_TOOL_REGISTRY.invoke("shell_exec_malicious", {})
    assert exc_404.value.status == 404
    assert exc_404.value.code == "TOOL_NOT_FOUND"

    # Missing required argument for data_view_reader
    with pytest.raises(AppError) as exc_422:
        await GLOBAL_TOOL_REGISTRY.invoke("data_view_reader", {})
    assert exc_422.value.status == 422
    assert exc_422.value.code == "TOOL_ARGUMENTS_INVALID"


def test_dp23_workflow_dag_cycle_detection():
    """C03: 순환(Cycle) 및 Self-loop 그래프 검출 시 거부 검증."""
    nodes = [
        WorkflowNode(node_id="n1", node_type="input", title="입력", config={}),
        WorkflowNode(node_id="n2", node_type="llm", title="추론", config={}),
        WorkflowNode(node_id="n3", node_type="output", title="출력", config={}),
    ]

    # 1. Self loop
    edges_self = [
        WorkflowEdge(source_node="n1", target_node="n1"),
    ]
    with pytest.raises(AppError) as exc_loop:
        WorkflowDefinition(workflow_id="wf-loop", name="루프", nodes=nodes, edges=edges_self)
    assert exc_loop.value.code == "WORKFLOW_SELF_LOOP_DETECTED"

    # 2. Cycle (n1 -> n2 -> n3 -> n1)
    edges_cycle = [
        WorkflowEdge(source_node="n1", target_node="n2"),
        WorkflowEdge(source_node="n2", target_node="n3"),
        WorkflowEdge(source_node="n3", target_node="n1"),
    ]
    with pytest.raises(AppError) as exc_cycle:
        WorkflowDefinition(workflow_id="wf-cycle", name="순환", nodes=nodes, edges=edges_cycle)
    assert exc_cycle.value.code == "WORKFLOW_CYCLE_DETECTED"


@pytest.mark.anyio
async def test_dp23_multistep_workflow_pipeline_execution():
    """C04: 다단계 DAG(input -> tool -> llm -> validate -> output) 순차 실행 및 스냅샷 보존 검증."""
    nodes = [
        WorkflowNode(node_id="step1", node_type="input", title="사용자 질문", config={"input_key": "query"}),
        WorkflowNode(
            node_id="step2",
            node_type="read_tool",
            title="금융 상품 조회",
            config={"tool_id": "financial_product_lookup", "arguments": {"category": "deposit"}},
        ),
        WorkflowNode(
            node_id="step3",
            node_type="llm",
            title="결과 분석 요약",
            config={"model_id": "mock-fast", "system_prompt": "금융 전문 상담 에이전트"},
        ),
        WorkflowNode(
            node_id="step4",
            node_type="validate",
            title="품질 검증",
            config={"target_key": "llm_output"},
        ),
        WorkflowNode(node_id="step5", node_type="output", title="최종 답변 반환", config={}),
    ]
    edges = [
        WorkflowEdge(source_node="step1", target_node="step2"),
        WorkflowEdge(source_node="step2", target_node="step3"),
        WorkflowEdge(source_node="step3", target_node="step4"),
        WorkflowEdge(source_node="step4", target_node="step5"),
    ]

    wf = WorkflowDefinition(
        workflow_id="wf-financial-inquiry",
        name="금융 상품 안내 파이프라인",
        nodes=nodes,
        edges=edges,
    )

    # Verify topological execution order
    order = wf.get_execution_order()
    assert order == ["step1", "step2", "step3", "step4", "step5"]

    # Execute workflow pipeline
    result = await GLOBAL_WORKFLOW_RUNNER.run(wf, {"query": "정기예금 금리 안내해줘"})

    assert result["status"] == "completed"
    assert result["step_count"] == 5
    assert len(result["checkpoints"]) == 5
    assert all(cp["status"] == "success" for cp in result["checkpoints"])
    assert result["final_output"] is not None
