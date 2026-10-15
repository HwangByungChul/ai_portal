import pytest
from app.errors import AppError
from app.workflows.models import WorkflowDefinition, WorkflowNode, WorkflowEdge
from app.workflows.runner import WorkflowRunner

@pytest.mark.anyio
async def test_controlled_workflow_successful_execution():
    """T6b: Standard DAG executes sequentially through input, tool, llm, output."""
    wf = WorkflowDefinition(
        workflow_id="wf-test-success",
        name="통합 테스트 워크플로우",
        nodes=[
            WorkflowNode(node_id="n1", node_type="input", title="사용자 입력", config={"input_key": "query"}),
            WorkflowNode(node_id="n2", node_type="read_tool", title="상품 조회", config={"tool_id": "financial_product_lookup", "arguments": {"category": "deposit"}}),
            WorkflowNode(node_id="n3", node_type="llm", title="결과 분석", config={"model_id": "mock-fast", "system_prompt": "You are a financial advisor.", "user_template": "Query: {{query}}, Products: {{tool_output}}"}),
            WorkflowNode(node_id="n4", node_type="output", title="최종 응답", config={}),
        ],
        edges=[
            WorkflowEdge(source_node="n1", target_node="n2"),
            WorkflowEdge(source_node="n2", target_node="n3"),
            WorkflowEdge(source_node="n3", target_node="n4"),
        ],
    )

    runner = WorkflowRunner()
    res = await runner.run(wf, {"query": "예금 상품 추천"})

    assert res["status"] == "completed", f"Checkpoints: {res['checkpoints']}"
    assert res["step_count"] == 4
    checkpoints = res["checkpoints"]
    assert checkpoints[0]["node_id"] == "n1" and checkpoints[0]["status"] == "success"
    assert checkpoints[1]["node_id"] == "n2" and checkpoints[1]["status"] == "success"
    assert checkpoints[2]["node_id"] == "n3" and checkpoints[2]["status"] == "success"
    # LLM output is not empty
    assert len(checkpoints[2]["output"]) > 0
    assert checkpoints[3]["node_id"] == "n4" and checkpoints[3]["status"] == "success"


@pytest.mark.anyio
async def test_controlled_workflow_aborts_on_failed_node():
    """T6b: Workflow aborts immediately when a node fails, downstream nodes never execute."""
    wf = WorkflowDefinition(
        workflow_id="wf-test-fail",
        name="실패 중단 워크플로우",
        nodes=[
            WorkflowNode(node_id="n1", node_type="input", title="입력", config={"input_key": "target"}),
            WorkflowNode(node_id="n2", node_type="validate", title="검증", config={"target_key": "target"}),
            WorkflowNode(node_id="n3", node_type="output", title="도달하지 않아야 하는 노드", config={}),
        ],
        edges=[
            WorkflowEdge(source_node="n1", target_node="n2"),
            WorkflowEdge(source_node="n2", target_node="n3"),
        ],
    )

    runner = WorkflowRunner()
    # Providing empty input causes validate node to fail
    res = await runner.run(wf, {"target": ""})

    assert res["status"] == "failed"
    # Step count must be 2: n1 executed, n2 failed, n3 was ABORTED and NOT executed
    assert res["step_count"] == 2
    assert res["checkpoints"][0]["status"] == "success"
    assert res["checkpoints"][1]["status"] == "failed"
    assert not any(c["node_id"] == "n3" for c in res["checkpoints"])


@pytest.mark.anyio
async def test_controlled_workflow_cycle_detection():
    """T6b: Cyclic workflows are detected and rejected at definition time."""
    with pytest.raises(AppError) as exc:
        WorkflowDefinition(
            workflow_id="wf-cycle",
            name="순환 워크플로우",
            nodes=[
                WorkflowNode(node_id="a", node_type="input", title="A"),
                WorkflowNode(node_id="b", node_type="read_tool", title="B"),
            ],
            edges=[
                WorkflowEdge(source_node="a", target_node="b"),
                WorkflowEdge(source_node="b", target_node="a"),
            ],
        )
    assert exc.value.code == "WORKFLOW_CYCLE_DETECTED"
    assert exc.value.status == 422
