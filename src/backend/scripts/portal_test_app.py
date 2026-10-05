"""Private browser harness only; fixed mock provider, no real key/environment use."""
import asyncio,json,os
from pathlib import Path
from app import main
from app.ai.providers import MockProvider
from app.ai.types import ProviderOutcome
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

def create_app():
    settings=Settings(openai_api_key=None,mode='mock',execution_enabled=True)
    main.MockProvider=BrowserMock
    return main.create_app(settings)
