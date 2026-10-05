"""Single-process asynchronous jobs, fenced by persistent epoch and private worker claim."""
import asyncio
from uuid import UUID
from app.ai.repository import ExecutionError
from app.ai.gateway import AiGateway

class ExecutionManager:
    def __init__(self,repository,provider,mode,hub):
        self.repository=repository;self.gateway=AiGateway(repository,provider);self.mode=mode;self.hub=hub
        self.tasks={};self.closed=False;self.recovery=None;self.leader=None

    async def start(self):
        self.leader=await self.repository.web_pool.getconn()
        try:
            row=await (await self.leader.execute('SELECT pg_try_advisory_lock(202610,4) AS ok')).fetchone()
            if not row['ok']:raise ExecutionError('EXECUTION_BLOCKED')
            async with self.leader.transaction():
                self.recovery=(await (await self.leader.execute('SELECT security.execution_recover(%s) AS data',(self.mode,))).fetchone())['data']
        except BaseException:
            await self.leader.close();await self.repository.web_pool.putconn(self.leader);self.leader=None;raise

    def notify(self,ctx,run_id):
        key=(ctx.tenant_id,UUID(str(run_id)))
        if self.closed or self.gateway.stop_latch or key in self.tasks:return
        task=asyncio.create_task(self._run(ctx,key[1]));self.tasks[key]=task
        task.add_done_callback(lambda finished:self.tasks.pop(key,None))

    def cancel(self,ctx,run_id):
        task=self.tasks.get((ctx.tenant_id,run_id))
        if task is not None:task.cancel()

    async def _heartbeat(self,ticket,work):
        while not work.done():
            await asyncio.sleep(20)
            try:ok=await self.repository.heartbeat(ticket)
            except ExecutionError:ok=False;self.gateway.stop_latch=True
            if not ok:work.cancel();return

    async def _run(self,ctx,run_id):
        ticket=None;work=None;heartbeat=None
        try:
            ticket=await self.repository.claim(ctx,run_id,self.mode)
            if ticket is None:return
            self.hub.begin(ticket.run)
            async def delta(text):
                if not await self.repository.heartbeat(ticket):raise ExecutionError('EXECUTION_BLOCKED')
                self.hub.append(ticket.run,text)
            work=asyncio.create_task(self.gateway.execute(ticket,delta));heartbeat=asyncio.create_task(self._heartbeat(ticket,work))
            try:
                outcome=await asyncio.wait_for(asyncio.shield(work),timeout=180)
            except (asyncio.CancelledError,TimeoutError):
                work.cancel()
                outcome=await work
                outcome=type(outcome)(None,outcome.receipt,outcome.end_status,'EXECUTION_INTERRUPTED' if self.closed else 'RUN_TIMEOUT')
            if outcome.body is not None and outcome.safe_error_code is None:
                saved=False;save_error='EXECUTION_BLOCKED'
                for attempt in range(2):
                    try:saved=await self.repository.finish(ticket,outcome.body);break
                    except ExecutionError as error:
                        save_error='RESULT_SAVE_FAILED' if error.code=='LEDGER_UNAVAILABLE' else 'EXECUTION_BLOCKED'
                        if error.code!='LEDGER_UNAVAILABLE':break
                        if attempt==1:break
                        await asyncio.sleep(0)
                if not saved:await self.repository.fail(ticket,save_error)
            else:await self.repository.fail(ticket,outcome.safe_error_code or 'EXECUTION_BLOCKED')
        except (ExecutionError,asyncio.CancelledError) as error:
            if ticket is not None:
                try:await self.repository.fail(ticket,'EXECUTION_INTERRUPTED')
                except ExecutionError:self.gateway.stop_latch=True
            else:
                try:await self.repository.reject(ctx,run_id,self.mode,getattr(error,'code','EXECUTION_BLOCKED'))
                except ExecutionError:self.gateway.stop_latch=True
        except Exception:
            self.gateway.stop_latch=True
            if ticket is not None:
                try:await self.repository.fail(ticket,'EXECUTION_INTERRUPTED')
                except ExecutionError:pass
        finally:
            if heartbeat is not None:heartbeat.cancel();await asyncio.gather(heartbeat,return_exceptions=True)
            if work is not None and not work.done():work.cancel();await asyncio.gather(work,return_exceptions=True)
            if ticket is not None:self.hub.clear(ticket.run)

    async def close(self):
        self.closed=True
        for task in list(self.tasks.values()):task.cancel()
        await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)
        self.hub.close();await self.gateway.provider.close()
        if self.leader is not None:
            try:await self.leader.execute('SELECT pg_advisory_unlock(202610,4)')
            finally:await self.repository.web_pool.putconn(self.leader);self.leader=None
