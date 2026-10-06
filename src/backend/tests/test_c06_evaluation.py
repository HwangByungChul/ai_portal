import copy,json
from pathlib import Path
import pytest
from scripts.c06_evaluate import runtime_payload,map_evidence,score,ROOT
from common_core.ai_pipeline.graphrag.answer import required_predicates,select_relevant,FactPacket

@pytest.fixture
def gold():
    manifest=json.loads((ROOT/'data/synthetic/document_manifest.json').read_text())
    questions=json.loads((ROOT/'data/evaluation/questions.json').read_text())['questions']
    mapping={(x['document_id'],x['version']):{'document_id':x['document_id'],'version_id':x['version']} for x in manifest['documents']}
    return manifest,questions,mapping

def test_runtime_request_contains_no_gold_fields(gold):
    m,qs,mapping=gold
    for question in qs:
        body=runtime_payload(question,mapping)
        assert set(body)<= {'agent_key','prompt','client_send_id','document_refs'}
        assert body['prompt']==question['prompt']
        assert 'EV-' not in json.dumps(body) and 'expected' not in json.dumps(body)
    assert qs[0]['execution']['status']=='not_run'

def test_exact_evidence_mapping_rejects_wrong_version_and_location(gold):
    m,qs,mapping=gold;e=m['evidence'][0];item={'document_id':e['document_id'],'version_id':e['version'],'quote':e['quote'],'location':{'line_start':e['line_start'],'line_end':e['line_end']},'content_status':'available'}
    assert map_evidence([item],m,mapping)==([e['evidence_id']],[])
    for changed in ({'version_id':'wrong'},{'quote':e['quote']+'invented'},{'location':{'line_start':0,'line_end':0}}):
        assert map_evidence([{**item,**changed}],m,mapping)[1]

def test_denial_with_provider_call_is_failure(gold):
    m,qs,mapping=gold
    q=next(x for x in qs if x['question_id']=='Q-017')
    assert score(q,{'category':'deny','http_status':404,'provider_calls_delta':1},m,mapping)['verdict']=='fail'
    assert score(q,{'category':'deny','http_status':404,'provider_calls_delta':0},m,mapping)['verdict']=='pass'

def test_accessible_unrelated_fact_does_not_pass(gold):
    m,qs,mapping=gold;q=qs[0];e=next(x for x in m['evidence'] if x['evidence_id']=='EV-A-R2-01')
    item={'document_id':e['document_id'],'version_id':e['version'],'quote':e['quote'],'location':{'line_start':e['line_start'],'line_end':e['line_end']},'content_status':'available'}
    result=score(q,{'category':'answer','http_status':202,'text':'기록관리팀 [1]','items':[item]},m,mapping)
    assert result['verdict']=='fail' and 'missing_required_evidence' in result['reasons']

@pytest.mark.parametrize('prompt,expected',[
 ('계약검토의 담당 부서와 위험 검토 승인 부서를 연결해 주세요.',{'담당부서','위험검토승인부서'}),
 ('계약검토 기록은 며칠 보관하나요?',{'기록보관기간'}),
 ('계약검토의 위험 검토 승인과 기록 보관은 어느 부서가 맡나요?',{'위험검토승인부서','기록보관담당부서'}),
 ('계약검토 기록 파기 승인자는 누구인가요?',set()),
])
def test_generic_question_roles_and_out_of_ontology(prompt,expected):
    assert set(required_predicates(prompt))==expected

def test_personal_reference_requires_single_authorized_subject():
    def p(fid,name):return FactPacket(fid,'개인리허설일정',name,'수요일 정오',(),{'quote':'원문'},'X')
    one=p('F0','사용자-X');two=p('F1','사용자-Y')
    assert select_relevant('내 개인 리허설 일정을 알려 주세요.',(one,))[0]==(one,)
    assert not select_relevant('내 개인 리허설 일정을 알려 주세요.',(one,two))[0]
    assert not select_relevant('다른 개인 리허설 일정은?',(one,))[0]


def test_relation_words_without_their_own_proof_fail(gold):
    m,qs,mapping=gold;q=next(x for x in qs if x['question_id']=='Q-007')
    result=score(q,{'category':'answer','http_status':202,'text':'업무의 담당부서: 여신심사팀 [1]\n업무의 위험검토승인부서: 위험관리팀 [1]','items':[]},m,mapping)
    assert 'missing_or_misbound_relation' in result['reasons']
