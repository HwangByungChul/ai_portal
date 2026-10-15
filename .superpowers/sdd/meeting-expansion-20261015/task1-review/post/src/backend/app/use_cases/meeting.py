"""Server-owned contract for meeting drafts; execution still requires Workflow approval."""
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Mapping, Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,StrictStr,field_validator,model_validator
from app.use_cases.catalog import get_use_case
from app.use_cases.meeting_dates import resolve_deadline

Text=Annotated[StrictStr,Field(min_length=1,max_length=4000)]

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')

class DocumentRef(StrictModel):
    document_id: UUID
    version_id: UUID

class MeetingInput(StrictModel):
    memo:Annotated[StrictStr,Field(max_length=4000)]=''
    meeting_date:date|None=None
    document_refs:list[DocumentRef]=Field(default_factory=list,max_length=3)

    @field_validator('meeting_date',mode='before')
    @classmethod
    def valid_date(cls,value):
        if value is not None and type(value) is not date:
            if not isinstance(value,str) or len(value)!=10 or date.fromisoformat(value).isoformat()!=value:
                raise ValueError('MEETING_DATE_INVALID')
        return value

    @field_validator('memo')
    @classmethod
    def valid_memo(cls,value):
        if '\x00' in value:raise ValueError('MEETING_INPUT_INVALID')
        value.encode('utf-8')
        return value

    @model_validator(mode='after')
    def valid_sources(self):
        if not self.memo.strip() and not self.document_refs:raise ValueError('MEETING_INPUT_INVALID')
        if len({ref.document_id for ref in self.document_refs})!=len(self.document_refs) or len({ref.version_id for ref in self.document_refs})!=len(self.document_refs):
            raise ValueError('MEETING_DOCUMENT_DUPLICATE')
        return self

class EvidenceItem(StrictModel):
    text:Text
    quote:Text
    source_ref:Annotated[StrictStr,Field(min_length=1,max_length=100)]='memo'

class ActionItem(EvidenceItem):
    assignee:Annotated[StrictStr,Field(min_length=1,max_length=100)]|None=None
    due_date:date|None=None
    due_expression:Text|None=None
    deadline_status:Literal['unspecified','resolved','unresolved']='unspecified'
    deadline_reason:StrictStr|None=None

class MeetingResult(StrictModel):
    decisions:list[EvidenceItem]=Field(max_length=50)
    unresolved:list[EvidenceItem]=Field(max_length=50)
    actions:list[ActionItem]=Field(max_length=50)

    def check_evidence(self,source:MeetingInput,document_sources:Mapping[str,str]|None=None):
        allowed={f'document:{ref.version_id}' for ref in source.document_refs}
        sources={'memo':source.memo}
        sources.update({key:value for key,value in (document_sources or {}).items() if key in allowed and isinstance(value,str)})
        for item in [*self.decisions,*self.unresolved,*self.actions]:
            if not item.quote.strip() or item.source_ref not in sources or item.quote not in sources[item.source_ref]:
                raise ValueError('MEETING_EVIDENCE_INVALID')
            if isinstance(item,ActionItem):
                if item.assignee is not None and (not item.assignee.strip() or item.assignee not in item.quote):
                    raise ValueError('MEETING_ASSIGNEE_UNCONFIRMED')
                resolved=resolve_deadline(item.quote,source.meeting_date,item.due_expression)
                if item.due_date is not None and item.due_date != resolved.due_date:
                    raise ValueError('MEETING_DEADLINE_UNCONFIRMED')
                if resolved.reason == 'expression_not_in_quote':
                    raise ValueError('MEETING_DEADLINE_UNCONFIRMED')
                item.due_date=resolved.due_date
                item.due_expression=resolved.expression
                item.deadline_status=resolved.status
                item.deadline_reason=resolved.reason
        return self


def meeting_contract():
    manifest=get_use_case('AGENT_03')
    body={'use_case_id':manifest.use_case_id,'contract_revision':2,
          'role_scope':manifest.role_scope,'required_tools':manifest.required_tools,
          'auto_decision_prohibited':manifest.auto_decision_prohibited,
          'system_prompt':manifest.system_prompt,'input_schema':MeetingInput.model_json_schema(),
          'output_schema':MeetingResult.model_json_schema(),
          'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'rules_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('meeting_dates.py','meeting_quality.py')}}
    encoded=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return body|{'manifest_digest':hashlib.sha256(encoded).hexdigest()}
