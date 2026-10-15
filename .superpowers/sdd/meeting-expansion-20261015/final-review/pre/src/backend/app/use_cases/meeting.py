"""Server-owned contract for meeting drafts; execution still requires Workflow approval."""
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field,StrictStr,field_validator
from app.use_cases.catalog import get_use_case

Text=Annotated[StrictStr,Field(min_length=1,max_length=4000)]

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')

class MeetingInput(StrictModel):
    memo:Text
    meeting_date:date|None=None

    @field_validator('memo')
    @classmethod
    def valid_memo(cls,value):
        if not value.strip() or '\x00' in value:raise ValueError('MEETING_INPUT_INVALID')
        value.encode('utf-8')
        return value

class EvidenceItem(StrictModel):
    text:Text
    quote:Text

class ActionItem(EvidenceItem):
    assignee:Annotated[StrictStr,Field(min_length=1,max_length=100)]|None=None
    due_date:date|None=None

class MeetingResult(StrictModel):
    decisions:list[EvidenceItem]=Field(max_length=50)
    unresolved:list[EvidenceItem]=Field(max_length=50)
    actions:list[ActionItem]=Field(max_length=50)

    def check_evidence(self,source:MeetingInput):
        for item in [*self.decisions,*self.unresolved,*self.actions]:
            if not item.quote.strip() or item.quote not in source.memo:
                raise ValueError('MEETING_EVIDENCE_INVALID')
            if isinstance(item,ActionItem):
                if item.assignee is not None and (not item.assignee.strip() or item.assignee not in item.quote):
                    raise ValueError('MEETING_ASSIGNEE_UNCONFIRMED')
                # Relative dates require a future explicit resolver; never infer them here.
                if item.due_date is not None and item.due_date.isoformat() not in item.quote:
                    raise ValueError('MEETING_DEADLINE_UNCONFIRMED')
        return self


def meeting_contract():
    manifest=get_use_case('AGENT_03')
    body={'use_case_id':manifest.use_case_id,'contract_revision':1,
          'role_scope':manifest.role_scope,'required_tools':manifest.required_tools,
          'auto_decision_prohibited':manifest.auto_decision_prohibited,
          'system_prompt':manifest.system_prompt,'input_schema':MeetingInput.model_json_schema(),
          'output_schema':MeetingResult.model_json_schema(),
          'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    encoded=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return body|{'manifest_digest':hashlib.sha256(encoded).hexdigest()}
