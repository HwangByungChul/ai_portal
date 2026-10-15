from copy import deepcopy
import pytest
from pydantic import ValidationError
from app.use_cases.meeting import MeetingInput,MeetingResult,meeting_contract


def result():
    return {'decisions':[{'text':'단계적으로 진행','quote':'단계적으로 진행한다.'}],
            'unresolved':[], 'actions':[{'text':'자료 준비','quote':'김담당이 2026-10-20까지 자료를 준비한다.',
                                      'assignee':'김담당','due_date':'2026-10-20'}]}


def test_actual_quotes_confirm_owner_and_date():
    source=MeetingInput(memo='단계적으로 진행한다. 김담당이 2026-10-20까지 자료를 준비한다.')
    assert MeetingResult.model_validate(result()).check_evidence(source).actions[0].assignee=='김담당'

@pytest.mark.parametrize('memo',['','   ','메모\x00내용'])
def test_invalid_memo_is_rejected(memo):
    with pytest.raises(ValidationError):MeetingInput(memo=memo)

@pytest.mark.parametrize('field,value,error',[
    ('quote','원문에 없는 문장','MEETING_EVIDENCE_INVALID'),
    ('assignee','미등록담당','MEETING_ASSIGNEE_UNCONFIRMED'),
    ('due_date','2026-10-21','MEETING_DEADLINE_UNCONFIRMED')])
def test_unconfirmed_action_is_not_published(field,value,error):
    data=deepcopy(result());data['actions'][0][field]=value
    with pytest.raises(ValueError,match=error):
        MeetingResult.model_validate(data).check_evidence(MeetingInput(memo='단계적으로 진행한다. 김담당이 2026-10-20까지 자료를 준비한다.'))


def test_unknown_owner_and_deadline_remain_null():
    data={'decisions':[],'unresolved':[],'actions':[{'text':'검토','quote':'검토하기로 했다.'}]}
    action=MeetingResult.model_validate(data).check_evidence(MeetingInput(memo='검토하기로 했다.')).actions[0]
    assert action.assignee is None and action.due_date is None


def test_contract_is_deterministic_and_requires_no_external_tool():
    contract=meeting_contract()
    assert contract==meeting_contract() and contract['use_case_id']=='AGENT_03'
    assert contract['required_tools']==[] and len(contract['manifest_digest'])==64
    with pytest.raises(ValidationError):MeetingInput(memo='메모',system_prompt='override')

from datetime import date
from uuid import UUID

REF={'document_id':'00000000-0000-0000-0000-000000000001','version_id':'00000000-0000-0000-0000-000000000002'}
KEY='document:'+REF['version_id']

def action_result(quote,**fields):
    return MeetingResult.model_validate({'decisions':[],'unresolved':[],'actions':[{'text':'자료 준비','quote':quote,**fields}]})

def test_documents_only_exact_selected_version_and_owner():
    source=MeetingInput(memo='',document_refs=[REF],meeting_date='2026-10-15')
    item=action_result('김담당이 내일까지 제출',source_ref=KEY,assignee='김담당').check_evidence(source,{KEY:'김담당이 내일까지 제출'}).actions[0]
    assert item.due_date==date(2026,10,16) and item.deadline_status=='resolved'
    for sources in ({}, {'document:other':'김담당이 내일까지 제출'}, {KEY:'다른 원문'}):
        with pytest.raises(ValueError,match='MEETING_EVIDENCE_INVALID'):
            action_result('김담당이 내일까지 제출',source_ref=KEY).check_evidence(source,sources)
    with pytest.raises(ValueError,match='MEETING_EVIDENCE_INVALID'):
        action_result('김담당이 내일까지 제출',source_ref='document:other').check_evidence(source,{'document:other':'김담당이 내일까지 제출'})

@pytest.mark.parametrize('values',[
    {'memo':'x'*4001}, {'memo':'메모','document_refs':[REF]*2},
    {'memo':'메모','document_refs':[REF]*4}, {'memo':'메모','meeting_date':'20261015'},
    {'memo':'메모','meeting_date':123}, {'memo':'메모','meeting_date':'2026-02-29'},
])
def test_input_bounds_and_strict_date(values):
    with pytest.raises(ValidationError):MeetingInput(**values)

def test_server_overwrites_claimed_status_and_requires_quote_date():
    source=MeetingInput(memo='내일 제출')
    action=action_result(source.memo,deadline_status='resolved',deadline_reason='model claim').check_evidence(source).actions[0]
    assert action.due_date is None and action.deadline_status=='unresolved' and action.deadline_reason=='meeting_date_required'
    with pytest.raises(ValueError,match='MEETING_DEADLINE_UNCONFIRMED'):
        action_result(source.memo,due_date='2026-10-16').check_evidence(source)
    with pytest.raises(ValueError,match='MEETING_DEADLINE_UNCONFIRMED'):
        action_result(source.memo,due_expression='2026-10-16').check_evidence(source)

def test_legacy_result_default_source_and_original_null_fields():
    source=MeetingInput(memo='검토하기로 했다.')
    result=action_result(source.memo)
    assert result.actions[0].source_ref=='memo'
    assert result.check_evidence(source).actions[0].deadline_status=='unspecified'
    assert meeting_contract()['contract_revision']==2
    assert set(meeting_contract()['rules_sha256'])=={'meeting_dates.py','meeting_quality.py'}

from datetime import datetime

@pytest.mark.parametrize('value',[datetime(2026,10,15),True,20261015, '2026-10-15T00:00:00'])
def test_meeting_date_rejects_coercion(value):
    with pytest.raises(ValidationError):MeetingInput(memo='메모',meeting_date=value)

def test_relative_model_date_mismatch_is_rejected():
    source=MeetingInput(memo='내일까지 제출',meeting_date='2026-10-15')
    with pytest.raises(ValueError,match='MEETING_DEADLINE_UNCONFIRMED'):
        action_result(source.memo,due_date='2026-10-17').check_evidence(source)
    assert action_result(source.memo,due_date='2026-10-16').check_evidence(source).actions[0].due_date==date(2026,10,16)

def test_equivalent_expressions_are_idempotent():
    source=MeetingInput(memo='오늘 즉 2026-10-15 제출',meeting_date='2026-10-15')
    result=action_result(source.memo).check_evidence(source)
    before=result.model_dump()
    assert result.check_evidence(source).model_dump()==before
