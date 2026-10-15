"""Server-owned exact meeting context. No model-supplied document metadata is trusted."""
import json
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from app.db import tenant_transaction
from app.errors import AppError
from app.documents.storage import SourceStorageError
from app.execution.summary_repository import stored
from app.use_cases.meeting import MeetingInput, MeetingResult
from app.use_cases.meeting_quality import evaluate_structure, HUMAN_RUBRIC


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class QualityReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    expected_review_revision: StrictInt = Field(ge=0, le=9223372036854775806)
    expected_run_revision: StrictInt = Field(ge=1, le=9223372036854775806)
    result_digest: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    accuracy: Literal['acceptable', 'needs_review', 'not_assessed']
    omission: Literal['acceptable', 'needs_review', 'not_assessed']
    owner: Literal['acceptable', 'needs_review', 'not_assessed']
    deadline: Literal['acceptable', 'needs_review', 'not_assessed']
    comment: StrictStr = Field(min_length=1, max_length=500)

    @field_validator('comment')
    @classmethod
    def comment_text(cls, value):
        value = value.strip()
        if not value or '\x00' in value:
            raise ValueError('invalid comment')
        value.encode('utf-8', errors='strict')
        return value


def compile_context(source, documents):
    # Legacy memo-only prompt remains byte-for-byte identical. Date authority is
    # persisted separately; a memo that looks like this header cannot replace it.
    if source.meeting_date is None and not documents:
        return source.memo
    value = canonical({'meeting_date': source.meeting_date.isoformat() if source.meeting_date else None,
                       'memo': source.memo,
                       'documents': [{'source_ref': x['source_ref'], 'text': x['text']} for x in documents]})
    if len(value) > 4000:
        raise AppError('MEETING_CONTEXT_TOO_LARGE', 422)
    return value


