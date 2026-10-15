from uuid import uuid4,UUID
from concurrent.futures import ThreadPoolExecutor
import json,pytest,psycopg
from psycopg.types.json import Jsonb
from test_assets import config,create
from test_operations import headers,ops_rows


def body(**changes):
    c=config(instructions='시스템 {{audience}}')
    return {'client_request_id':str(uuid4()),'config':c,'profile':{'schema_version':1,'system_prompt':c['instructions'],'developer_prompt':'검토 기준 {{rule}}','user_template':'질문 {{question}}','model_ref':'default_general','document_refs':[]},**changes}


def signed(client,login,f,actor='A-ADM',tenant='A'):
    return headers(f,tenant,login(client,actor)['csrf_token'])


def save(client,h,value):return client.post('/api/v1/admin/builder/assets',headers=h,json=value)
def read(client,h,aid,vid):return client.get('/api/v1/admin/builder/assets/'+aid+'/versions/'+vid,headers=h)
def append(client,h,aid,value,revision=1):return client.post('/api/v1/admin/builder/assets/'+aid+'/versions',headers=h,json={**value,'expected_revision':revision})
def clone(client,h,aid,vid,client_id=None):return client.post('/api/v1/admin/builder/assets/'+aid+'/clone',headers=h,json={'client_request_id':client_id or str(uuid4()),'source_version_id':vid})


def test_profiles_saved_atomically_immutable_and_replayed(client,login,db_fixture):
    f=db_fixture;h=signed(client,login,f);value=body();reply=save(client,h,value)
    assert reply.status_code==201
    r=reply.json()['data'];a=r['asset_id'];v=r['version_id']
    assert save(client,h,value).json()['data']=={**r,'replayed':True}
    changed={**value,'profile':{**value['profile'],'developer_prompt':'다른 기준'}}
    assert save(client,h,changed).status_code==409
    original=read(client,h,a,v).json()['data'];assert original['profile']==value['profile'] and original['profile_source']=='stored'
    assert original['profile_hash']==r['profile_hash'] and original['parent_version_id'] is None
    later=body();later['profile']['developer_prompt']='신규 기준'
    newer=append(client,h,a,later).json()['data'];assert newer['revision']==2
    assert read(client,h,a,v).json()['data']==original
    assert append(client,h,a,later).json()['data']['replayed']
    assert append(client,h,a,body()).status_code==409
    # Old non-structured API cannot drop system/developer/user fields.
    assert client.post('/api/v1/admin/assets/'+a+'/versions',headers=h,json={'client_request_id':str(uuid4()),'expected_revision':2,'config':config()}).json()['error']['code']=='BUILDER_PROFILE_REQUIRED'
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.builder_profiles').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM portal.asset_versions').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
        assert '시스템' not in json.dumps(conn.execute('SELECT action,revisions FROM ops.audit_events').fetchall())


def test_exact_version_clone_and_same_request_recovery(client,login,db_fixture):
    f=db_fixture;h=signed(client,login,f);value=body();r=save(client,h,value).json()['data']
    append(client,h,r['asset_id'],body())
    key=str(uuid4());reply=clone(client,h,r['asset_id'],r['version_id'],key);assert reply.status_code==201
    copied=reply.json()['data'];assert copied['asset_id']!=r['asset_id'] and copied['parent_version_id']==r['version_id']
    detail=read(client,h,copied['asset_id'],copied['version_id']).json()['data'];assert detail['config']==value['config'] and detail['profile']==value['profile']
    assert clone(client,h,r['asset_id'],r['version_id'],key).json()['data']['replayed']
    edited=append(client,h,copied['asset_id'],body()).json()['data']
    assert read(client,h,copied['asset_id'],edited['version_id']).json()['data']['parent_version_id']==r['version_id']
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.assets').fetchone()[0]==2
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='builder.clone'").fetchone()[0]==1


