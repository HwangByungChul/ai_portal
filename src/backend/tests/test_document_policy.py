from dataclasses import replace
from uuid import uuid4
import psycopg
import pytest
from app.db import tenant_transaction, make_index_pool, DatabaseBoundaryError
from app.documents.policy import DocumentUnavailable,resolve_readable_version
from document_support import documents,add_chunk

@pytest.mark.parametrize('actor,tenant,version_no',[('A-U1','A',2),('A-U2','A',2),('A-ADM','A',2),('P-A','A',2),('B-U1','B',1),('B-ADM','B',1),('DUAL','A',2),('DUAL','B',1)])
def test_latest_allowed_version(documents,actor,tenant,version_no):
    result=documents.resolve(actor,tenant)
    assert result.version_no==version_no and result.index_id==documents.indexes[version_no-1]

@pytest.mark.parametrize('actor,tenant,allowed',[('A-U1','A',True),('A-U2','A',True),('A-ADM','A',False),('P-A','A',False),('B-U1','B',False),('DUAL','A',False),('DUAL','B',False)])
def test_private_reader_is_not_administrator(documents,actor,tenant,allowed):
    if allowed:assert documents.resolve(actor,tenant,documents.private).version_id==documents.private_version
    else:
        with pytest.raises(DocumentUnavailable,match='^DOCUMENT_UNAVAILABLE$'):documents.resolve(actor,tenant,documents.private)

@pytest.mark.parametrize('target',['missing','unshared','staging'])
def test_unavailable_objects_have_same_outcome(documents,target):
    d=documents;doc=uuid4() if target=='missing' else d.org
    version=None if target=='missing' else d.versions[1 if target=='unshared' else 2]
    with pytest.raises(DocumentUnavailable,match='^DOCUMENT_UNAVAILABLE$'):d.resolve('B-U1','B',doc,version)

@pytest.mark.parametrize('mutation',['share','publication','deleted','owner_tenant'])
def test_current_source_revocation(documents,mutation):
    d=documents;assert d.resolve('B-U1','B').version_no==1
    with d.f.db.admin_connection() as conn:
        if mutation=='share':conn.execute('UPDATE security.share_grants SET active=false,revoked_at=clock_timestamp() WHERE grant_id=%s',(d.grant,))
        elif mutation=='publication':conn.execute('UPDATE security.document_publications SET active=false WHERE version_id=%s',(d.versions[0],))
        elif mutation=='deleted':conn.execute('UPDATE security.document_access SET deleted_at=clock_timestamp() WHERE document_id=%s',(d.org,))
        else:conn.execute('UPDATE security.tenants SET active=false WHERE tenant_id=%s',(d.f.tenant_ids['A'],))
    with pytest.raises(DocumentUnavailable):d.resolve('B-U1','B')

@pytest.mark.parametrize('mutation',['account','tenant','membership','revision','revoked','expired','idle'])
def test_stored_context_revalidates(documents,mutation):
    d=documents;ctx=d.f.run(d.f.context('B-U1','B'));assert d.f.run(resolve_readable_version(d.f.pool,ctx,d.org)).version_no==1
    d.f.mutate_access(ctx,mutation)
    with pytest.raises(DocumentUnavailable):d.f.run(resolve_readable_version(d.f.pool,ctx,d.org))

def test_forged_context_and_role_fields_do_not_authorize(documents):
    d=documents;ctx=d.f.run(d.f.context('B-U1','B'))
    with pytest.raises(DocumentUnavailable):d.f.run(resolve_readable_version(d.f.pool,replace(ctx,user_id=d.f.actor_ids['A-U1']),d.private))
    with pytest.raises(DocumentUnavailable):d.f.run(resolve_readable_version(d.f.pool,replace(ctx,effective_role='PADMIN'),d.private))

def test_raw_web_rls_and_context_cleanup(documents):
    d=documents;ctx=d.f.run(d.f.context('B-U1','B'))
    async def inspect():
        async with tenant_transaction(d.f.pool,ctx) as conn:
            rows=await (await conn.execute('SELECT version_id FROM rag.document_versions')).fetchall()
            assert [x['version_id'] for x in rows]==[d.versions[0]]
            assert len(await (await conn.execute('SELECT chunk_id FROM rag.chunks')).fetchall())==1
        async with d.f.pool.connection() as conn:
            assert await (await conn.execute('SELECT chunk_id FROM rag.chunks')).fetchall()==[]
            await conn.execute("SELECT set_config('app.tenant_id','invalid',false)")
            assert await (await conn.execute('SELECT chunk_id FROM rag.chunks')).fetchall()==[]
    d.f.run(inspect())

@pytest.mark.parametrize('claim,epoch,job,tenant',[('0'*64,'1',None,None),('invalid','1',None,None),(None,'2',None,None),(None,'bad',None,None),(None,'1','missing',None),(None,'1',None,'B')])
def test_index_lease_cannot_be_forged(documents,claim,epoch,job,tenant):
    d=documents
    with d.index_connection(claim=claim,epoch=epoch,job=uuid4() if job else None,tenant=d.f.tenant_ids[tenant] if tenant else None) as conn:
        assert conn.execute('SELECT chunk_id FROM rag.chunks').fetchall()==[]

