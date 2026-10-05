from uuid import uuid4
import psycopg
import pytest
from psycopg.types.json import Jsonb
from document_support import documents,add_chunk,add_version


def test_full_catalog_and_new_privilege_boundary(documents):
    f=documents.f;f.verify_catalog()
    with f.db.admin_connection() as conn:
        assert conn.execute("SELECT extversion,n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE extname='vector'").fetchone()==('0.8.6','rag')
        rows=conn.execute("SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE c.relkind='r' AND n.nspname='rag'").fetchall()
        assert len(rows)==8 and all(r==(True,True,'ai_owner') for r in rows)
        for table,col in [('rag.document_versions','title'),('rag.document_versions','source_object_key'),('rag.chunks','text'),('rag.chunks','embedding'),('rag.evidence','exact_quote'),('portal.answer_evidence','quote_snapshot')]:
            assert not conn.execute('SELECT has_column_privilege(%s,%s,%s,\'SELECT\')',('ai_policy_executor',table,col)).fetchone()[0]
        for table in ['rag.document_versions','rag.chunks','rag.evidence','portal.answer_evidence']:
            assert not conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\')',('ai_meter',table)).fetchone()[0]
        assert conn.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('ai_owner','ai_policy_executor') AND NOT rolcanlogin").fetchone()[0]==2
        assert conn.execute("SELECT count(*) FROM pg_auth_members WHERE member IN (SELECT oid FROM pg_roles WHERE rolname IN ('ai_web','ai_index','ai_meter'))").fetchone()[0]==0

@pytest.mark.parametrize('vector',['['+','.join(['1']*1535)+']','['+','.join(['NaN']+['0']*1535)+']','['+','.join(['Infinity']+['0']*1535)+']'],ids=['dimension-1535','nan','infinity'])
def test_vector_rejects_dimension_and_nonfinite(documents,vector):
    d=documents
    with d.f.db.admin_connection() as conn:
        with pytest.raises(psycopg.DataError):add_chunk(conn,d.f.tenant_ids['A'],d.org,d.versions[2],d.indexes[2],ordinal=1,vector=vector)
        assert conn.execute('SELECT count(*) FROM rag.chunks').fetchone()[0]==4


def test_exact_cosine_search_and_transaction_rollback(documents):
    d=documents;tenant=d.f.tenant_ids['A']
    with d.f.db.admin_connection() as conn:
        v='['+','.join(['0','1']+['0']*1534)+']';other=add_chunk(conn,tenant,d.org,d.versions[0],d.indexes[0],ordinal=1,vector=v)
        query='['+','.join(['1']+['0']*1535)+']'
        rows=conn.execute('SELECT chunk_id,embedding OPERATOR(rag.<=>) %s::rag.vector AS distance FROM rag.chunks WHERE index_id=%s ORDER BY distance,ordinal',(query,d.indexes[0])).fetchall()
        assert rows==[(d.chunks[0],0.0),(other,1.0)]
        with pytest.raises(RuntimeError):
            with conn.transaction():
                add_chunk(conn,tenant,d.org,d.versions[2],d.indexes[2],ordinal=1)
                raise RuntimeError('ROLLBACK_PROBE')
        assert conn.execute('SELECT count(*) FROM rag.chunks WHERE index_id=%s',(d.indexes[2],)).fetchone()[0]==1
        assert conn.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='rag' AND (indexdef LIKE '%hnsw%' OR indexdef LIKE '%ivfflat%')").fetchone()[0]==0

@pytest.mark.parametrize('field,value',[('title','changed'),('source_object_key','../source'),('visibility','private'),('embedding_dimensions',3072),('execution_mode','real')])
def test_source_and_index_identity_are_immutable(documents,field,value):
    d=documents
    with d.f.db.admin_connection() as conn:
        if field in ['title','source_object_key']:table='rag.document_versions';where='version_id';key=d.versions[0]
        elif field=='visibility':table='security.document_access';where='document_id';key=d.org
        else:table='rag.index_builds';where='index_id';key=d.indexes[0]
        with pytest.raises(psycopg.errors.CheckViolation):conn.execute(f'UPDATE {table} SET {field}=%s WHERE {where}=%s',(value,key))

