"""Current permission resolution for published document versions only."""
from dataclasses import dataclass
from uuid import UUID

from app.db import tenant_transaction
from app.types import AuthContext


class DocumentUnavailable(ValueError):
    def __init__(self):
        super().__init__('DOCUMENT_UNAVAILABLE')


@dataclass(frozen=True)
class ReadableVersion:
    """Internal authorized metadata; never serialize source key/hash to an admin list."""
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    version_no: int
    index_id: UUID
    execution_mode: str
    title: str
    source_object_key: str
    source_sha256: bytes
    media_type: str
    byte_length: int
    character_length: int


async def resolve_readable_version(pool, ctx: AuthContext, document_id: UUID,
                                   version_id: UUID | None = None) -> ReadableVersion:
    """Select latest *allowed* version; an unshared newer version cannot hide v1."""
    if not isinstance(document_id, UUID) or (version_id is not None and not isinstance(version_id, UUID)):
        raise DocumentUnavailable()
    try:
        async with tenant_transaction(pool, ctx) as conn:
            row = await (await conn.execute('''
                SELECT v.tenant_id,v.document_id,v.version_id,v.version_no,i.index_id,
                       i.execution_mode,v.title,v.source_object_key,v.source_sha256,
                       v.media_type,v.byte_length,v.character_length
                FROM rag.document_versions v JOIN rag.index_builds i
                 ON (i.tenant_id,i.document_id,i.version_id)=(v.tenant_id,v.document_id,v.version_id)
                WHERE v.document_id=%s AND (%s::uuid IS NULL OR v.version_id=%s)
                 AND security.document_can_read(v.tenant_id,v.document_id,v.version_id,i.index_id)
                ORDER BY v.version_no DESC,v.version_id LIMIT 1
                ''', (document_id, version_id, version_id))).fetchone()
            if row is None:
                raise DocumentUnavailable()
            return ReadableVersion(**row)
    except ValueError:
        # Session/membership revocation and nonexistent objects share the same outcome.
        raise DocumentUnavailable() from None
