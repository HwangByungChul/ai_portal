"""Workflow DAG Models, Validation, and Topological Sorter."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator
from app.errors import AppError

NodeType = Literal["input", "read_tool", "llm", "validate", "output"]

class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: StrictStr = Field(min_length=1, max_length=64)
    node_type: NodeType
    title: StrictStr = Field(min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)

class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_node: StrictStr
    target_node: StrictStr

class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: StrictStr
    name: StrictStr
    description: StrictStr = ""
    nodes: list[WorkflowNode] = Field(min_length=2, max_length=20)
    edges: list[WorkflowEdge] = Field(min_length=1, max_length=30)
    max_steps: int = 20

    @model_validator(mode="after")
    def validate_dag(self):
        node_ids = {n.node_id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise AppError("WORKFLOW_DUPLICATE_NODES", 422)

        # Edge endpoints validation
        for edge in self.edges:
            if edge.source_node not in node_ids or edge.target_node not in node_ids:
                raise AppError("WORKFLOW_EDGE_ENDPOINT_INVALID", 422)
            if edge.source_node == edge.target_node:
                raise AppError("WORKFLOW_SELF_LOOP_DETECTED", 422)

        # Cycle detection using Kahn's algorithm
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in self.edges:
            adj[edge.source_node].append(edge.target_node)
            in_degree[edge.target_node] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        if not queue:
            raise AppError("WORKFLOW_CYCLE_DETECTED", 422)

        visited_count = 0
        sorted_nodes: list[str] = []
        while queue:
            curr = queue.pop(0)
            sorted_nodes.append(curr)
            visited_count += 1
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(self.nodes):
            raise AppError("WORKFLOW_CYCLE_DETECTED", 422)

        return self

    def get_execution_order(self) -> list[str]:
        # Compute topological order
        node_ids = {n.node_id for n in self.nodes}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in self.edges:
            adj[edge.source_node].append(edge.target_node)
            in_degree[edge.target_node] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        sorted_nodes: list[str] = []
        while queue:
            curr = queue.pop(0)
            sorted_nodes.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        return sorted_nodes
