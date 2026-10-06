"""One durable scoped Job; no evaluator input. Payload INSERT/checkpoint share a transaction."""
from uuid import UUID,uuid5
import asyncio
import secrets
from psycopg.types.json import Jsonb
from app.documents.storage import StoredSource
from app.documents.plan import build_document_plan
from common_core.ai_pipeline.document.schemas import DocumentMetadata
from app.errors import AppError


def local_id(index,kind,ordinal):return uuid5(index,f'{kind}:{ordinal}')


class DocumentWorker:
    def __init__(self,repository,gateway):
        if repository.mode!=gateway.provider.mode:raise ValueError('INDEX_MODE_MISMATCH')
        self.repository=repository;self.gateway=gateway

    async def _control(self,ctx,job_id,action,epoch=None,claim=None,data=None):
        # Web APIs keep session checks. Only the dedicated index capability can
        # control an admitted Job after HTTP logout, using its current principal.
        if action=='claim':data={**(data or {}),'mode':self.repository.mode}
        return await self.gateway.rpc('document_background_control',
            (ctx.user_id,ctx.tenant_id,job_id,action,epoch,claim,Jsonb(data or {})))

    async def _guard(self,conn,ticket):
        await conn.execute('SELECT security.document_worker_guard(%s,%s,%s,%s)',(ticket['tenant_id'],ticket['job_id'],ticket['epoch'],ticket['claim']))

    async def run(self,ctx,job_id):
        claim=secrets.token_bytes(32);job=await self._control(ctx,job_id,'claim',claim=claim)
        if job is None:return
        ticket={'tenant_id':ctx.tenant_id,'job_id':job_id,'epoch':job['epoch'],'claim':claim}
        heartbeat=asyncio.create_task(self._heartbeat(ctx,job_id,ticket))
        try:
            async with asyncio.timeout(300):
                recovery=await self.gateway.rpc('document_embedding_recover',(ctx.tenant_id,job_id,ticket['epoch'],claim))
                if recovery['unknown_batches']:raise AppError('INDEX_NEEDS_REVIEW',409)
                async with self.gateway.index_pool.connection() as conn:
                    async with conn.transaction():
                        await self._guard(conn,ticket)
                        row=await (await conn.execute('SELECT * FROM rag.document_versions WHERE tenant_id=%s AND document_id=%s AND version_id=%s',(ctx.tenant_id,UUID(job['document_id']),UUID(job['version_id'])))).fetchone()
                        if row is None:raise AppError('DOCUMENT_UNAVAILABLE',404)
                        content=self.repository.storage.read(StoredSource(row['source_object_key'],bytes(row['source_sha256']),row['byte_length'],row['character_length'],row['title'],row['media_type']))
                meta=DocumentMetadata(ctx.tenant_id,UUID(job['document_id']),UUID(job['version_id']),UUID(job['index_id']),bytes(row['source_sha256']),job['mode'])
                plan=build_document_plan(content,row['title'],row['media_type'],meta)
                if plan.source_fingerprint!=job['source_fingerprint']:raise AppError('SOURCE_INVALID',422)
                await self._control(ctx,job_id,'plan',ticket['epoch'],claim,{'batches':len(plan.batches),'fingerprint':plan.source_fingerprint,'coverage':{'status':plan.graph.coverage,'reasons':[reason for _,reason in plan.graph.reasons]}})
                for batch in plan.batches:
                    async with self.gateway.index_pool.connection() as conn:
                        async with conn.transaction():
                            await self._guard(conn,ticket)
                            index=await (await conn.execute('SELECT checkpoint_summary FROM rag.index_builds WHERE tenant_id=%s AND index_id=%s',(ctx.tenant_id,meta.index_id))).fetchone()
                            checkpoint=index['checkpoint_summary'].get(str(batch.ordinal))
                            if checkpoint:
                                if checkpoint['fingerprint']!=batch.fingerprint:raise AppError('INDEX_NEEDS_REVIEW',409)
                                continue
                    call,vectors=await self.gateway.batch(ticket,batch,[plan.chunks[i].text for i in batch.chunk_ordinals])
                    await self._save_batch(ticket,plan,batch,call,vectors)
                async with self.gateway.index_pool.connection() as conn:
                    async with conn.transaction():
                        await self._guard(conn,ticket)
                        await self._graph(conn,meta,plan)
                        counts={'chunks':len(plan.chunks),'entities':len(plan.graph.entities),'relations':len(plan.graph.relations),'evidence':len(plan.evidence)}
                        await conn.execute('SELECT security.document_publish(%s,%s,%s,%s,%s)',(ctx.tenant_id,job_id,ticket['epoch'],claim,Jsonb(counts)))
        except BaseException as error:
            code=error.code if isinstance(error,AppError) else 'INDEX_INTERRUPTED'
            try:await self._control(ctx,job_id,'review',ticket['epoch'],claim,{'code':code})
            except BaseException:pass
            raise
        finally:
            heartbeat.cancel()
            try:await heartbeat
            except asyncio.CancelledError:pass

    async def _save_batch(self,ticket,plan,batch,call,vectors):
        meta=plan.metadata;job_id=ticket['job_id'];claim=ticket['claim']
        async with self.gateway.index_pool.connection() as conn:
            async with conn.transaction():
                await self._guard(conn,ticket)
                for ordinal,vector in zip(batch.chunk_ordinals,vectors):
                    c=plan.chunks[ordinal]
                    await conn.execute('''INSERT INTO rag.chunks(tenant_id,document_id,version_id,index_id,chunk_id,ordinal,text,location,embedding,source_sha256,batch_ordinal,call_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::rag.vector,%s,%s,%s)''',(meta.tenant_id,meta.document_id,meta.version_id,meta.index_id,local_id(meta.index_id,'chunk',ordinal),ordinal,c.text,Jsonb({'start':c.start,'end':c.end,'tokens':c.token_count}),'['+','.join(str(x) for x in vector)+']',meta.source_sha256,batch.ordinal,call))
                await conn.execute('SELECT security.document_checkpoint(%s,%s,%s,%s,%s,%s,%s,%s)',(meta.tenant_id,job_id,ticket['epoch'],claim,batch.ordinal,batch.fingerprint,len(vectors),call))

    async def _heartbeat(self,ctx,job,ticket):
        while True:
            await asyncio.sleep(20)
            await self._control(ctx,job,'heartbeat',ticket['epoch'],ticket['claim'])

    async def _graph(self,conn,m,p):
        scope=(m.tenant_id,m.document_id,m.version_id,m.index_id)
        for e in p.graph.entities:
            await conn.execute('INSERT INTO rag.entities(tenant_id,document_id,version_id,index_id,entity_id,semantic_key,entity_type,label,properties) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(*scope,local_id(m.index_id,'entity',e.ordinal),e.semantic_key,e.entity_type,e.canonical_label,Jsonb({})))
        for e in p.evidence:
            await conn.execute('INSERT INTO rag.evidence(tenant_id,document_id,version_id,index_id,evidence_id,chunk_id,start_offset,end_offset,line_start,line_end,exact_quote,source_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(*scope,local_id(m.index_id,'evidence',e.ordinal),local_id(m.index_id,'chunk',e.chunk_ordinal),e.start_offset,e.end_offset,e.line_start,e.line_end,e.exact_quote,m.source_sha256))
        for rel in p.graph.relations:
            rid=local_id(m.index_id,'relation',rel.ordinal)
            await conn.execute('INSERT INTO rag.relations(tenant_id,document_id,version_id,index_id,relation_id,from_entity_id,to_entity_id,relation_type,properties) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(*scope,rid,local_id(m.index_id,'entity',rel.from_ordinal),local_id(m.index_id,'entity',rel.to_ordinal),rel.predicate,Jsonb(dict(rel.properties))))
            for ordinal in rel.evidence_ordinals:
                await conn.execute('INSERT INTO rag.relation_evidence(tenant_id,index_id,relation_id,evidence_id) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(m.tenant_id,m.index_id,rid,local_id(m.index_id,'evidence',ordinal)))
