import json
from pathlib import Path
import pytest
from app.use_cases.meeting import MeetingInput,MeetingResult
from app.use_cases.meeting_quality import evaluate_structure,HUMAN_RUBRIC

CASES=json.loads(Path(__file__).with_name('fixtures').joinpath('meeting-evaluation-v2.json').read_text())['cases']

@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_synthetic_evaluation(case):
    source=MeetingInput.model_validate(case['input']);result=MeetingResult.model_validate(case['result'])
    original=result.model_dump()
    stats=evaluate_structure(result,source)
    assert stats.evidence_valid==case['expected']['evidence_valid'] and stats.human_review_required
    assert result.model_dump()==original
    if stats.evidence_valid:
        normalized=result.model_copy(deep=True).check_evidence(source)
        due=normalized.actions[0].due_date
        assert (due.isoformat() if due else None)==case['expected']['due_date']
        assert stats.unresolved_deadlines==case['expected']['unresolved_deadlines']

def test_human_rubric_has_no_semantic_pass_or_numeric_accuracy():
    assert set(HUMAN_RUBRIC)=={'accuracy','omission','owner','deadline'}
    source=MeetingInput(memo='2026-10-10까지 제출',meeting_date='2026-10-15')
    result=MeetingResult(decisions=[],unresolved=[],actions=[{'text':'제출','quote':source.memo}])
    stats=evaluate_structure(result,source)
    assert stats.past_deadlines==1 and stats.human_review_required
    assert not hasattr(stats,'semantic_pass')


@pytest.mark.parametrize('base', [None, '2026-10-15'])
@pytest.mark.parametrize('expression', [None, '월말'])
def test_unsupported_deadline_normalization_and_quality_count(base, expression):
    source = MeetingInput(memo='월말까지 제출', meeting_date=base)
    result = MeetingResult(decisions=[], unresolved=[], actions=[{
        'text': '제출', 'quote': source.memo, 'due_expression': expression,
        'deadline_status': 'resolved', 'deadline_reason': None,
    }])
    original = result.model_dump()
    stats = evaluate_structure(result, source)
    assert stats.evidence_valid and stats.unresolved_deadlines == 1
    assert stats.past_deadlines == 0 and stats.human_review_required
    assert result.model_dump() == original
    action = result.check_evidence(source).actions[0]
    assert action.due_date is None and action.due_expression == '월말'
    assert action.deadline_status == 'unresolved' and action.deadline_reason == 'unsupported_expression'

@pytest.mark.parametrize('quote,count', [
    ('보고서를 제출하기로 결정했다', 0),
    ('오늘 또는 월말까지 제출', 1),
    ('이번주 안까지 제출', 1),
])
def test_deadline_count_without_model_expression(quote, count):
    source = MeetingInput(memo=quote, meeting_date='2026-10-15')
    result = MeetingResult(decisions=[], unresolved=[], actions=[{'text': '제출', 'quote': quote}])
    stats = evaluate_structure(result, source)
    assert stats.evidence_valid and stats.unresolved_deadlines == count
    action = result.check_evidence(source).actions[0]
    assert action.due_date is None
    assert action.deadline_status == ('unresolved' if count else 'unspecified')


@pytest.mark.parametrize('expression', [None, '월말'])
def test_model_date_cannot_confirm_unsupported_deadline(expression):
    source = MeetingInput(memo='월말까지 제출', meeting_date='2026-10-15')
    result = MeetingResult(decisions=[], unresolved=[], actions=[{
        'text': '제출', 'quote': source.memo, 'due_expression': expression,
        'due_date': '2026-10-31',
    }])
    stats = evaluate_structure(result, source)
    assert not stats.evidence_valid and 'MEETING_DEADLINE_UNCONFIRMED' in stats.error
    assert stats.human_review_required
