"""Private bodies stay in memory. Fixed OpenAI endpoint, no automatic retry/fallback."""
import asyncio
import httpx
from typing import Protocol
from openai import AsyncOpenAI,APIStatusError,APITimeoutError,APIConnectionError,APIResponseValidationError
from openai.types.chat import ChatCompletionChunk
from pydantic import ValidationError
from app.ai.types import ProviderOutcome,UsageReceipt
from app.ai.pricing import cost_krw

PER_CALL_TIMEOUT=60.0

class Provider(Protocol):
    async def generate(self,claim,messages,on_delta)->ProviderOutcome:...
    async def close(self):...

class MockProvider:
    async def generate(self,claim,messages,on_delta):
        body='모의 AI 응답입니다. 실제 모델 호출 없이 실행·권한·사용량 흐름을 검증했습니다.'
        for text in (body[:15],body[15:]):
            await asyncio.sleep(0.01);await on_delta(text)
        return ProviderOutcome(body,UsageReceipt(120,40,160,'gpt-4o-mini','default','mock-'+str(claim.call_id)),'observed',None)
    async def close(self):pass

class StrictReceiptClient(AsyncOpenAI):
    # Version-pinned SDK response hook: prevent bool/string/float token coercion before metering.
    # Only ChatCompletionChunk is customized; URL, retries, timeout, framing remain SDK-owned.
    def _process_response_data(self,*,data,cast_to,response):
        if cast_to is ChatCompletionChunk:
            try:return ChatCompletionChunk.model_validate(data,strict=True)
            except ValidationError:raise APIResponseValidationError(response=response,body=None) from None
        return super()._process_response_data(data=data,cast_to=cast_to,response=response)

class OpenAIProvider:
    response_format=None
    max_completion_tokens=1024
    def __init__(self,api_key,*,http_client=None):
        # Passing empty optional identity values prevents unrelated environment defaults.
        http_client=http_client or httpx.AsyncClient(trust_env=False,timeout=60.0)
        self.client=StrictReceiptClient(api_key=api_key,base_url='https://api.openai.com/v1',max_retries=0,timeout=60.0,
            organization='',project='',admin_api_key='',webhook_secret='',http_client=http_client,
            _strict_response_validation=True)

    async def generate(self,claim,messages,on_delta):
        deadline=asyncio.timeout(PER_CALL_TIMEOUT)
        async with deadline:
            outcome=await self._generate(claim,messages,on_delta)
        if deadline.expired():return ProviderOutcome(None,outcome.receipt,outcome.end_status,'PROVIDER_TIMEOUT')
        return outcome

    async def _generate(self,claim,messages,on_delta):
        chunks=[];size=0;receipt=None;finished=False;code=None;stream=None;invalid=False
        try:
            stream=await self.client.chat.completions.create(model='gpt-4o-mini',messages=messages,
                service_tier='default',max_completion_tokens=self.max_completion_tokens,stream=True,stream_options={'include_usage':True},n=1,store=False,**({'response_format':self.response_format} if self.response_format is not None else {}))
            request_id=stream.response.headers.get('x-request-id')
            async for chunk in stream:
                if chunk.model not in ('gpt-4o-mini','gpt-4o-mini-2024-07-18') or chunk.service_tier!='default':invalid=True
                if chunk.usage is not None:
                    u=chunk.usage
                    candidate=UsageReceipt(u.prompt_tokens,u.completion_tokens,u.total_tokens,chunk.model,chunk.service_tier,request_id)
                    try:cost_krw(candidate)
                    except (ValueError,TypeError):invalid=True
                    else:
                        if receipt is not None and receipt!=candidate:invalid=True
                        receipt=candidate
                if not chunk.choices:continue
                if len(chunk.choices)!=1 or chunk.choices[0].index!=0:invalid=True;continue
                choice=chunk.choices[0]
                if choice.delta.refusal:code='RESPONSE_BLOCKED'
                text=choice.delta.content
                if text:
                    if finished:invalid=True;continue
                    if not isinstance(text,str) or '\x00' in text:code='RESPONSE_BLOCKED';continue
                    size+=len(text.encode('utf-8'))
                    if size>65536:code='OUTPUT_TRUNCATED';break
                    chunks.append(text)
                    if not invalid:await on_delta(text)
                if choice.finish_reason is not None:
                    finished=True
                    code=code or {'stop':None,'length':'OUTPUT_TRUNCATED','content_filter':'RESPONSE_BLOCKED'}.get(choice.finish_reason,'RESPONSE_BLOCKED')
            if invalid:return ProviderOutcome(None,None,'observed' if finished else 'unknown','USAGE_INVALID')
            if not finished:return ProviderOutcome(None,receipt,'unknown',code or 'STREAM_INTERRUPTED')
            body=''.join(chunks)
            return ProviderOutcome(body if body.strip() and code is None else None,receipt,'observed',code or (None if body.strip() else 'EMPTY_RESPONSE'))
        except APITimeoutError:return ProviderOutcome(None,receipt,'observed' if finished else 'unknown','PROVIDER_TIMEOUT')
        except APIStatusError:return ProviderOutcome(None,receipt,'observed','PROVIDER_ERROR')
        except APIConnectionError:return ProviderOutcome(None,receipt,'observed' if finished else 'unknown','PROVIDER_ERROR')
        except APIResponseValidationError:return ProviderOutcome(None,None,'observed' if finished else 'unknown','USAGE_INVALID')
        except (ValueError,TypeError,UnicodeError):return ProviderOutcome(None,None,'unknown','USAGE_INVALID')
        except asyncio.CancelledError:return ProviderOutcome(None,receipt,'observed' if finished else 'unknown','EXECUTION_INTERRUPTED')
        except Exception:return ProviderOutcome(None,receipt,'unknown','STREAM_INTERRUPTED')
        finally:
            if stream is not None:
                try:await stream.close()
                except Exception:pass
    async def close(self):await self.client.close()
