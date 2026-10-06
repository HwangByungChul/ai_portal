import asyncio,json
from uuid import uuid4
import httpx2
from app.ai.rag_provider import RagOpenAIProvider,RAG_FORMAT
from app.ai.types import DispatchClaim
from test_ai_provider import chunk

def test_rag_sdk_strict_schema_with_fake_transport_only():
    calls=[];deltas=[];body=json.dumps({'answer_kind':'answer','selected_fact_ids':['F0']})
    def transport(request):
        data=json.loads(request.content);calls.append(data);assert data['response_format']==RAG_FORMAT
        assert str(request.url)=='https://api.openai.com/v1/chat/completions'
        rows=[chunk(body),chunk(finish='stop'),chunk(usage={'prompt_tokens':120,'completion_tokens':30,'total_tokens':150})]
        return httpx2.Response(200,headers={'content-type':'text/event-stream','x-request-id':'synthetic-rag-request'},content=(''.join('data: '+json.dumps(x)+'\n\n' for x in rows)+'data: [DONE]\n\n').encode(),request=request)
    async def check():
        p=RagOpenAIProvider('synthetic-not-real-key',http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport),trust_env=False))
        async def delta(text):deltas.append(text)
        try:return await p.generate(DispatchClaim(uuid4(),1,'synthetic'),[{'role':'user','content':'합성 질문'}],delta)
        finally:await p.close()
    result=asyncio.run(check());assert result.body==body and result.receipt.total_tokens==150 and result.safe_error_code is None and len(calls)==1
