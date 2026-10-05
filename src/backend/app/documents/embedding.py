"""Embedding uses one permit/dispatch/meter path. Unknown dispatch is never retried."""
from dataclasses import asdict
import hashlib
import math
import struct
import secrets
from uuid import UUID
from psycopg.types.json import Jsonb
from app.ai.providers import StrictReceiptClient
from app.ai.types import UsageReceipt
from app.ai.pricing import cost_krw
from app.errors import AppError


def vector_values(values,count):
    if type(values) not in (list,tuple) or len(values)!=count:raise ValueError('VECTOR_INVALID')
    for vector in values:
        if type(vector) not in (list,tuple) or len(vector)!=1536 or any(type(x) not in (float,int) or not math.isfinite(x) for x in vector) or not any(x!=0 for x in vector):raise ValueError('VECTOR_INVALID')
    result=[]
    try:
        for v in values:
            rounded=[struct.unpack('f',struct.pack('f',float(x)))[0] for x in v]
            norm=math.sqrt(math.fsum(x*x for x in rounded))
            if not math.isfinite(norm) or norm==0:raise ValueError('VECTOR_INVALID')
            result.append(tuple(struct.unpack('f',struct.pack('f',x/norm))[0] for x in rounded))
    except (OverflowError,struct.error):raise ValueError('VECTOR_INVALID') from None
    return tuple(result)


class MockEmbeddingProvider:
    mode="mock"
    async def embed(self,claim,texts,tokens):
        vectors=[]
        for text in texts:
            seed=hashlib.sha256(text.encode()).digest()
            vectors.append([(1 if seed[i%32]&(1<<(i%8)) else -1)/math.sqrt(1536) for i in range(1536)])
        return vectors,UsageReceipt(tokens,0,tokens,'text-embedding-3-small','default','mock-'+str(claim))
    async def close(self):pass


class OpenAIEmbeddingProvider:
    mode="real"
    def __init__(self,api_key,*,http_client=None):
        import httpx2
        from openai.types.create_embedding_response import CreateEmbeddingResponse
        class Client(StrictReceiptClient):
            def _process_response_data(self,*,data,cast_to,response):
                if cast_to is CreateEmbeddingResponse:
                    from openai import APIResponseValidationError
                    try:return CreateEmbeddingResponse.model_validate(data,strict=True)
                    except ValueError:raise APIResponseValidationError(response=response,body=None) from None
                return super()._process_response_data(data=data,cast_to=cast_to,response=response)
        self.client=Client(api_key=api_key,base_url='https://api.openai.com/v1',max_retries=0,timeout=60.0,organization='',project='',admin_api_key='',webhook_secret='',http_client=http_client or httpx2.AsyncClient(trust_env=False,timeout=60.0),_strict_response_validation=True)
    async def embed(self,claim,texts,tokens):
        result=await self.client.embeddings.create(model='text-embedding-3-small',input=texts,dimensions=1536,encoding_format='float')
        if result.model!='text-embedding-3-small' or len(result.data)!=len(texts) or [x.index for x in result.data]!=list(range(len(texts))):raise ValueError('VECTOR_INVALID')
        receipt=UsageReceipt(result.usage.prompt_tokens,0,result.usage.total_tokens,result.model,'default',result._request_id)
        cost_krw(receipt)
        return vector_values([x.embedding for x in result.data],len(texts)),receipt
    async def close(self):await self.client.close()


class EmbeddingGateway:
    def __init__(self,index_pool,meter_pool,provider,period):
        self.index_pool=index_pool;self.meter_pool=meter_pool;self.provider=provider;self.period=period

    async def rpc(self,name,args,meter=False):
        pool=self.meter_pool if meter else self.index_pool
        async with pool.connection() as conn:
            async with conn.transaction():
                return (await (await conn.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+') AS data',args)).fetchone())['data']

    async def batch(self,ticket,batch,texts):
        args=(ticket['tenant_id'],ticket['job_id'],ticket['epoch'],ticket['claim'])
        permit=await self.rpc('document_embedding_permit',(*args,self.period,batch.ordinal,bytes.fromhex(batch.fingerprint)))
        if not permit['created']:raise AppError('INDEX_NEEDS_REVIEW',409)
        call=UUID(permit['call_id']);dispatch=secrets.token_bytes(32)
        # A commit-uncertain dispatch cannot authorize a provider call.
        if not await self.rpc('document_embedding_dispatch',(*args,call,dispatch)):raise AppError('INDEX_NEEDS_REVIEW',409)
        try:
            vectors,receipt=await self.provider.embed(call,texts,batch.token_count)
            vectors=vector_values(vectors,len(texts));cost_krw(receipt)
            outcome=await self.rpc('call_meter',(ticket['tenant_id'],call,ticket['epoch'],dispatch,Jsonb(asdict(receipt)),'observed',False),True)
            if outcome['state']!='settled' or outcome['conflict'] or outcome['invalid'] or outcome['overrun']:raise AppError('INDEX_NEEDS_REVIEW',409)
            return call,vectors
        except BaseException:
            # No second remote attempt. A known settled receipt is idempotent; missing is unknown.
            try:await self.rpc('call_meter',(ticket['tenant_id'],call,ticket['epoch'],dispatch,None,'unknown',False),True)
            except BaseException:pass
            raise