def test_historical_simple_version_is_derived_without_backfill(client,login,db_fixture):
    f=db_fixture;r=create(client,login,f).json()['data'];h=headers(f,csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token'])
    view=read(client,h,r['asset_id'],r['version_id']).json()['data'];assert view['profile_source']=='legacy-derived' and view['profile']['system_prompt']==config()['instructions']
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.builder_profiles').fetchone()[0]==0
    copied=clone(client,h,r['asset_id'],r['version_id']).json()['data']
    assert read(client,h,copied['asset_id'],copied['version_id']).json()['data']['profile_source']=='stored'


@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('P_READ_ONLY','A',403),('B-ADM','B',404),('B-ADM','A',403)])
def test_version_clone_scope(client,login,db_fixture,actor,tenant,status):
    f=db_fixture;h=signed(client,login,f);r=save(client,h,body()).json()['data'];other=signed(client,login,f,actor,tenant)
    assert read(client,other,r['asset_id'],r['version_id']).status_code==status
    assert clone(client,other,r['asset_id'],r['version_id']).status_code==status
    assert save(client,other,body()).status_code==(201 if actor=='B-ADM' and tenant=='B' else 403)


@pytest.mark.parametrize('case',['extra','model_url','system_mismatch','duplicate_refs','general_refs','invalid_template','many_variables','blank_developer'])
def test_schema_rejects_invalid_profile_without_partial_save(client,login,db_fixture,case):
    f=db_fixture;h=signed(client,login,f);value=body()
    if case=='extra':value['profile']['credential']='do-not-store'
    elif case=='model_url':value['profile']['model_ref']='http://arbitrary.invalid'
    elif case=='system_mismatch':value['profile']['system_prompt']='다른 지시문'
    elif case=='duplicate_refs':value['profile']['document_refs']=[{'document_id':str(uuid4()),'version_id':str(uuid4())}]*2
    elif case=='general_refs':value['profile']['document_refs']=[{'document_id':str(uuid4()),'version_id':str(uuid4())}]
    elif case=='invalid_template':value['profile']['user_template']='{{a.b}}'
    elif case=='many_variables':value['profile']['user_template']=''.join('{{x'+str(i)+'}}' for i in range(21))
    elif case=='blank_developer':value['profile']['developer_prompt']=' '
    assert save(client,h,value).status_code==422
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.assets').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM portal.builder_profiles').fetchone()[0]==0


def test_structured_preview_roles_hash_and_data_not_rebound(client,login,db_fixture):
    f=db_fixture;h=signed(client,login,f);r=save(client,h,body()).json()['data'];path='/api/v1/admin/builder/assets/'+r['asset_id']+'/versions/'+r['version_id']+'/preview'
    values={'audience':'{{secret}}','rule':'확인','question':'어떻게 하나요?'}
    reply=client.post(path,headers=h,json={'values':values});assert reply.status_code==200
    data=reply.json()['data'];assert [x['role'] for x in data['messages']]==['system','developer','user']
    assert data['messages'][0]['content']=='시스템 {{secret}}' and data['provider_called'] is False
    assert data['profile_hash']==r['profile_hash']
    assert client.post(path,headers=h,json={'values':values}).json()['data']['composition_hash']==data['composition_hash']
    assert client.post(path,headers=h,json={'values':{}}).status_code==422
    assert client.post(path,headers=headers(f),json={'values':values}).status_code==403


def test_partial_profile_failure_rolls_back_asset_version_and_audit(client,login,db_fixture):
    f=db_fixture;h=signed(client,login,f)
    with f.db.admin_connection() as conn:
        conn.execute("CREATE FUNCTION portal.dp11_fail() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'fixed fault';END;$$; CREATE TRIGGER dp11_fail BEFORE INSERT ON portal.builder_profiles FOR EACH ROW EXECUTE FUNCTION portal.dp11_fail()")
    tables=('portal.assets','portal.asset_versions','portal.builder_profiles','portal.builder_receipts','ops.audit_events')
    with f.db.admin_connection() as conn:before=[conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in tables]
    value=body();assert save(client,h,value).status_code==503
    with f.db.admin_connection() as conn:
        assert [conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in tables]==before
        conn.execute('DROP TRIGGER dp11_fail ON portal.builder_profiles')
    assert save(client,h,value).status_code==201


def test_concurrent_saves_and_replays(client,login,db_fixture):
    f=db_fixture;h=signed(client,login,f);value=body()
    with ThreadPoolExecutor(max_workers=2) as ex:rows=list(ex.map(lambda _:save(client,h,value),range(2)))
    assert sorted(x.status_code for x in rows)==[200,201]
    aid=rows[0].json()['data']['asset_id']
    with ThreadPoolExecutor(max_workers=2) as ex:rows=list(ex.map(lambda _:append(client,h,aid,body()),range(2)))
    assert sorted(x.status_code for x in rows)==[201,409]


