"""Deterministic bounded document plan, with injected offline token counting."""
from dataclasses import asdict
import hashlib
import json
from .parser import parse_source
from .schemas import DocumentMetadata,Batch,PlanError
from .chunker import chunk_source,checked_count
from ..graphrag.evidence import build_evidence
from ..graphrag.extractor import extract_graph
from ..graphrag.context import validate_graph
from ..graphrag.schemas import DocumentPlan


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def _context(metadata):
    return {k:(v.hex() if type(v) is bytes else str(v)) for k,v in asdict(metadata).items()}


def build_document_plan(source,metadata: DocumentMetadata,tokenizer) -> DocumentPlan:
    if source!=parse_source(source.raw_text.encode('utf-8'),source.media_type) or source.source_sha256!=metadata.source_sha256 or source.parser_revision!=metadata.parser_revision:
        raise PlanError('SOURCE_INTEGRITY_FAILED')
    chunks=chunk_source(source,tokenizer);evidence=build_evidence(source,chunks,metadata)
    graph=extract_graph(source,chunks,evidence,metadata);validate_graph(source,chunks,evidence,graph)
    context=_context(metadata);context['chunk_token_limit']='512';context['overlap']='0';context['batch_chunk_limit']='8'
    source_fingerprint=_digest(context);batches=[]
    for start in range(0,len(chunks),8):
        group=chunks[start:start+8];tokens=sum(c.token_count for c in group);ordinal=len(batches)
        if tokens>4096 or ordinal>=16:raise PlanError('INDEX_LIMIT_EXCEEDED')
        fingerprint=_digest({'context':context,'source_fingerprint':source_fingerprint,'batch_ordinal':ordinal,
            'chunks':[(c.ordinal,c.text,c.token_count) for c in group]})
        batches.append(Batch(ordinal,tuple(c.ordinal for c in group),tokens,fingerprint))
    return DocumentPlan(metadata,source_fingerprint,chunks,evidence,graph,tuple(batches))


def validate_document_plan(source,plan,tokenizer):
    if (len(plan.chunks)>128 or len(plan.batches)>16 or any(c.token_count>512 for c in plan.chunks)):
        raise PlanError('INDEX_LIMIT_EXCEEDED')
    validate_graph(source,plan.chunks,plan.evidence,plan.graph)
    if plan!=build_document_plan(source,plan.metadata,tokenizer):raise PlanError('DOCUMENT_PLAN_INVALID')