class MeetingRuntime:
    def __init__(self, repository, documents):
        self.repository = repository
        self.documents = documents

    async def resolve(self, ctx, source):
        docs = []
        if source.document_refs and self.documents is None:
            raise AppError('DOCUMENT_UNAVAILABLE', 404)
        for ref in source.document_refs:
            row = await self.repository.call(ctx, 'meeting_source',
                    (ctx.session_id, ctx.tenant_id, ref.document_id, ref.version_id))
            try:
                text = self.verify_source(row)
            except (SourceStorageError, ValueError, TypeError, KeyError):
                raise AppError('DOCUMENT_UNAVAILABLE', 404) from None
            docs.append({'source_tenant_id': row['tenant_id'], 'document_id': row['document_id'],
                         'version_id': row['version_id'], 'source_ref': f'document:{row["version_id"]}',
                         'source_sha256': row['source_sha256'], 'title': row['title'], 'version_no': row['version_no'],
                         'source_mapping': row['source_mapping'], 'text': text})
        compiled = compile_context(source, docs)
        return {'source': source.model_dump(mode='json'), 'documents': docs, 'compiled': compiled}

    def verify_source(self, row):
        from common_core.ai_pipeline.document.parser import parse_source
        from app.policies.document_ingest import require_document_policy
        material = row | {'source_sha256': bytes.fromhex(row['source_sha256'])}
        raw = self.documents.storage.read(stored(material))
        parsed = parse_source(raw, row['media_type'])
        mapping = {'revision': parsed.parser_revision, 'offset_unit': 'unicode_codepoint',
                   'mapping': parsed.mapping, 'lines': [{'start': x.start, 'end': x.end, 'kind': x.kind} for x in parsed.lines]}
        expected = {k:v for k,v in row['source_mapping'].items() if k != 'origin'}
        if parsed.parser_revision != row['parser_revision'] or canonical(mapping) != canonical(expected):
            raise SourceStorageError('SOURCE_INTEGRITY_FAILED')
        text = raw.decode('utf-8')
        require_document_policy(row['title'] + '\n' + text)
        return text

    async def context(self, ctx, parent):
        data = await self.repository.meeting_context(ctx, parent)
        if data is None:
            return None
        source = MeetingInput.model_validate(data['source'])
        # SQL rechecks current ACL/version/SHA. Filesystem and parser are rechecked
        # independently before any provider dispatch or content exposure.
        fresh = await self.resolve(ctx, source)
        if canonical(fresh) != canonical(data):
            raise AppError('DOCUMENT_UNAVAILABLE', 404)
        return data

    async def summary(self,ctx,parent):
        summary=await self.repository.call(ctx,'meeting_context_summary',(ctx.session_id,ctx.tenant_id,parent))
        if summary is None:return None
        for doc in summary['documents']:
            if doc['current_available']:
                try:
                    row=await self.repository.call(ctx,'meeting_source',(ctx.session_id,ctx.tenant_id,UUID(doc['document_id']),UUID(doc['version_id'])))
                    self.verify_source(row)
                    if row['source_sha256']!=doc['source_sha256']:raise SourceStorageError('SOURCE_INTEGRITY_FAILED')
                except (AppError,SourceStorageError,ValueError,TypeError,KeyError) as error:
                    if isinstance(error,AppError) and error.status not in (404,409,422):raise
                    doc['current_available']=False;doc['title']=None
            doc.pop('source_sha256',None)
        return summary

    @staticmethod
    def annotate(value,data):
        documents={x['source_ref']:x for x in data['documents']}
        for kind in ('decisions','unresolved','actions'):
            for item in value[kind]:
                doc=documents.get(item['source_ref'])
                if doc is None:continue
                starts=[];position=0
                while True:
                    start=doc['text'].find(item['quote'],position)
                    if start<0:break
                    starts.append(start);position=start+1
                spans=[(start,start+len(item['quote'])) for start in starts]
                display={'title':doc['title'],'version_id':doc['version_id'],'location_ambiguous':len(starts)>1}
                start,end=spans[0]
                origin=doc['source_mapping'].get('origin')
                if origin and origin['media_type']=='application/pdf':
                    pages=[x['page'] for x in origin['pages'] if any(x['start']<end and x['end']>start for start,end in spans)]
                    if pages:display.update(page_start=min(pages),page_end=max(pages))
                elif origin:
                    display['structure_locations']=[{k:v for k,v in x.items() if k not in ('start','end')} for x in origin['locations'] if x['kind']!='sheet' and any(x['start']<end and x['end']>start for start,end in spans)]
                item['source_display']=display
        return value

    async def guard_child(self, ctx, child):
        parent = await self.repository.call(ctx, 'meeting_parent_for_child', (ctx.session_id,ctx.tenant_id,child))
        if parent is not None:
            await self.context(ctx, UUID(str(parent)))

    @staticmethod
    def normalize(value, data):
        source = MeetingInput.model_validate(data['source'])
        documents = {x['source_ref']: x['text'] for x in data['documents']}
        try:
            result = MeetingResult.model_validate_json(value) if isinstance(value, str) else MeetingResult.model_validate(value)
            return result.check_evidence(source, documents).model_dump(mode='json')
        except ValueError:raise AppError('MEETING_EVIDENCE_INVALID',422) from None

    async def candidates(self, ctx, cursor=None, limit=20):
        if not 1 <= limit <= 20:
            raise AppError('REQUEST_INVALID', 422)
        # Fixed RPC returns only same-tenant currently readable exact versions;
        # source bodies/object keys never appear in the public response.
        data = await self.repository.call(ctx, 'meeting_document_candidates',
                                          (ctx.session_id, ctx.tenant_id, cursor, limit, self.repository.mode))
        for item in data['items']:
            item['ready'] = False
            item['unavailable_reason'] = 'source_unavailable'
            if self.documents is None:
                continue
            try:
                row = await self.repository.call(ctx, 'meeting_source',
                        (ctx.session_id,ctx.tenant_id,UUID(item['document_id']),UUID(item['version_id'])))
                self.verify_source(row)
                item['ready'] = True
                item['unavailable_reason'] = None
            except (SourceStorageError, AppError, ValueError, TypeError, KeyError) as error:
                if isinstance(error, AppError) and error.status not in (404, 409, 422):
                    raise
                # Authorized metadata is visible, but never invented as source.
        return data

    async def quality(self, ctx, parent, body=None):
        data = await self.context(ctx, parent)
        if data is None:
            raise AppError('NOT_FOUND', 404)
        row = await self.repository.runtime(ctx, 'read', parent)
        if row.get('state') != 'completed' or row.get('result_access') != 'final':
            raise AppError('REVISION_CONFLICT', 409)
        value = self.normalize(row['result'], data)
        action = 'review' if body is not None else 'read'
        result = await self.repository.call(ctx, 'meeting_quality_control',
                 (ctx.session_id, ctx.tenant_id, action, parent, self.repository.json(body.model_dump(mode='json') if body else {})))
        result.update(structural=evaluate_structure(MeetingResult.model_validate(value), MeetingInput.model_validate(data['source']),
                      {x['source_ref']: x['text'] for x in data['documents']}).__dict__,
                      rubric=HUMAN_RUBRIC, human_review_required=True)
        return result
