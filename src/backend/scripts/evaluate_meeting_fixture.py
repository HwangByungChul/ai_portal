"""Free structural fixture runner. Never calls DB/providers or claims semantic quality."""
import json
from dataclasses import asdict
from pathlib import Path
import sys
from app.use_cases.meeting import MeetingInput,MeetingResult
from app.use_cases.meeting_quality import evaluate_structure


def evaluate(path):
    fixture=json.loads(Path(path).read_text())
    if fixture.get('provenance')!='synthetic_fixture_only':raise ValueError('SYNTHETIC_FIXTURE_REQUIRED')
    items=[]
    for case in fixture['cases']:
        metrics=evaluate_structure(MeetingResult.model_validate(case['result']),MeetingInput.model_validate(case['source']),case.get('documents',{}))
        items.append({'id':case['id'],'structural':asdict(metrics)})
    return {'revision':fixture['revision'],'provenance':fixture['provenance'],'provider_calls':0,'human_review_required':True,'items':items}


if __name__=='__main__':
    path=sys.argv[1] if len(sys.argv)==2 else Path(__file__).parents[1]/'tests/fixtures/meeting-runtime-evaluation-v2.json'
    print(json.dumps(evaluate(path),ensure_ascii=False,sort_keys=True))
