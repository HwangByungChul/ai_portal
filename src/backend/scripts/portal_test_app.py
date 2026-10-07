"""Private browser harness only; fixed mock provider, no real key/environment use."""
import asyncio,json,os
from pathlib import Path
from app import main
from app.ai.providers import MockProvider
from app.ai.types import ProviderOutcome
from app.ai.rag_provider import RagMockProvider
from app.ai.summary_provider import SummaryMockProvider
from app.documents.embedding import MockEmbeddingProvider
from app.config import Settings
from scripts.devdb import _read_private
RUNTIME=Path(__file__).resolve().parents[1]/'.runtime'
class BrowserMock(MockProvider):
    async def generate(self,claim,messages,on_delta):
        fd=os.open(RUNTIME/'B05-provider-count.txt',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write('1\n')
        behavior=json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']
        if behavior=='unknown':return ProviderOutcome(None,None,'unknown','STREAM_INTERRUPTED')
        if behavior=='slow':
            await on_delta('저장 전 모의 초안')
            while json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']=='slow':await asyncio.sleep(.05)
        return await super().generate(claim,messages,on_delta)

class BrowserRag(RagMockProvider):
    async def generate(self,claim,messages,on_delta):
        if json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']=='slow-rag':
            await on_delta('공개금지 RAG 초안')
            while json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']=='slow-rag':await asyncio.sleep(.05)
        return await super().generate(claim,messages,on_delta)
class BrowserSummary(SummaryMockProvider):
    async def generate(self,claim,messages,on_delta):
        # Private disposable browser fixture only; production provider is unchanged.
        if json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']=='slow-rag':
            await on_delta('공개금지 요약 초안')
            while json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']=='slow-rag':await asyncio.sleep(.05)
        return await super().generate(claim,messages,on_delta)
class BrowserEmbedding(MockEmbeddingProvider):
    async def embed(self,claim,texts,tokens):
        behavior=json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']
        if behavior=='unknown-index':raise TimeoutError()
        while json.loads(_read_private(RUNTIME/'B05-provider-control.json'))['behavior']=='slow-index':await asyncio.sleep(.05)
        return await super().embed(claim,texts,tokens)

def create_app():
    settings=Settings(openai_api_key=None,mode='mock',execution_enabled=True)
    main.SummaryMockProvider=BrowserSummary;main.MockProvider=BrowserMock;main.RagMockProvider=BrowserRag;main.MockEmbeddingProvider=BrowserEmbedding
    return main.create_app(settings)
