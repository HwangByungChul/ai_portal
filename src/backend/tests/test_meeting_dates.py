from datetime import date
import pytest
from app.use_cases.meeting_dates import resolve_deadline

@pytest.mark.parametrize('base,expression,expected',[
    ('2024-02-28','내일','2024-02-29'),('2024-02-29','모레','2024-03-02'),
    ('2026-12-31','1일 후','2027-01-01'),('2026-10-15','오늘','2026-10-15'),
    ('2026-10-18','이번주 월요일','2026-10-12'),('2026-12-31','다음주 월요일','2027-01-04'),
    ('2026-10-19','다음주 일요일','2026-11-01'),('2026-10-15','0일후','2026-10-15'),
])
def test_calendar_rules(base,expression,expected):
    resolved=resolve_deadline(expression+'까지 제출',date.fromisoformat(base))
    assert resolved.due_date==date.fromisoformat(expected) and resolved.status=='resolved'

@pytest.mark.parametrize('quote,base,reason',[
    ('내일 제출',None,'meeting_date_required'),('다음주 제출',date(2026,10,15),'ambiguous_expression'),
    ('조속히 제출',date(2026,10,15),'ambiguous_expression'),('2영업일 후 제출',date(2026,10,15),'ambiguous_expression'),
    ('오늘 또는 내일 제출',date(2026,10,15),'conflicting_expressions'),
    ('2026-02-29 제출',None,'invalid_calendar_date'),('99999일후 제출',date(2026,10,15),'offset_out_of_bounds'),
    ('1일후 제출',date(9999,12,31),'calendar_out_of_bounds'),
])
def test_unresolved_dates(quote,base,reason):
    result=resolve_deadline(quote,base)
    assert result.due_date is None and result.reason==reason and result.human_review_required

def test_explicit_iso_without_meeting_base_and_past_flag():
    assert resolve_deadline('2026-10-20 제출',None).due_date==date(2026,10,20)
    assert resolve_deadline('2026-10-10 제출',date(2026,10,15)).reason=='past_due'

def test_expression_must_be_verbatim_and_all_conflicts_considered():
    assert resolve_deadline('오늘 제출',date(2026,10,15),'내일').reason=='expression_not_in_quote'
    assert resolve_deadline('오늘 또는 내일 제출',date(2026,10,15),'오늘').reason=='conflicting_expressions'
    assert resolve_deadline('월말 제출',date(2026,10,15),'월말').reason=='unsupported_expression'
    assert resolve_deadline('오늘 즉 2026-10-15 제출',date(2026,10,15)).status=='resolved'


@pytest.mark.parametrize('phrase', ['월말', '월초', '분기말', '연내', '다음달', '이달', '주말'])
@pytest.mark.parametrize('base', [None, date(2026, 10, 15)])
def test_unsupported_periods_survive_optional_expression_omission(phrase, base):
    quote = phrase + '까지 제출'
    omitted = resolve_deadline(quote, base)
    supplied = resolve_deadline(quote, base, phrase)
    assert omitted == supplied
    assert omitted.status == 'unresolved' and omitted.reason == 'unsupported_expression'
    assert omitted.due_date is None and omitted.human_review_required

@pytest.mark.parametrize('expression', [None, '오늘', '월말'])
def test_supported_date_cannot_hide_unsupported_period(expression):
    result = resolve_deadline('오늘 또는 월말까지 제출', date(2026, 10, 15), expression)
    assert result.status == 'unresolved' and result.due_date is None
    assert result.reason == 'unsupported_expression' and result.human_review_required

@pytest.mark.parametrize('expression', [None, '이번주'])
def test_this_week_without_weekday_remains_ambiguous(expression):
    result = resolve_deadline('이번주 안까지 제출', date(2026, 10, 15), expression)
    assert result.status == 'unresolved' and result.reason == 'ambiguous_expression'
    assert result.due_date is None and result.human_review_required

def test_quote_without_deadline_remains_unspecified():
    result = resolve_deadline('보고서를 제출하기로 결정했다', date(2026, 10, 15))
    assert result.status == 'unspecified' and result.expression is None
    assert result.due_date is None and result.reason is None and not result.human_review_required
