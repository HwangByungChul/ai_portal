"""Pinned SDK HTTP failure cases: no network, no automatic retries."""
import asyncio
from uuid import uuid4
import pytest
import httpx2
from app.ai.providers import OpenAIProvider
from app.ai.types import DispatchClaim
from app.documents.embedding import OpenAIEmbeddingProvider

@pytest.mark.parametrize('status',[401,429,500,503])
@pytest.mark.parametrize('operation',['generate','embed'])
def test_provider_http_errors_are_one_attempt_and_do_not_return_content(status,operation):
 calls=[];marker='T286-PROVIDER-PRIVATE-7812'
 def transport(request):
  calls.append(str(request.url));return httpx2.Response(status,json={'error':{'message':marker,'type':'synthetic'}},request=request)
 async def check():
  client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport),trust_env=False)
  provider=OpenAIProvider('synthetic-not-a-key',http_client=client) if operation=='generate' else OpenAIEmbeddingProvider('synthetic-not-a-key',http_client=client)
  try:
   if operation=='generate':
    async def delta(text):raise AssertionError('error response must not display text')
    result=await provider.generate(DispatchClaim(uuid4(),1,'synthetic-proof'),[{'role':'user','content':'합성 질문'}],delta)
    assert result.body is None and result.receipt is None and result.safe_error_code=='PROVIDER_ERROR' and marker not in repr(result)
   else:
    from openai import APIStatusError
    with pytest.raises(APIStatusError):await provider.embed(uuid4(),['합성 자료'],4)
  finally:await provider.close()
 asyncio.run(check());assert len(calls)==1
