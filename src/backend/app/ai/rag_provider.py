"""Structured fact IDs only; general provider keeps its original stream contract."""
import asyncio,json
from app.ai.providers import MockProvider,OpenAIProvider
from app.ai.types import ProviderOutcome,UsageReceipt
from app.ai.token_limits import general_token_count

RAG_FORMAT={'type':'json_schema','json_schema':{'name':'rag_fact_selection','strict':True,'schema':{'type':'object','properties':{'answer_kind':{'type':'string','enum':['answer','insufficient_evidence']},'selected_fact_ids':{'type':'array','items':{'type':'string'}}},'required':['answer_kind','selected_fact_ids'],'additionalProperties':False}}}
class RagOpenAIProvider(OpenAIProvider):
    response_format=RAG_FORMAT
class RagMockProvider:
    async def generate(self,claim,messages,on_delta):
        data=json.loads(messages[-1]['content']);result={'answer_kind':'answer','selected_fact_ids':[x['fact_id'] for x in data['facts']]}
        body=json.dumps(result,separators=(',',':'));await on_delta(body)
        input_tokens=general_token_count(messages);output_tokens=25
        return ProviderOutcome(body,UsageReceipt(input_tokens,output_tokens,input_tokens+output_tokens,'gpt-4o-mini','default','mock-'+str(claim.call_id)),'observed',None)
    async def close(self):pass
