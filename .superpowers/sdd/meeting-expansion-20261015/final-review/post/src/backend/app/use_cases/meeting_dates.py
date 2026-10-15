"""Deterministic calendar deadlines, relative to the meeting (never wall clock).

Weeks begin Monday. 이번주 includes elapsed weekdays; 다음주 is the next
Monday-based week. No holiday, business-day or time-of-day inference is made.
"""
from dataclasses import dataclass
from datetime import date, timedelta
import re

EXPRESSION = re.compile(r'(?<![\d-])\d{4}-\d{2}-\d{2}(?!\d)|오늘|내일|모레|(?<![\d-])\d+\s*일\s*후|(?:이번|다음)\s*주\s*[월화수목금토일]요일')
AMBIGUOUS = re.compile(r'영업일|조속히|다음\s*주(?!\s*[월화수목금토일]요일)|이번\s*주(?!\s*[월화수목금토일]요일)')

# Recognize a bounded set of unsupported calendar periods without computing dates.
UNSUPPORTED = re.compile(r'월말|월초|분기말|연내|연말|연초|(?:다음|이번|이)\s*달|주말')

@dataclass(frozen=True)
class DeadlineResolution:
    due_date: date | None
    expression: str | None
    status: str
    reason: str | None
    human_review_required: bool


def resolve_deadline(quote: str, meeting_date: date | None, expression: str | None = None) -> DeadlineResolution:
    def unresolved(reason, expr=expression):
        return DeadlineResolution(None, expr, 'unresolved', reason, True)
    if expression is not None and (not expression.strip() or expression not in quote):
        return unresolved('expression_not_in_quote')
    matches = list(dict.fromkeys(EXPRESSION.findall(quote)))
    if AMBIGUOUS.search(quote):
        return unresolved('ambiguous_expression')
    unsupported = UNSUPPORTED.search(quote)
    if unsupported:
        return unresolved('unsupported_expression', expression or unsupported.group())
    if not matches:
        return unresolved('unsupported_expression') if expression else DeadlineResolution(None, None, 'unspecified', None, False)
    if expression is not None and expression not in matches:
        return unresolved('unsupported_expression')
    dates = []
    for value in matches:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            try: dates.append(date.fromisoformat(value))
            except ValueError: return unresolved('invalid_calendar_date', value)
            continue
        if meeting_date is None: return unresolved('meeting_date_required', value)
        try:
            if value in ('오늘', '내일', '모레'):
                resolved = meeting_date + timedelta(days=('오늘', '내일', '모레').index(value))
            elif '후' in value:
                # Bound before integer conversion; reject absurd or overflow-prone offsets.
                digits = re.match(r'\d+', value).group()
                if len(digits) > 4 or int(digits) > 3660: return unresolved('offset_out_of_bounds', value)
                resolved = meeting_date + timedelta(days=int(digits))
            else:
                weekday = '월화수목금토일'.index(value[-3])
                resolved = meeting_date + timedelta(days=-meeting_date.weekday()+weekday+(7 if value.startswith('다음') else 0))
            dates.append(resolved)
        except (OverflowError, ValueError): return unresolved('calendar_out_of_bounds', value)
    if len(set(dates)) != 1: return unresolved('conflicting_expressions')
    resolved = dates[0]
    past = meeting_date is not None and resolved < meeting_date
    return DeadlineResolution(resolved, expression or matches[0], 'resolved', 'past_due' if past else None, past)