@pytest.mark.parametrize('mutation',['expired','revoked','job_epoch','job_expired','initiator_membership','initiator_account','deleted','cleanup'])
def test_index_lease_revocation_and_cleanup_no_read(documents,mutation):
    d=documents
    with d.index_connection() as conn:assert conn.execute('SELECT chunk_id FROM rag.chunks').fetchall()==[(d.chunks[2],)]
    with d.f.db.admin_connection() as conn:
        if mutation=='expired':conn.execute("UPDATE security.job_authorizations SET expires_at=clock_timestamp()-interval '1 second'")
        elif mutation=='revoked':conn.execute('UPDATE security.job_authorizations SET revoked_at=clock_timestamp()')
        elif mutation=='job_epoch':conn.execute('UPDATE rag.jobs SET lease_epoch=2')
        elif mutation=='job_expired':conn.execute("UPDATE rag.jobs SET lease_expires_at=clock_timestamp()-interval '1 second'")
        elif mutation=='initiator_membership':conn.execute('UPDATE security.memberships SET active=false WHERE user_id=%s',(d.f.actor_ids['A-ADM'],))
        elif mutation=='initiator_account':conn.execute('UPDATE security.accounts SET active=false WHERE user_id=%s',(d.f.actor_ids['A-ADM'],))
        elif mutation=='deleted':conn.execute('UPDATE security.document_access SET deleted_at=clock_timestamp() WHERE document_id=%s',(d.org,))
        else:
            # A distinct cleanup job can exist after indexing has terminated; it grants no payload reads.
            conn.execute("UPDATE rag.jobs SET state='interrupted',stage='terminal',ended_at=clock_timestamp()")
            j=uuid4();conn.execute('''INSERT INTO rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,execution_mode,state,heartbeat_at,lease_expires_at)
              VALUES(%s,%s,%s,%s,%s,%s,'internal_cleanup','mock','running',clock_timestamp(),clock_timestamp()+interval '60 seconds')''',
              (d.f.tenant_ids['A'],j,d.org,d.versions[2],d.indexes[2],d.f.actor_ids['A-ADM']))
            conn.execute('''INSERT INTO security.job_authorizations(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,action,deletion_revision,lease_hash,lease_epoch,expires_at)
              VALUES(%s,%s,%s,%s,%s,%s,'internal_cleanup',1,%s,1,clock_timestamp()+interval '60 seconds')''',
              (d.f.tenant_ids['A'],j,d.org,d.versions[2],d.indexes[2],d.f.actor_ids['A-ADM'],bytes.fromhex(d.claim)));d.job=j
    with d.index_connection() as conn:assert conn.execute('SELECT chunk_id FROM rag.chunks').fetchall()==[]

def test_index_write_exact_staging_target(documents):
    d=documents;tenant=d.f.tenant_ids['A']
    with d.index_connection() as conn:
        add_chunk(conn,tenant,d.org,d.versions[2],d.indexes[2],ordinal=1)
        for v,i in [(d.versions[0],d.indexes[0]),(d.private_version,d.private_index)]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):add_chunk(conn,tenant,d.org if v==d.versions[0] else d.private,v,i,ordinal=1)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('UPDATE rag.chunks SET text=\'changed\'')
        assert conn.execute('SELECT version_id FROM rag.document_versions').fetchall()==[(d.versions[2],)]

@pytest.mark.parametrize('role',['ai_web','ai_index','ai_meter'])
def test_runtime_roles_cannot_mutate_control_or_become_owner(documents,role):
    with documents.f.role_connection(role) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT * FROM security.document_access')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('DELETE FROM security.share_grants')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SET ROLE ai_policy_executor')
        if role=='ai_meter':
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT text FROM rag.chunks')

def test_index_pool_verifies_identity_and_owns_no_content(documents):
    d=documents
    async def check():
        pool=make_index_pool(d.f.db.runtime_dsn('ai_index'),1)
        try:
            await pool.open();await pool.wait(timeout=5)
            async with pool.connection() as conn:assert (await (await conn.execute('SELECT current_user AS role')).fetchone())['role']=='ai_index'
        finally:await pool.close()
    d.f.run(check())
    with pytest.raises(DatabaseBoundaryError):make_index_pool(d.f.db.runtime_dsn('ai_web'))


def test_index_initiator_downgrade_blocks_payload(documents):
    d=documents
    with d.index_connection() as conn:assert len(conn.execute('SELECT chunk_id FROM rag.chunks').fetchall())==1
    with d.f.db.admin_connection() as conn:conn.execute("UPDATE security.memberships SET role='USER' WHERE user_id=%s",(d.f.actor_ids['A-ADM'],))
    with d.index_connection() as conn:assert conn.execute('SELECT chunk_id FROM rag.chunks').fetchall()==[]


def test_publication_replacement_does_not_expose_old_index(documents):
    from document_support import add_version
    from uuid import uuid4
    d=documents;tenant=d.f.tenant_ids['A'];new_index=uuid4()
    with d.f.db.admin_connection() as conn:
        conn.execute("INSERT INTO rag.index_builds(tenant_id,document_id,version_id,index_id,execution_mode,pipeline_revision,source_fingerprint,state) SELECT tenant_id,document_id,version_id,%s,'mock','c01-v2',source_fingerprint,'published' FROM rag.index_builds WHERE index_id=%s",(new_index,d.indexes[0]))
        conn.execute('UPDATE security.document_publications SET published_index_id=%s,revision=revision+1 WHERE version_id=%s',(new_index,d.versions[0]))
    assert d.resolve('B-U1','B').index_id==new_index
    ctx=d.f.run(d.f.context('B-U1','B'))
    async def check():
        async with tenant_transaction(d.f.pool,ctx) as conn:
            assert await (await conn.execute('SELECT chunk_id FROM rag.chunks WHERE index_id=%s',(d.indexes[0],))).fetchall()==[]
    d.f.run(check())
