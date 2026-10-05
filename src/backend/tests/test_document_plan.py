from dataclasses import replace
from uuid import uuid4
import hashlib
import pytest
from common_core.ai_pipeline.document.schemas import DocumentMetadata,PlanError
from common_core.ai_pipeline.document.pipeline import build_document_plan,validate_document_plan
from app.documents.plan import build_document_plan as backend_plan
from c02_support import make_plan


def test_token_chunks_batches_and_determinism():
    counter=lambda text:len(text)*4
    source,plan=make_plan(('가나다라마바사.\n'*400),tokenizer=counter)
    assert len(plan.chunks)>8 and all(1<=c.token_count<=512 for c in plan.chunks)
    assert all(len(b.chunk_ordinals)<=8 and b.token_count<=4096 for b in plan.batches)
    assert tuple(i for b in plan.batches for i in b.chunk_ordinals)==tuple(range(len(plan.chunks)))
    assert all(a.end<=b.start for a,b in zip(plan.chunks,plan.chunks[1:]))
    assert plan==build_document_plan(source,plan.metadata,counter)
    assert plan.source_fingerprint!=build_document_plan(source,replace(plan.metadata,execution_mode='real'),counter).source_fingerprint
    assert plan.batches[0].fingerprint!=build_document_plan(source,replace(plan.metadata,index_id=uuid4()),counter).batches[0].fingerprint


def test_long_sentence_splits_unicode_without_confirming_partial_claims():
    source,plan=make_plan('업무의 담당 부서는 '+'😀'*600+'팀이다.')
    assert len(plan.chunks)>1 and all(len(c.text)<=512 for c in plan.chunks)
    assert not plan.graph.relations
    assert all(not ev.complete for ev in plan.evidence)
    assert all(source.raw_text[e.start_offset:e.end_offset]==e.exact_quote for e in plan.evidence)


def test_preflight_limit_never_silently_truncates():
    with pytest.raises(PlanError,match='INDEX_LIMIT_EXCEEDED'):make_plan('가'*3000,tokenizer=lambda s:len(s)*32)

@pytest.mark.parametrize('count',[lambda _:0,lambda _:-1,lambda _:1.5,lambda _:True],ids=['zero','negative','fraction','bool'])
def test_invalid_token_counter(count):
    with pytest.raises(PlanError,match='TOKENIZER_INVALID'):make_plan('내용',tokenizer=count)

@pytest.mark.parametrize('field,value',[('execution_mode','other'),('embedding_dimensions',3072),('parser_revision','bad'),('pipeline_revision','bad'),('embedding_model','other'),('tenant_id','claimed')])
def test_metadata_contract(field,value):
    _,plan=make_plan('내용')
    with pytest.raises(PlanError):replace(plan.metadata,**{field:value})


def test_plan_rejects_tampered_batch_and_source_hash():
    source,plan=make_plan('가상 여신심사의 담당 부서는 팀이다.')
    with pytest.raises(PlanError):validate_document_plan(source,replace(plan,batches=(replace(plan.batches[0],fingerprint='0'*64),)),len)
    with pytest.raises(PlanError,match='SOURCE_INTEGRITY_FAILED'):build_document_plan(source,replace(plan.metadata,source_sha256=b'\0'*32),len)


def test_backend_offline_adapter_no_network(monkeypatch):
    import socket
    calls=[]
    def forbidden(*a,**k):calls.append(True);raise AssertionError('NETWORK_NOT_ALLOWED')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    raw='가상 여신심사의 담당 부서는 팀이다.'.encode();meta=DocumentMetadata(uuid4(),uuid4(),uuid4(),uuid4(),hashlib.sha256(raw).digest(),'mock')
    plan=backend_plan(raw,'제목','text/plain',meta)
    assert len(plan.graph.relations)==1 and calls==[] and plan.chunks[0].token_count<=512
