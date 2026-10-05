from dataclasses import replace
from uuid import uuid4
import pytest
from c02_support import make_plan

@pytest.mark.parametrize('text,rule,predicate',[
 ('업무의 담당 부서는 팀이다.','GR01','담당부서'),
 ('업무의 위험 검토 승인 부서는 팀이다.','GR02','위험검토승인부서'),
 ('업무의 기록 보관 담당 부서는 팀이다.','GR03','기록보관담당부서'),
 ('업무의 기록 보관 기간은 180일이다.','GR04','기록보관기간'),
 ('업무는 승인 검토 전에 상환능력 점검표를 작성한다.','GR05','필수점검표'),
 ('업무의 기록 보관 담당 부서는 팀이다.\n팀은 업무 기록의 누락 여부를 매월 5일에 점검한다.','GR06','누락점검일'),
 ('사람의 개인 시연 리허설은 목요일 오후 3시에 진행한다.','GR07','개인리허설일정'),
 ('지원 요청의 접수 담당은 팀이다.','GR08','접수담당'),
 ('팀은 요청 접수 후 2영업일 이내에 접수 확인을 통보한다.','GR09','접수확인기한'),
 ('가상 AI 서비스의 복구 목표는 4시간이다.','GR10','복구목표')],ids=['GR01','GR02','GR03','GR04','GR05','GR06','GR07','GR08','GR09','GR10'])
def test_positive_rules(text,rule,predicate):
    _,plan=make_plan(text)
    matches=[r for r in plan.graph.relations if r.rule_id==rule]
    assert len(matches)==1 and matches[0].predicate==predicate
    assert plan.graph.coverage=='complete'

@pytest.mark.parametrize('text',['업무의 담당 부서는 팀이 아니다.','업무의 담당 부서는 팀 또는 다른팀이다.','특정 경우 업무의 담당 부서는 팀이다.','그의 담당 부서는 팀이다.','업무의 담당 부서는 팀일 수 있다.','업무의 담당 부서는 팀이다. 예외가 있다.'],ids=['negative','disjunction','condition','pronoun','possible','separate-exception'])
def test_unsupported_and_uncertain_claims(text):
    _,plan=make_plan(text)
    assert not plan.graph.relations
    assert plan.graph.coverage=='partial'


def test_conflicting_values_withhold_both():
    _,plan=make_plan('업무의 담당 부서는 팀이다.\n업무의 담당 부서는 다른팀이다.')
    assert not plan.graph.relations and any(reason=='CONFLICTING_VALUES' for _,reason in plan.graph.reasons)


def test_same_relation_only_links_its_actual_evidence():
    _,plan=make_plan('업무의 담당 부서는 팀이다.\n업무의 위험 검토 승인 부서는 다른팀이다.\n업무의 담당 부서는 팀이다.')
    responsible=next(r for r in plan.graph.relations if r.predicate=='담당부서');risk=next(r for r in plan.graph.relations if r.predicate=='위험검토승인부서')
    assert responsible.evidence_ordinals==(0,2) and risk.evidence_ordinals==(1,)


def test_alias_and_semantic_key_are_tenant_scoped():
    source,a=make_plan('가상 여신심사의 담당 부서는 팀이다.\n여신심사의 기록 보관 기간은 180일이다.')
    assert len([e for e in a.graph.entities if e.entity_type=='PROCESS'])==1
    from common_core.ai_pipeline.document.pipeline import build_document_plan
    b=build_document_plan(source,replace(a.metadata,tenant_id=uuid4(),index_id=uuid4()),len)
    assert a.graph.entities[0].semantic_key!=b.graph.entities[0].semantic_key


def test_missing_or_conflicting_responsibility_does_not_infer_schedule():
    for text in ['팀은 업무 기록의 누락 여부를 매월 5일에 점검한다.',
                 '업무의 기록 보관 담당 부서는 팀이다.\n업무의 기록 보관 담당 부서는 다른팀이다.\n팀은 업무 기록의 누락 여부를 매월 5일에 점검한다.']:
        _,plan=make_plan(text);assert not any(r.rule_id=='GR06' for r in plan.graph.relations)


def test_relative_time_and_conditions_preserved():
    _,plan=make_plan('팀은 요청 접수 후 2영업일 이내에 접수 확인을 통보한다.\n업무는 승인 검토 전에 점검표를 작성한다.')
    rel=next(r for r in plan.graph.relations if r.rule_id=='GR09');assert dict(rel.properties)=={'qualifier':'이내','relative_trigger':'요청 접수 후'}
    assert plan.graph.entities[rel.to_ordinal].label=='2영업일'
    assert dict(next(r for r in plan.graph.relations if r.rule_id=='GR05').properties)['condition']=='승인 검토 전에'


@pytest.mark.parametrize('text',['업무는 필요하면 점검표를 작성한다.','업무는 조건에 따라 점검표를 작성한다.'])
def test_condition_cannot_become_artifact_label(text):
    _,plan=make_plan(text);assert not plan.graph.relations and plan.graph.coverage=='partial'
