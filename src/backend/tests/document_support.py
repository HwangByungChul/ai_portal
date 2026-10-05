from dataclasses import dataclass
import hashlib
from uuid import uuid4
import pytest
from psycopg.types.json import Jsonb

@dataclass
class Documents:
    f: object
    org: object
    private: object
    versions: list
    indexes: list
    private_version: object
    private_index: object
    job: object
    claim: str
    grant: object
    chunks: list

    def resolve(self, actor, tenant, doc=None, version=None):
        from app.documents.policy import resolve_readable_version
        ctx=self.f.run(self.f.context(actor,tenant))
        return self.f.run(resolve_readable_version(self.f.pool,ctx,doc or self.org,version))

    def index_connection(self, *, claim=None, epoch='1', job=None, tenant=None):
        conn=self.f.role_connection('ai_index')
        values={'app.job_id':str(job or self.job),'app.job_epoch':str(epoch),
                'app.job_tenant_id':str(tenant or self.f.tenant_ids['A']),
                'app.job_claim':self.claim if claim is None else claim}
        for k,v in values.items():conn.execute('SELECT set_config(%s,%s,false)',(k,v))
        return conn


def add_version(conn, tenant, doc, number, state='published', *, mode='mock',pipeline='c01-v1'):
    version,index=uuid4(),uuid4();body=b'sample';sha=hashlib.sha256(body).digest()
    conn.execute('''INSERT INTO rag.document_versions(tenant_id,document_id,version_id,version_no,title,source_object_key,source_sha256,media_type,byte_length,character_length,ingest_hmac,parser_revision,source_mapping)
     VALUES(%s,%s,%s,%s,'synthetic','tenants/'||%s::text||'/documents/'||%s::text||'/'||%s::text||'/source',%s,'text/plain',6,6,%s,'c01-v1',%s)''',
     (tenant,doc,version,number,tenant,doc,version,sha,sha,Jsonb({})))
    conn.execute('''INSERT INTO rag.index_builds(tenant_id,document_id,version_id,index_id,execution_mode,pipeline_revision,source_fingerprint,state)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',(tenant,doc,version,index,mode,pipeline,sha,state))
    if state=='published':conn.execute('INSERT INTO security.document_publications(tenant_id,document_id,version_id,published_index_id,active) VALUES(%s,%s,%s,%s,true)',(tenant,doc,version,index))
    return version,index


def add_chunk(conn,tenant,doc,version,index,*,ordinal=0,vector=None):
    chunk=uuid4();vector=vector or '['+','.join(['1']+['0']*1535)+']'
    conn.execute('''INSERT INTO rag.chunks(tenant_id,document_id,version_id,index_id,chunk_id,ordinal,text,location,embedding,source_sha256,batch_ordinal)
      VALUES(%s,%s,%s,%s,%s,%s,'sample',%s,%s::rag.vector,%s,0)''',
      (tenant,doc,version,index,chunk,ordinal,Jsonb({}),vector,hashlib.sha256(b'sample').digest()))
    return chunk


@pytest.fixture
def documents(db_fixture):
    f=db_fixture;tenant=f.tenant_ids['A'];org,private=uuid4(),uuid4();versions=[];indexes=[];chunks=[];job,grant=uuid4(),uuid4();claim=hashlib.sha256(uuid4().bytes).hexdigest()
    with f.db.admin_connection() as conn:
        with conn.transaction():
            for doc,visibility in [(org,'org'),(private,'private')]:
                conn.execute('INSERT INTO security.document_access(tenant_id,document_id,owner_user_id,visibility) VALUES(%s,%s,%s,%s)',(tenant,doc,f.actor_ids['A-U1'],visibility))
            conn.execute('INSERT INTO security.private_readers VALUES(%s,%s,%s)',(tenant,private,f.actor_ids['A-U2']))
            for number in [1,2,3]:
                version,index=add_version(conn,tenant,org,number,'staging' if number==3 else 'published')
                versions.append(version);indexes.append(index);chunks.append(add_chunk(conn,tenant,org,version,index))
            pv,pi=add_version(conn,tenant,private,1);add_chunk(conn,tenant,private,pv,pi)
            conn.execute('INSERT INTO security.share_grants(grant_id,owner_tenant_id,document_id,version_id,recipient_tenant_id,issued_by) VALUES(%s,%s,%s,%s,%s,%s)',(grant,tenant,org,versions[0],f.tenant_ids['B'],f.actor_ids['A-ADM']))
            conn.execute('''INSERT INTO rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,execution_mode,state,heartbeat_at,lease_expires_at)
                VALUES(%s,%s,%s,%s,%s,%s,'internal_index','mock','running',clock_timestamp(),clock_timestamp()+interval '60 seconds')''',
                (tenant,job,org,versions[2],indexes[2],f.actor_ids['A-ADM']))
            conn.execute('''INSERT INTO security.job_authorizations(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,action,lease_hash,lease_epoch,expires_at)
              VALUES(%s,%s,%s,%s,%s,%s,'internal_index',%s,1,clock_timestamp()+interval '60 seconds')''',
              (tenant,job,org,versions[2],indexes[2],f.actor_ids['A-ADM'],bytes.fromhex(claim)))
    return Documents(f,org,private,versions,indexes,pv,pi,job,claim,grant,chunks)
