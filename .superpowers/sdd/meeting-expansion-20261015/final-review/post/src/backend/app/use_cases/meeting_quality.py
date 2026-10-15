"""Structural evidence checks are not a semantic quality or approval decision."""
from dataclasses import dataclass
from typing import Mapping
from app.use_cases.meeting import MeetingInput, MeetingResult

HUMAN_RUBRIC = {
    'accuracy': 'Compare every decision and unresolved issue with the verified originals; identify unsupported interpretation.',
    'omission': 'Compare the complete originals with the draft for missing material decisions, issues and actions.',
    'owner': 'Confirm the quoted name is the actual action owner rather than a mentioned participant.',
    'deadline': 'Confirm the quoted expression is the action deadline rather than an unrelated date; review ambiguity and past dates.',
}

@dataclass(frozen=True)
class StructuralQuality:
    evidence_valid: bool
    item_count: int
    unresolved_deadlines: int
    past_deadlines: int
    error: str | None
    human_review_required: bool = True


def evaluate_structure(result: MeetingResult, source: MeetingInput, document_sources: Mapping[str,str] | None = None) -> StructuralQuality:
    # Evaluation must not mutate a persisted or caller-owned historical result.
    checked = result.model_copy(deep=True)
    count = len(checked.decisions)+len(checked.unresolved)+len(checked.actions)
    try: checked.check_evidence(source,document_sources)
    except ValueError as error: return StructuralQuality(False,count,0,0,str(error))
    return StructuralQuality(True,count,sum(a.deadline_status=='unresolved' for a in checked.actions),sum(a.deadline_reason=='past_due' for a in checked.actions),None)
