import json
from app.ai.providers import OpenAIProvider
from app.ai.types import ProviderOutcome,UsageReceipt
from app.ai.token_limits import general_token_count,encoding
SUMMARY_FORMAT={'type':'json_schema','json_schema':{'name':'summary_selection','strict':True,'schema':{'type':'object','properties':{'selected_ids':{'type':'array','items':{'type':'string'},'maxItems':5}},'required':['selected_ids'],'additionalProperties':False}}}
class SummaryOpenAIProvider(OpenAIProvider):
    response_format=SUMMARY_FORMAT
    max_completion_tokens=512
class SummaryMockProvider:
    async def generate(self,claim,messages,on_delta):
        data=json.loads(messages[-1]['content'])
        body=json.dumps({'selected_ids':[x['id'] for x in data['candidates'][:data['bullet_count']]]},separators=(',',':'))
        await on_delta(body)
        inp=general_token_count(messages);out=len(encoding('o200k_base').encode(body,disallowed_special=()))
        return ProviderOutcome(body,UsageReceipt(inp,out,inp+out,'gpt-4o-mini','default','mock-'+str(claim.call_id)),'observed',None)
    async def close(self):pass
