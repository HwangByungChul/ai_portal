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
