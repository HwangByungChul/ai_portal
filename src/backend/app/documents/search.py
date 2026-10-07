"""Exact vector/graph retrieval inside current published-version RLS scope."""
import json,unicodedata
from uuid import UUID
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.policies.document_ingest import require_document_policy
from app.documents.policy import resolve_readable_version,DocumentUnavailable
from app.documents.storage import StoredSource
from app.documents.plan import build_document_plan
from app.documents.worker import local_id
from app.ai.token_limits import general_token_count,encoding
from common_core.ai_pipeline.document.schemas import DocumentMetadata
from common_core.ai_pipeline.graphrag.extractor import PROCESS_ALIASES
from common_core.ai_pipeline.graphrag.answer import FactPacket,select_relevant

SOURCE_KEYS=('source_tenant_id','document_id','version_id','index_id')
def source_binding(row):return {k:str(row[k]) for k in SOURCE_KEYS}

class SearchRepository:
    def __init__(self,documents):self.documents=documents;self.pool=documents.pool
    async def allowed(self,ctx,refs,mode,conn=None):
        from contextlib import AsyncExitStack
        async with AsyncExitStack() as stack:
            if conn is None:conn=await stack.enter_async_context(tenant_transaction(self.pool,ctx))
            if refs:
                if len(refs)>5 or len({(str(x['document_id']),str(x['version_id'])) for x in refs})!=len(refs):raise AppError('REQUEST_INVALID',422)
                rows=[]
                for ref in refs:
                    row=await (await conn.execute("SELECT v.tenant_id AS source_tenant_id,v.document_id,v.version_id,i.index_id FROM rag.document_versions v JOIN rag.index_builds i ON (i.tenant_id,i.document_id,i.version_id)=(v.tenant_id,v.document_id,v.version_id) WHERE v.document_id=%s AND v.version_id=%s AND i.execution_mode=%s AND security.document_can_read(v.tenant_id,v.document_id,v.version_id,i.index_id)",(UUID(str(ref['document_id'])),UUID(str(ref['version_id'])),mode))).fetchone()
                    if row is None:raise AppError('DOCUMENT_UNAVAILABLE',404)
                    rows.append(row)
            else:
                rows=await (await conn.execute("SELECT DISTINCT ON(v.tenant_id,v.document_id) v.tenant_id AS source_tenant_id,v.document_id,v.version_id,i.index_id FROM rag.document_versions v JOIN rag.index_builds i ON (i.tenant_id,i.document_id,i.version_id)=(v.tenant_id,v.document_id,v.version_id) WHERE security.document_can_read(v.tenant_id,v.document_id,v.version_id,i.index_id) AND i.execution_mode=%s ORDER BY v.tenant_id,v.document_id,v.version_no DESC LIMIT 129",(mode,))).fetchall()
                if len(rows)>128:raise AppError('SEARCH_LIMIT_EXCEEDED',409)
            return tuple(source_binding(x) for x in rows)
    async def guard(self,ctx,mode,sources):
        return await self.documents.rpc(ctx,'rag_sources_guard',(ctx.session_id,ctx.tenant_id,mode,Jsonb(list(sources))))
    async def packets(self,ctx,prompt,mode,sources,vector):
        question=unicodedata.normalize('NFC',prompt)
        for alias,value in sorted(PROCESS_ALIASES.items(),key=lambda x:-len(x[0])):question=question.replace(alias,value)
        indexes=[UUID(x['index_id']) for x in sources]
        scope=Jsonb(list(sources))
        def allowed(alias):return 'EXISTS(SELECT 1 FROM jsonb_to_recordset(%s::jsonb) AS scope(source_tenant_id uuid,document_id uuid,version_id uuid,index_id uuid) WHERE (scope.source_tenant_id,scope.document_id,scope.version_id,scope.index_id)=('+alias+'.tenant_id,'+alias+'.document_id,'+alias+'.version_id,'+alias+'.index_id))'
        async with tenant_transaction(self.pool,ctx) as conn:
            await conn.execute('SELECT security.rag_sources_guard(%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,mode,Jsonb(list(sources))))
            chunks=await (await conn.execute('SELECT tenant_id,index_id,chunk_id FROM rag.chunks c WHERE '+allowed('c')+' ORDER BY embedding OPERATOR(rag.<=>) %s::rag.vector,index_id,ordinal LIMIT 6',(scope,'['+','.join(str(x) for x in vector)+']'))).fetchall()
            # Seed only question-matched authorized entities; vector rank is not a sufficiency claim.
            personal_reference=len(sources)==1 and '내' in question and '개인' in question and '리허설' in question
            seeds=await (await conn.execute("SELECT tenant_id,index_id,entity_id,semantic_key FROM rag.entities e WHERE "+allowed('e')+" AND (strpos(%s,label)>0 OR (%s AND entity_type='PERSON')) ORDER BY char_length(label) DESC,entity_id LIMIT 4",(scope,question,personal_reference))).fetchall()
            keys={x['semantic_key'] for x in seeds};relations={};limited=False
            for hop in range(2):
                if not keys:break
                rows=await (await conn.execute('''SELECT r.*,a.label AS subject,b.label AS value,a.semantic_key AS left_key,b.semantic_key AS right_key FROM rag.relations r JOIN rag.entities a ON (a.tenant_id,a.index_id,a.entity_id)=(r.tenant_id,r.index_id,r.from_entity_id) JOIN rag.entities b ON (b.tenant_id,b.index_id,b.entity_id)=(r.tenant_id,r.index_id,r.to_entity_id) WHERE '''+allowed('r')+''' AND (a.semantic_key=ANY(%s) OR b.semantic_key=ANY(%s)) ORDER BY r.tenant_id,r.index_id,r.relation_id LIMIT 33''',(scope,list(keys),list(keys)))).fetchall()
                for row in rows:relations[(row['tenant_id'],row['index_id'],row['relation_id'])]=row
                if len(rows)>32 or len(relations)>32:limited=True;break
                keys|={x[k] for x in rows for k in ('left_key','right_key')}
            packets=[];plans={};packet_ranks={}
            chunk_ranks={(x['tenant_id'],x['index_id'],x['chunk_id']):n for n,x in enumerate(chunks)}
            for row in list(relations.values())[:32]:
                rid=row['relation_id'];idx=row['index_id'];plan_key=(row['tenant_id'],idx);proofs=await (await conn.execute('''SELECT e.* FROM rag.relation_evidence re JOIN rag.evidence e ON (e.tenant_id,e.index_id,e.evidence_id)=(re.tenant_id,re.index_id,re.evidence_id) WHERE re.tenant_id=%s AND re.index_id=%s AND re.relation_id=%s ORDER BY e.evidence_id LIMIT 21''',(row['tenant_id'],idx,rid))).fetchall()
                if not proofs or len(proofs)>20:raise AppError('ANSWER_EVIDENCE_INVALID',409)
                if plan_key not in plans:
                    v=await (await conn.execute('SELECT tenant_id,document_id,version_id,title,source_object_key,source_sha256,byte_length,character_length,media_type,source_mapping FROM rag.document_versions WHERE tenant_id=%s AND version_id=%s',(row['tenant_id'],row['version_id']))).fetchone()
                    if v is None:raise AppError('DOCUMENT_UNAVAILABLE',404)
                    raw=self.documents.storage.read(StoredSource(v['source_object_key'],bytes(v['source_sha256']),v['byte_length'],v['character_length'],v['title'],v['media_type'],v['source_mapping']))
                    require_document_policy(v["title"]+"\n"+raw.decode("utf-8"))
                    plan=build_document_plan(raw,v['title'],v['media_type'],DocumentMetadata(row['tenant_id'],row['document_id'],row['version_id'],idx,bytes(v['source_sha256']),mode))
                    i=await (await conn.execute('SELECT source_fingerprint,pipeline_revision FROM rag.index_builds WHERE tenant_id=%s AND index_id=%s',(row['tenant_id'],idx))).fetchone()
                    if i is None or bytes(i['source_fingerprint']).hex()!=plan.source_fingerprint:raise AppError('ANSWER_EVIDENCE_INVALID',409)
                    plans[plan_key]=plan
                plan=plans[plan_key];expected=next((x for x in plan.graph.relations if local_id(idx,'relation',x.ordinal)==rid),None)
                if expected is None or row['relation_type']!=expected.predicate or row['properties']!=dict(expected.properties) or row['from_entity_id']!=local_id(idx,'entity',expected.from_ordinal) or row['to_entity_id']!=local_id(idx,'entity',expected.to_ordinal) or {e['evidence_id'] for e in proofs}!={local_id(idx,'evidence',x) for x in expected.evidence_ordinals}:raise AppError('ANSWER_EVIDENCE_INVALID',409)
                for proof in proofs:
                    original=next(x for x in plan.evidence if local_id(idx,'evidence',x.ordinal)==proof['evidence_id'])
                    if proof['exact_quote']!=original.exact_quote or bytes(proof['source_sha256'])!=plan.metadata.source_sha256 or any(proof[k]!=getattr(original,k) for k in ('start_offset','end_offset','line_start','line_end')):raise AppError('ANSWER_EVIDENCE_INVALID',409)
                    evidence={**source_binding({**row,'source_tenant_id':row['tenant_id']}),'evidence_id':str(proof['evidence_id']),'relation_id':str(rid),'source_sha256':bytes(proof['source_sha256']).hex(),'quote':proof['exact_quote'],'location':{k:proof[k] for k in ('start_offset','end_offset','line_start','line_end')}}
                    packet_ranks['F'+str(len(packets))]=chunk_ranks.get((row['tenant_id'],idx,proof['chunk_id']),len(chunks))
                    packets.append(FactPacket('F'+str(len(packets)),expected.predicate,plan.graph.entities[expected.from_ordinal].canonical_label,plan.graph.entities[expected.to_ordinal].canonical_label,expected.properties,evidence,str(row['tenant_id'])))
        packets.sort(key=lambda packet:packet_ranks[packet.fact_id])
        relevant,required=select_relevant(question,packets,limited)
        # Whole packets only; never clip a proof and present a partial claim as complete.
        context=json.dumps([p.public() for p in relevant],ensure_ascii=False,separators=(',',':'))
        if len(encoding('o200k_base').encode(context,disallowed_special=()))>2000:return (),required
        return relevant,required
