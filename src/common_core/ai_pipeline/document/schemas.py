"""Immutable source and plan contracts; no authority or provider dependencies."""
from dataclasses import dataclass
from uuid import UUID

PARSER_REVISION = 'source-map-v1'
PIPELINE_REVISION = 'rules-v1'


class PlanError(ValueError):
    """Safe code only; never include source text in the error."""


@dataclass(frozen=True)
class SourceLine:
    start: int
    end: int
    kind: str


@dataclass(frozen=True)
class ParsedSource:
    raw_text: str
    source_sha256: bytes
    text: str
    mapping: tuple[tuple[int, int], ...]
    lines: tuple[SourceLine, ...]
    warnings: tuple[str, ...]
    parser_revision: str = PARSER_REVISION
    media_type: str = 'text/plain'


@dataclass(frozen=True)
class DocumentMetadata:
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    index_id: UUID
    source_sha256: bytes
    execution_mode: str
    parser_revision: str = PARSER_REVISION
    pipeline_revision: str = PIPELINE_REVISION
    embedding_model: str = 'text-embedding-3-small'
    embedding_dimensions: int = 1536

    def __post_init__(self):
        if (not all(type(v) is UUID for v in (self.tenant_id,self.document_id,self.version_id,self.index_id))
                or type(self.source_sha256) is not bytes or len(self.source_sha256)!=32
                or self.execution_mode not in ('mock','real') or self.parser_revision!=PARSER_REVISION
                or self.pipeline_revision!=PIPELINE_REVISION or self.embedding_model!='text-embedding-3-small'
                or type(self.embedding_dimensions) is not int or self.embedding_dimensions!=1536):
            raise PlanError('PLAN_METADATA_INVALID')


@dataclass(frozen=True)
class Unit:
    ordinal: int
    start: int
    end: int
    complete: bool
    kind: str


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    start: int
    end: int
    text: str
    token_count: int
    units: tuple[Unit, ...]


@dataclass(frozen=True)
class Batch:
    ordinal: int
    chunk_ordinals: tuple[int, ...]
    token_count: int
    fingerprint: str
