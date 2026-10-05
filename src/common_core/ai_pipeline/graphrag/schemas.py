"""Graph instances are bound to a single immutable source/index context."""
from dataclasses import dataclass
from ..document.schemas import DocumentMetadata,Chunk,Batch

@dataclass(frozen=True)
class Evidence:
    ordinal: int
    chunk_ordinal: int
    unit_ordinal: int
    start_offset: int
    end_offset: int
    line_start: int
    line_end: int
    exact_quote: str
    complete: bool
    scope: DocumentMetadata

@dataclass(frozen=True)
class Entity:
    ordinal: int
    entity_type: str
    label: str
    canonical_label: str
    semantic_key: str
    scope: DocumentMetadata

@dataclass(frozen=True)
class Relation:
    ordinal: int
    rule_id: str
    from_ordinal: int
    to_ordinal: int
    predicate: str
    properties: tuple[tuple[str,str],...]
    evidence_ordinals: tuple[int,...]
    scope: DocumentMetadata

@dataclass(frozen=True)
class GraphPlan:
    metadata: DocumentMetadata
    entities: tuple[Entity,...]
    relations: tuple[Relation,...]
    coverage: str
    reasons: tuple[tuple[int,str],...]

@dataclass(frozen=True)
class DocumentPlan:
    metadata: DocumentMetadata
    source_fingerprint: str
    chunks: tuple[Chunk,...]
    evidence: tuple[Evidence,...]
    graph: GraphPlan
    batches: tuple[Batch,...]
