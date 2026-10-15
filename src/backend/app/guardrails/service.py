"""Tenant policy and durable, content-free runtime audit; no process-global state."""
from uuid import uuid4
from app.guardrails.engine import GuardrailPolicy,evaluate_input,evaluate_output,text_hash
from app.guardrails.repository import GuardrailRepository
from app.errors import AppError

class GuardrailService:
    def __init__(self,pool=None,*,repository=None):
        self.repository=repository if repository is not None else GuardrailRepository(pool)

    async def snapshot(self,ctx):
        data=await self.repository.runtime_policy(ctx)
        revision=data.get('revision')
        action=data.get('output_pii_action','mask')
        if type(revision) is not int or revision<1 or action not in ('mask','block'):
            raise AppError('STORAGE_UNAVAILABLE',503)
        return GuardrailPolicy(revision=revision,output_pii_action=action)

    async def inspect(self,ctx,text,*,direction,run_id=None,trace_id=None,previous=None):
        current=await self.snapshot(ctx)
        action='block' if current.output_pii_action=='block' or (previous is not None and previous.output_pii_action=='block') else 'mask'
        policy=GuardrailPolicy(revision=current.revision,output_pii_action=action)
        result=(evaluate_input if direction=='input' else evaluate_output)(text,policy=policy)
        if result.rule_ids:
            await self.repository.record_violation(ctx,trace_id=trace_id or uuid4(),
                user_id=ctx.user_id,run_id=run_id,direction=direction,
                rule_ids=list(result.rule_ids),content_hash=text_hash(text),policy_revision=current.revision)
        return result
