import hashlib
from uuid import uuid4
from common_core.ai_pipeline.document.schemas import DocumentMetadata
from common_core.ai_pipeline.document.parser import parse_source
from common_core.ai_pipeline.document.pipeline import build_document_plan


def make_plan(text, *, media='text/plain',mode='mock',metadata=None,tokenizer=len):
    raw=text.encode();source=parse_source(raw,media)
    metadata=metadata or DocumentMetadata(uuid4(),uuid4(),uuid4(),uuid4(),hashlib.sha256(raw).digest(),mode)
    return source,build_document_plan(source,metadata,tokenizer)
