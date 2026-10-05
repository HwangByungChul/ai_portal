import asyncio
import json
from uuid import uuid4
import httpx2
import pytest
from app.ai.providers import OpenAIProvider
from app.ai.types import DispatchClaim


def chunk(text=None,finish=None,usage=None,model='gpt-4o-mini',tier='default',refusal=None):
    return {'id':'chatcmpl-synthetic','object':'chat.completion.chunk','created':1780000000,'model':model,'service_tier':tier,
        'choices':[] if usage is not None else [{'index':0,'delta':{'content':text,'refusal':refusal},'finish_reason':finish}], 'usage':usage}

@pytest.mark.parametrize('case,code,end,has_usage',[('normal',None,'observed',True),('missing_usage',None,'observed',False),
 ('eof','STREAM_INTERRUPTED','unknown',False),('length','OUTPUT_TRUNCATED','observed',True),('empty','EMPTY_RESPONSE','observed',True),
 ('refusal','RESPONSE_BLOCKED','observed',True),('wrong_model','USAGE_INVALID','observed',False),
 ('wrong_tier','USAGE_INVALID','observed',False),('bad_usage','USAGE_INVALID','observed',False),('bool_usage','USAGE_INVALID','observed',False),
 ('float_usage','USAGE_INVALID','observed',False),('string_usage','USAGE_INVALID','observed',False),('http','PROVIDER_ERROR','observed',False),
 ('timeout','PROVIDER_TIMEOUT','unknown',False),('connection','PROVIDER_ERROR','unknown',False)])
def test_real_sdk_stream_with_fake_transport_only(case,code,end,has_usage):
    calls=[];deltas=[]
    def transport(request):
        calls.append(json.loads(request.content))
        assert str(request.url)=='https://api.openai.com/v1/chat/completions'
        if case=='timeout':raise httpx2.ReadTimeout('synthetic-private-error',request=request)
        if case=='connection':raise httpx2.ConnectError('synthetic-private-error',request=request)
        if case=='http':return httpx2.Response(429,json={'error':{'message':'synthetic-private-error','type':'synthetic'}},request=request)
        usage={'prompt_tokens':120,'completion_tokens':40,'total_tokens':160}
        if case=='bad_usage':usage['total_tokens']=99
        if case=='bool_usage':usage={'prompt_tokens':True,'completion_tokens':40,'total_tokens':41}
        if case=='float_usage':usage={'prompt_tokens':120.0,'completion_tokens':40,'total_tokens':160}
        if case=='string_usage':usage={'prompt_tokens':'120','completion_tokens':40,'total_tokens':160}
        kwargs={'model':'other-model'} if case=='wrong_model' else {'tier':'priority'} if case=='wrong_tier' else {}
        rows=[] if case=='empty' else [chunk('합성 응답',refusal='blocked' if case=='refusal' else None,**kwargs)]
        if case!='eof':rows.append(chunk(finish='length' if case=='length' else 'stop',**kwargs))
        if case not in ('missing_usage','eof'):rows.append(chunk(usage=usage,**kwargs))
        body=''.join('data: '+json.dumps(v)+'\n\n' for v in rows)+'data: [DONE]\n\n'
        return httpx2.Response(200,headers={'content-type':'text/event-stream','x-request-id':'synthetic-request'},content=body.encode(),request=request)
    async def run():
        provider=OpenAIProvider('synthetic-not-a-real-key',http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport),trust_env=False))
        async def delta(text):deltas.append(text)
        try:return await provider.generate(DispatchClaim(uuid4(),1,'synthetic-proof'),[{'role':'user','content':'합성 질문'}],delta)
        finally:await provider.close()
    result=asyncio.run(run())
    assert result.safe_error_code==code and result.end_status==end and (result.receipt is not None)==has_usage
    assert len(calls)==1
    assert calls[0]=={'model':'gpt-4o-mini','messages':[{'role':'user','content':'합성 질문'}],'service_tier':'default',
        'max_completion_tokens':1024,'stream':True,'stream_options':{'include_usage':True},'n':1,'store':False}
    assert result.body==('합성 응답' if code is None else None)
    assert 'synthetic-private-error' not in repr(result)


def test_total_stream_deadline_is_not_only_per_read_timeout(monkeypatch):
    import app.ai.providers as module
    monkeypatch.setattr(module,'PER_CALL_TIMEOUT',.03)
    calls=[]
    class SlowStream(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield ('data: '+json.dumps(chunk('합성 부분 응답'))+'\n\n').encode()
            await asyncio.sleep(1)
        async def aclose(self):pass
    def transport(request):
        calls.append(request)
        return httpx2.Response(200,headers={'content-type':'text/event-stream'},stream=SlowStream(),request=request)
    async def check():
        provider=OpenAIProvider('synthetic-not-a-real-key',http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport),trust_env=False))
        async def delta(text):pass
        start=asyncio.get_running_loop().time()
        try:outcome=await provider.generate(DispatchClaim(uuid4(),1,'synthetic-proof'),[{'role':'user','content':'합성 질문'}],delta)
        finally:await provider.close()
        assert outcome.safe_error_code=='PROVIDER_TIMEOUT' and outcome.end_status=='unknown' and outcome.body is None
        assert asyncio.get_running_loop().time()-start<.5 and len(calls)==1
    asyncio.run(check())