@pytest.mark.parametrize('mutation',['new_private_reader','delete_private_reader','private_share','publish_staging','duplicate_job','job_mode'])
def test_control_constraints(documents,mutation):
    d=documents;tenant=d.f.tenant_ids['A']
    with d.f.db.admin_connection() as conn:
        with pytest.raises((psycopg.errors.CheckViolation,psycopg.errors.UniqueViolation,psycopg.errors.ForeignKeyViolation)):
            if mutation=='new_private_reader':conn.execute('INSERT INTO security.private_readers VALUES(%s,%s,%s)',(tenant,d.private,d.f.actor_ids['A-ADM']))
            elif mutation=='delete_private_reader':conn.execute('DELETE FROM security.private_readers WHERE document_id=%s',(d.private,))
            elif mutation=='private_share':conn.execute('INSERT INTO security.share_grants(grant_id,owner_tenant_id,document_id,version_id,recipient_tenant_id,issued_by) VALUES(%s,%s,%s,%s,%s,%s)',(uuid4(),tenant,d.private,d.private_version,d.f.tenant_ids['B'],d.f.actor_ids['A-ADM']))
            elif mutation=='publish_staging':conn.execute('INSERT INTO security.document_publications(tenant_id,document_id,version_id,published_index_id,active) VALUES(%s,%s,%s,%s,true)',(tenant,d.org,d.versions[2],d.indexes[2]))
            else:
                conn.execute('''INSERT INTO rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,execution_mode)
                  VALUES(%s,%s,%s,%s,%s,%s,'internal_index',%s)''',(tenant,uuid4(),d.org,d.versions[2],d.indexes[2],d.f.actor_ids['A-ADM'],'real' if mutation=='job_mode' else 'mock'))

@pytest.mark.parametrize('mismatch',['tenant','version','index'])
def test_chunk_composite_foreign_keys(documents,mismatch):
    d=documents
    with d.f.db.admin_connection() as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            add_chunk(conn,d.f.tenant_ids['B'] if mismatch=='tenant' else d.f.tenant_ids['A'],d.org,d.versions[1] if mismatch=='version' else d.versions[0],d.indexes[1] if mismatch=='index' else d.indexes[0],ordinal=1)


def test_graph_endpoints_and_evidence_cannot_cross_indexes(documents):
    d=documents;tenant=d.f.tenant_ids['A'];e1,e2=uuid4(),uuid4()
    with d.f.db.admin_connection() as conn:
        for entity,i,v in [(e1,d.indexes[0],d.versions[0]),(e2,d.indexes[1],d.versions[1])]:
            conn.execute("INSERT INTO rag.entities(tenant_id,document_id,version_id,index_id,entity_id,semantic_key,entity_type,label,properties) VALUES(%s,%s,%s,%s,%s,'process','PROCESS','synthetic',%s)",(tenant,d.org,v,i,entity,Jsonb({})))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):conn.execute('INSERT INTO rag.relations(tenant_id,document_id,version_id,index_id,relation_id,from_entity_id,to_entity_id,relation_type,properties) VALUES(%s,%s,%s,%s,%s,%s,%s,\'DEPENDS_ON\',%s)',(tenant,d.org,d.versions[0],d.indexes[0],uuid4(),e1,e2,Jsonb({})))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):conn.execute('''INSERT INTO rag.evidence(tenant_id,document_id,version_id,index_id,evidence_id,chunk_id,start_offset,end_offset,line_start,line_end,exact_quote,source_sha256)
          SELECT %s,%s,%s,%s,%s,%s,0,6,1,1,'sample',source_sha256 FROM rag.document_versions WHERE version_id=%s''',
          (tenant,d.org,d.versions[0],d.indexes[0],uuid4(),d.chunks[1],d.versions[0]))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):conn.execute('INSERT INTO security.document_publications(tenant_id,document_id,version_id,published_index_id) VALUES(%s,%s,%s,%s)',(tenant,d.org,d.versions[2],d.indexes[0]))


def test_inactive_private_grant_is_also_rejected(documents):
    d=documents
    with d.f.db.admin_connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute('INSERT INTO security.share_grants(grant_id,owner_tenant_id,document_id,version_id,recipient_tenant_id,issued_by,active) VALUES(%s,%s,%s,%s,%s,%s,false)',(uuid4(),d.f.tenant_ids['A'],d.private,d.private_version,d.f.tenant_ids['B'],d.f.actor_ids['A-ADM']))


def test_grant_identity_cannot_be_repointed(documents):
    d=documents
    with d.f.db.admin_connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):conn.execute('UPDATE security.share_grants SET version_id=%s WHERE grant_id=%s',(d.versions[1],d.grant))
