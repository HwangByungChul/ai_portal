"""Evaluator only. No evaluation imports are allowed from common_core/backend plan."""
from pathlib import Path
import hashlib
import json
from uuid import UUID,uuid5
from app.documents.plan import build_document_plan
from common_core.ai_pipeline.document.schemas import DocumentMetadata

ROOT=Path(__file__).resolve().parents[3]
NAMESPACE=UUID('978c7162-ee90-442a-b8ee-c2ce23a1a346')


def corpus_plans():
    manifest=json.loads((ROOT/'data/synthetic/document_manifest.json').read_text())
    results=[]
    for doc in manifest['documents']:
        raw=(ROOT/doc['source_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==doc['sha256']
        meta=DocumentMetadata(uuid5(NAMESPACE,doc['owner_tenant_id']),uuid5(NAMESPACE,doc['document_id']),
            uuid5(NAMESPACE,doc['document_id']+doc['version']),uuid5(NAMESPACE,doc['document_id']+doc['version']+':mock'),
            hashlib.sha256(raw).digest(),'mock')
        # Only raw bytes/title/registered IDs are input; evaluator R/EV lists are not passed.
        plan=build_document_plan(raw,doc['title'],'text/markdown',meta)
        results.append((doc,raw,plan))
    return manifest,results


def expected_label(kind,label):
    # Independent expected fixture normalization; no use of runtime alias code.
    if kind=='PROCESS' and label=='가상 여신심사':return '여신심사'
    if kind=='PROCESS' and label=='가상 AI 지원 요청':return 'AI 지원 요청'
    return label


def compare_corpus(manifest,doc,raw,plan):
    entities={x['entity_id']:x for x in manifest['entities']}
    actual=[]
    for rel in plan.graph.relations:
        left=plan.graph.entities[rel.from_ordinal];right=plan.graph.entities[rel.to_ordinal]
        quotes=tuple(sorted(plan.evidence[i].exact_quote for i in rel.evidence_ordinals))
        actual.append((left.entity_type,left.canonical_label,rel.predicate,right.entity_type,right.canonical_label,quotes))
    ev_by_id={x['evidence_id']:x for x in manifest['evidence']};expected=[]
    for rel in doc['relations']:
        left,right=entities[rel['subject_entity_id']],entities[rel['object_entity_id']]
        expected.append((left['kind'],expected_label(left['kind'],left['label']),rel['predicate'],right['kind'],expected_label(right['kind'],right['label']),tuple(sorted(ev_by_id[x]['quote'] for x in rel['evidence_ids']))))
    assert sorted(actual)==sorted(expected)
    source=raw.decode();mapping=[]
    for ev_id in doc['evidence_ids']:
        expected=ev_by_id[ev_id];found=[e for e in plan.evidence if e.exact_quote==expected['quote']]
        assert len(found)==1;ev=found[0]
        assert ev.line_start==expected['line_start'] and ev.line_end==expected['line_end']
        assert source[ev.start_offset:ev.end_offset]==ev.exact_quote
        mapping.append({'evaluator_id':ev_id,'runtime_evidence_ordinal':ev.ordinal,'chunk_ordinal':ev.chunk_ordinal,
            'start_offset':ev.start_offset,'end_offset':ev.end_offset,'line_start':ev.line_start,'line_end':ev.line_end,
            'quote_sha256':hashlib.sha256(ev.exact_quote.encode()).hexdigest()})
    return {'document_id':doc['document_id'],'version':doc['version'],'source_sha256':hashlib.sha256(raw).hexdigest(),
        'chunks':len(plan.chunks),'evidence':len(plan.evidence),'entities':len(plan.graph.entities),'relations':len(plan.graph.relations),
        'coverage':plan.graph.coverage,'coverage_reasons':[reason for _,reason in plan.graph.reasons],
        'embedding_tokens_planned':sum(c.token_count for c in plan.chunks),'batches':len(plan.batches),
        'source_fingerprint':plan.source_fingerprint,'batch_fingerprints':[b.fingerprint for b in plan.batches],
        'evaluator_mapping':mapping,'expected_relations_match':True,'original_intervals_match':True,'paid_calls':0,'persisted_index':False}