def test_legacy_send_collision_cannot_add_profile_to_old_version(client,login,db_fixture):
    f=db_fixture;value=body();r=create(client,login,f,body={'client_request_id':value['client_request_id'],'config':value['config']}).json()['data'];h=headers(f,csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token'])
    assert save(client,h,value).status_code==409
    assert read(client,h,r['asset_id'],r['version_id']).json()['data']['profile_source']=='legacy-derived'


def test_document_scope_saved_and_revocation_blocks_clone_replay(client,login,ops_rows,auth_settings):
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from test_document_sharing import publish
    f=ops_rows;ctx=f.run(f.context('A-ADM','A'));repo=DocumentRepository(f.pool,SourceStorage(auth_settings.source_root),auth_settings.login_hmac_secret.get_secret_value())
    ids=f.run(publish(f,repo,ctx));value=body();value['config']['execution_kind']='rules_rag';value['profile']['model_ref']='default_rules_rag';value['profile']['document_refs']=[{k:ids[k] for k in ('document_id','version_id')}]
    h=signed(client,login,f);r=save(client,h,value).json()['data'];key=str(uuid4())
    assert clone(client,h,r['asset_id'],r['version_id'],key).status_code==201
    f.run(repo.delete(ctx,UUID(ids['document_id']),1))
    assert clone(client,h,r['asset_id'],r['version_id'],key).status_code==404
    assert save(client,h,value).status_code==404
    assert client.post('/api/v1/admin/builder/assets/'+r['asset_id']+'/versions/'+r['version_id']+'/preview',headers=h,json={'values':{'audience':'A','rule':'R','question':'Q'}}).status_code==404


def test_direct_web_cannot_call_private_registry_or_change_profile(db_fixture):
    f=db_fixture
    with f.role_connection('ai_web') as conn:
        assert not conn.execute("SELECT has_function_privilege(current_user,'security.asset_registry_v029(uuid,uuid,text,uuid,jsonb,uuid)','EXECUTE')").fetchone()[0]
        for table in ('portal.builder_profiles','portal.builder_receipts'):
            assert not conn.execute('SELECT has_table_privilege(current_user,%s,\'SELECT,INSERT,UPDATE,DELETE\')',(table,)).fetchone()[0]
    with f.role_connection('ai_web') as conn:
        with conn.transaction():
            for key,value in [('app.user_id',f.actor_ids['A-U1']),('app.session_id',f.state.session_ids['A-U1']),('app.tenant_id',f.tenant_ids['A']),('app.operations_scope','agent_admin')]:conn.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
            with pytest.raises(psycopg.Error) as error:conn.execute("SELECT security.builder_save(%s,%s,'create',NULL,%s,%s)",(f.state.session_ids['A-U1'],f.tenant_ids['A'],Jsonb(body()),uuid4()))
            assert error.value.sqlstate=='A0403'


@pytest.mark.parametrize('value',[True,2])
def test_schema_version_is_strict_and_fixed(client,login,db_fixture,value):
    f=db_fixture;h=signed(client,login,f);payload=body();payload['profile']['schema_version']=value
    assert save(client,h,payload).status_code==422


def test_direct_rpc_canonical_duplicate_document_refs_rejected(ops_rows,auth_settings):
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from test_document_sharing import publish
    f=ops_rows;ctx=f.run(f.context('A-ADM','A'));repo=DocumentRepository(f.pool,SourceStorage(auth_settings.source_root),auth_settings.login_hmac_secret.get_secret_value())
    ids=f.run(publish(f,repo,ctx));value=body();value['config']['execution_kind']='rules_rag';value['profile']['model_ref']='default_rules_rag'
    ref={k:ids[k] for k in ('document_id','version_id')};value['profile']['document_refs']=[ref,{k:str(v).upper() for k,v in ref.items()}]
    with f.role_connection('ai_web') as conn:
        with conn.transaction():
            for key,val in [('app.user_id',ctx.user_id),('app.session_id',ctx.session_id),('app.tenant_id',ctx.tenant_id)]:conn.execute('SELECT set_config(%s,%s,true)',(key,str(val)))
            with pytest.raises(psycopg.Error) as error:conn.execute("SELECT security.builder_save(%s,%s,'create',NULL,%s,%s)",(ctx.session_id,ctx.tenant_id,Jsonb(value),uuid4()))
            assert error.value.sqlstate=='A0422'
