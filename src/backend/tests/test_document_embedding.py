import asyncio,json
import httpx2
import pytest
from app.documents.embedding import OpenAIEmbeddingProvider,vector_values

@pytest.mark.parametrize('case',['valid','bool_usage','wrong_model','bad_dimension','zero_vector','http_error'])
def test_pinned_sdk_embedding_contract_without_network(case):
    calls=[]
    async def transport(request):
        calls.append(request)
        assert request.url.host=='api.openai.com' and request.url.path=='/v1/embeddings'
        body=json.loads(request.content);assert body['model']=='text-embedding-3-small' and body['dimensions']==1536 and body['encoding_format']=='float'
        if case=='http_error':return httpx2.Response(503,json={'error':{'message':'synthetic','type':'server_error'}})
        vector=[1.0]+[0.0]*1535
        if case=='bad_dimension':vector=vector[:-1]
        if case=='zero_vector':vector=[0.0]*1536
        data={'object':'list','model':'wrong' if case=='wrong_model' else 'text-embedding-3-small','data':[{'object':'embedding','index':0,'embedding':vector}],'usage':{'prompt_tokens':True if case=='bool_usage' else 4,'total_tokens':4}}
        return httpx2.Response(200,json=data,headers={'x-request-id':'synthetic-embedding'})
    async def check():
        client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport),trust_env=False)
        provider=OpenAIEmbeddingProvider('synthetic-not-real',http_client=client)
        try:
            if case=='valid':
                vectors,receipt=await provider.embed('synthetic',['합성 입력'],4);assert len(vectors[0])==1536 and receipt.total_tokens==4
            else:
                with pytest.raises(Exception):await provider.embed('synthetic',['합성 입력'],4)
            assert len(calls)==1
        finally:await provider.close()
    asyncio.run(check())
