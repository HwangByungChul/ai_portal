"""Bounded local Job scheduler; durable DB state controls restart and exact leases."""
import asyncio
import secrets
from uuid import UUID
from app.types import AuthContext

class DocumentManager:
    def __init__(self,worker,mode):
        self.worker=worker;self.mode=mode;self.tasks={};self.contexts={};self.semaphore=asyncio.Semaphore(2);self.tenant_locks={};self.poller=None;self.closing=False
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
        # Cleanup purges all versions of a document; recovery and repeated
        # DELETE requests must share the same bounded queue entry.
        key=(ctx.tenant_id,document if kind=='internal_cleanup' else job)
        if self.closing or key in self.tasks or len(self.tasks)>=100:return
        task=asyncio.create_task(self._run(ctx,job,kind,document));self.tasks[key]=task
        task.add_done_callback(lambda done:self.tasks.pop(key,None))
    async def _run(self,ctx,job,kind,document):
        try:
            # Wait for the tenant before taking a project slot so one busy
            # tenant cannot occupy both slots or fail queued work at dispatch.
            lock=self.tenant_locks.setdefault(ctx.tenant_id,asyncio.Lock())
            async with lock:
                async with self.semaphore:
                    if kind=='internal_cleanup':await self.cleanup(ctx,document,None if job==document else job)
                    else:await self.worker.run(ctx,job)
        except asyncio.CancelledError:raise
        except Exception:pass # Safe state is durable; no payload/error logging or remote retry.
    async def cleanup(self,ctx,document,job=None):
        repo=self.worker.repository;gateway=self.worker.gateway;claim=secrets.token_bytes(32)
        async def control(action,epoch=None):
            return await gateway.rpc('document_cleanup_background',(ctx.user_id,ctx.tenant_id,document,job,action,self.mode,epoch,claim))
        owned=await control('claim')
        if not owned:return
        job=UUID(owned['job_id']);epoch=owned['epoch']
        try:
            info=await control('purge',epoch)
            for version in info['version_ids']:
                await control('heartbeat',epoch)
                repo.storage.remove(f'tenants/{ctx.tenant_id}/documents/{document}/{UUID(version)}/source')
            await control('finish',epoch)
        except BaseException:
            try:await control('release',epoch)
            except Exception:pass # Crash/expired lease remains durable for bounded recovery.
            raise
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
