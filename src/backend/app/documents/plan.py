"""Offline planning adapter. Caller must already authorize the exact source/job.

This module does not read files, perform ACL decisions, call providers or write
DB rows. C03 supplies currently authorized stored bytes and registration IDs.
"""
from common_core.ai_pipeline.document.parser import parse_source
from common_core.ai_pipeline.document.pipeline import build_document_plan as build_core_plan
from common_core.ai_pipeline.document.schemas import DocumentMetadata
from app.ai.token_limits import encoding
from app.documents.storage import validate_source


def build_document_plan(raw_bytes: bytes,title: str,media_type: str,metadata: DocumentMetadata):
    validate_source(raw_bytes,title,media_type)
    source=parse_source(raw_bytes,media_type)
    codec=encoding('cl100k_base')
    return build_core_plan(source,metadata,lambda text: len(codec.encode(text,disallowed_special=())))
