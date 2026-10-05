"""Bounded local Job scheduler; durable DB state controls restart and exact leases."""
import asyncio
from uuid import UUID
from app.types import AuthContext

class DocumentManager:
    def __init__(self,worker,mode):
        self.worker=worker;self.mode=mode;self.tasks={};self.contexts={};self.semaphore=asyncio.Semaphore(2);self.poller=None;self.closing=False
    async def start(self):
        await self.recover();self.poller=asyncio.create_task(self._poll())
    async def recover(self):
        repo=self.worker.repository
        async with repo.pool.connection() as c:
            async with c.transaction():rows=(await (await c.execute('SELECT security.document_pending(%s) AS data',(self.mode,))).fetchone())['data']
        for row in rows:
            ctx=AuthContext(UUID(row['origin_session_id']),UUID(row['initiator_user_id']),UUID(row['tenant_id']),'USER','')
            self.notify(ctx,UUID(row['job_id']),row['job_kind'],UUID(row['document_id']))
    def notify(self,ctx,job,kind='internal_index',document=None):
        self.contexts[ctx.tenant_id]=ctx
        key=(ctx.tenant_id,job)
        if self.closing or key in self.tasks or len(self.tasks)>=100:return
        task=asyncio.create_task(self._run(ctx,job,kind,document));self.tasks[key]=task
        task.add_done_callback(lambda done:self.tasks.pop(key,None))
    async def _run(self,ctx,job,kind,document):
        try:
            async with self.semaphore:
                if kind=='internal_cleanup':await self.cleanup(ctx,document)
                else:await self.worker.run(ctx,job)
        except asyncio.CancelledError:raise
        except Exception:pass # Safe state is durable; no payload/error logging or remote retry.
    async def cleanup(self,ctx,document):
        repo=self.worker.repository
        info=await repo.rpc(ctx,'document_cleanup',(ctx.session_id,ctx.tenant_id,document,'purge'))
        for version in info['version_ids']:
            repo.storage.remove(f'tenants/{ctx.tenant_id}/documents/{document}/{UUID(version)}/source')
        await repo.rpc(ctx,'document_cleanup',(ctx.session_id,ctx.tenant_id,document,'finish'))
    async def _poll(self):
        while True:
            await asyncio.sleep(10)
            try:
                await self.recover()
                for ctx in list(self.contexts.values()):
                    try:await self.worker.repository.cleanup_orphans(ctx)
                    except Exception:pass
            except Exception:pass
    async def close(self):
        self.closing=True
        if self.poller:self.poller.cancel()
        pending=[*self.tasks.values(),*([self.poller] if self.poller else [])]
        for t in pending:t.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
        await self.worker.gateway.provider.close()
