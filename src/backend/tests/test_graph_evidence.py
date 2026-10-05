from dataclasses import replace
from uuid import uuid4
import pytest
from common_core.ai_pipeline.graphrag.context import validate_graph
from common_core.ai_pipeline.document.schemas import PlanError
from c02_support import make_plan

@pytest.mark.parametrize('attack',['quote','line','offset','scope','foreign_relation','relation_quote','complete'])
def test_exact_relation_evidence_validation(attack):
    source,plan=make_plan('업무의 담당 부서는 팀이다.\n업무의 위험 검토 승인 부서는 다른팀이다.')
    evidence=plan.evidence;graph=plan.graph;e=evidence[0]
    if attack=='quote':evidence=(replace(e,exact_quote='없는 값'),*evidence[1:])
    elif attack=='line':evidence=(replace(e,line_start=2),*evidence[1:])
    elif attack=='offset':evidence=(replace(e,start_offset=e.start_offset+1),*evidence[1:])
    elif attack=='scope':evidence=(replace(e,scope=replace(e.scope,index_id=uuid4())),*evidence[1:])
    elif attack=='foreign_relation':graph=replace(graph,relations=(replace(graph.relations[0],scope=replace(plan.metadata,index_id=uuid4())),*graph.relations[1:]))
    elif attack=='relation_quote':graph=replace(graph,relations=(replace(graph.relations[0],evidence_ordinals=(1,)),*graph.relations[1:]))
    else:evidence=(replace(e,complete=False),*evidence[1:])
    with pytest.raises(PlanError):validate_graph(source,plan.chunks,evidence,graph)

@pytest.mark.parametrize('category',['evidence','entity','relation','edges'])
def test_graph_limits_fail_instead_of_truncate(category):
    source,plan=make_plan('업무의 담당 부서는 팀이다.');graph=plan.graph;evidence=plan.evidence
    if category=='evidence':evidence=evidence*513
    elif category=='entity':graph=replace(graph,entities=graph.entities*257)
    elif category=='relation':graph=replace(graph,relations=graph.relations*1025)
    else:graph=replace(graph,relations=(replace(graph.relations[0],evidence_ordinals=(0,)*2049),))
    with pytest.raises(PlanError,match='INDEX_LIMIT_EXCEEDED'):validate_graph(source,plan.chunks,evidence,graph)
