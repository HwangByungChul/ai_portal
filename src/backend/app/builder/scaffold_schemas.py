"""Strict, side-effect-free contracts for AI Builder scaffold proposals."""
import re
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator
from app.assets.routes import AssetConfig
from app.builder.schemas import Profile, SaveProfile
from app.errors import AppError
from app.conversations.routes import DocumentRef
from app.workflows.models import WorkflowEdge, WorkflowNode
from app.workflows.approved_models import InputConfig


def _utf8_text(value: str, limit: int, *, nonblank: bool = False) -> None:
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise ValueError("SCAFFOLD_TEXT_INVALID") from None
    if "\x00" in value or size > limit or (nonblank and not value.strip()):
        raise ValueError("SCAFFOLD_TEXT_INVALID")


Notice = Annotated[StrictStr, Field(min_length=1, max_length=500)]

class ScaffoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    target: Literal["agent", "workflow"]
    intent: StrictStr = Field(min_length=1, max_length=4000)
    answers: dict[StrictStr, StrictStr] = Field(default_factory=dict, max_length=20)
    document_refs: list[DocumentRef] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_input(self):
        _utf8_text(self.intent, 4000, nonblank=True)
        if len({(ref.document_id, ref.version_id) for ref in self.document_refs}) != len(self.document_refs):
            raise ValueError("SCAFFOLD_REQUEST_INVALID")
        for key, value in self.answers.items():
            _utf8_text(key, 160, nonblank=True)
            _utf8_text(value, 2000)
            if len(key) > 80:
                raise ValueError("SCAFFOLD_REQUEST_INVALID")
        return self

class ProposalEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    missing_questions: list[Notice] = Field(default_factory=list, max_length=8)
    warnings: list[Notice] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_notices(self):
        for text in self.missing_questions + self.warnings:
            _utf8_text(text, 2000, nonblank=True)
        return self


class AgentProposal(ProposalEnvelope):
    config: AssetConfig
    profile: Profile

    @model_validator(mode="after")
    def match_profile(self):
        # Reuse the exact persistence contract, without generating IDs or doing I/O.
        SaveProfile(client_request_id=UUID(int=0), config=self.config, profile=self.profile)
        _reject_sensitive_fields(self.model_dump(mode="json"))
        return self

class WorkflowProposal(ProposalEnvelope):
    name: StrictStr = Field(min_length=1, max_length=120)
    description: StrictStr = Field(max_length=500)
    nodes: list[WorkflowNode] = Field(min_length=3, max_length=20)
    edges: list[WorkflowEdge] = Field(min_length=2, max_length=30)

    @model_validator(mode="after")
    def validate_graph(self):
        _reject_sensitive_fields(self.model_dump(mode="json"))
        ids = [node.node_id for node in self.nodes]
        node_ids = set(ids)
        pairs = [(edge.source_node, edge.target_node) for edge in self.edges]
        if len(node_ids) != len(ids) or len(set(pairs)) != len(pairs):
            raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
        if any(source not in node_ids or target not in node_ids or source == target for source, target in pairs):
            raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
        _utf8_text(self.name, 480, nonblank=True)
        kinds = [node.node_type for node in self.nodes]
        if kinds.count("input") != 1 or kinds.count("output") != 1 or kinds.count("llm") != 1:
            raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
        for node in self.nodes:
            _utf8_text(node.node_id, 256, nonblank=True)
            _utf8_text(node.title, 512, nonblank=True)
            allowed = {"input": {"input_key"}, "read_tool": set(), "llm": set(), "validate": set(), "output": set()}[node.node_type]
            if set(node.config) - allowed:
                raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
            if node.node_type == "input":
                InputConfig.model_validate(node.config)
        indegree = {node_id: 0 for node_id in node_ids}
        outgoing = {node_id: [] for node_id in node_ids}
        incoming = {node_id: [] for node_id in node_ids}
        for source, target in pairs:
            outgoing[source].append(target)
            incoming[target].append(source)
            indegree[target] += 1
        ready = [node_id for node_id, count in indegree.items() if count == 0]
        visited = 0
        while ready:
            source = ready.pop()
            visited += 1
            for target in outgoing[source]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if visited != len(node_ids):
            raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
        input_id = next(node.node_id for node in self.nodes if node.node_type == "input")
        output_id = next(node.node_id for node in self.nodes if node.node_type == "output")
        reachable = {input_id}
        pending = [input_id]
        while pending:
            source = pending.pop()
            for target in outgoing[source]:
                if target not in reachable:
                    reachable.add(target)
                    pending.append(target)
        ancestors = {output_id}
        pending = [output_id]
        while pending:
            target = pending.pop()
            for source in incoming[target]:
                if source not in ancestors:
                    ancestors.add(source)
                    pending.append(source)
        if reachable != node_ids or ancestors != node_ids:
            raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
        return self

# Only proposals are scanned: user requirements may discuss integration URLs,
# but generated configuration must never contain endpoints or credential values.
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:://|\bwww\.|\bbearer\s+\S+|"
    r"\b(?:api[_ -]?key|password|client[_ -]?secret|secret|token|"
    r"credential|authorization|endpoint|url)\s*[\"']?\s*[:=]\s*\S+|"
    r"\bsk-[a-z0-9_-]{16,})"
)


def _reject_sensitive_fields(value):
    forbidden = ("password", "secret", "token", "credential", "api_key", "apikey",
                 "authorization", "endpoint", "url")
    if isinstance(value, dict):
        for key, item in value.items():
            if any(term in str(key).casefold() for term in forbidden):
                raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
            _reject_sensitive_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive_fields(item)
    elif isinstance(value, str):
        _utf8_text(value, 8000)
        if _SENSITIVE_TEXT.search(value):
            raise ValueError("SCAFFOLD_PROPOSAL_INVALID")

def validate_proposal(target: Literal["agent", "workflow"], payload: object) -> AgentProposal | WorkflowProposal:
    # JSON UUID strings use the shared DocumentRef parser. Text and integer
    # fields remain strict through StrictStr / StrictInt in the shared schemas.
    if target == "agent":
        model = AgentProposal
    elif target == "workflow":
        model = WorkflowProposal
    else:
        raise ValueError("SCAFFOLD_TARGET_INVALID")
    try:
        return model.model_validate(payload)
    except AppError:
        # Profile template validation uses a domain exception. Preserve the pure
        # proposal boundary's single invalid-input error family for callers.
        raise ValueError("SCAFFOLD_PROPOSAL_INVALID") from None
