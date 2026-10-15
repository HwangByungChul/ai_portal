"""Private browser harness only; fixed mock provider, no real key/environment use."""
import asyncio,json,os
from dataclasses import replace
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
        outcome=await super().generate(claim,messages,on_delta)
        # Explicit private fixture control; deterministic contract result, not quality acceptance.
        if behavior=='meeting':
            context=None
            for message in messages:
                try:
                    candidate=json.loads(message.get('content',''))
                    if isinstance(candidate,dict) and 'meeting_date' in candidate:context=candidate
                except (ValueError,TypeError):pass
            documents=context.get('documents',[]) if context else []
            ref=documents[0]['source_ref'] if documents else 'memo'
            outcome=replace(outcome,body=json.dumps({'decisions':[{'text':'자료 검토','quote':'자료를 검토하기로 했다.','source_ref':ref}],'unresolved':[],'actions':[{'text':'후속 검토','quote':'김검토는 내일 자료를 확인한다.','source_ref':ref,'assignee':'김검토','due_expression':'내일','due_date':None}] if context else []},ensure_ascii=False))
        return outcome

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
    settings=Settings(openai_api_key=None,mode='mock',execution_enabled=True,portal_origins=('http://127.0.0.1:5173','http://127.0.0.1:5174') if os.environ.get('PORTAL_TEST_PORTS')=='1' else ())
    import app.ai.routing as routing
    routing.MockProvider=BrowserMock
    main.SummaryMockProvider=BrowserSummary;main.MockProvider=BrowserMock;main.RagMockProvider=BrowserRag;main.MockEmbeddingProvider=BrowserEmbedding
    return main.create_app(settings)
