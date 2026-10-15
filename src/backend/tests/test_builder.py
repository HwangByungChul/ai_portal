from uuid import uuid4
import pytest
from app.builder.templates import compile_template
from app.errors import AppError
from test_assets import create, config
from test_operations import headers, ops_rows


def test_binding_is_single_pass_and_deterministic():
    assert compile_template('대상 {{audience}} / {{audience}}', {'audience': '{{secret}}'}) == (['audience'], '대상 {{secret}} / {{secret}}')
    assert compile_template('{"형식": "JSON"}', {}) == ([], '{"형식": "JSON"}')


@pytest.mark.parametrize('template,values', [
    ('{{ name }}', {'name': 'a'}), ('{{name', {'name': 'a'}), ('name}}', {}),
    ('{{a.b}}', {}), ('{{x}}', {}), ('{{x}}', {'x': 'a', 'extra': 'b'}),
    ('{{x}}', {'x': ' '}), ('{{x}}', {'x': 1}), ('{{x}}', {'x': 'a'*2001}),
    ('{{x}}', {'x': '\x00'}), ('{{x}}', {'x': '\ud800'}),
    ('{{x}}'*5, {'x': 'a'*2000}), ('a'*2001, {}),
    (''.join('{{v'+str(i)+'}}' for i in range(21)), {f'v{i}':'x' for i in range(21)})])
def test_template_rejects_invalid_or_unbounded_inputs(template, values):
    with pytest.raises(AppError) as problem:
        compile_template(template, values)
    assert problem.value.code == 'BUILDER_TEMPLATE_INVALID'


def preview(client, f, asset, values=None, revision=1, refs=None):
    csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token']
    return client.post('/api/v1/admin/builder/assets/'+asset+'/preview', headers=headers(f,csrf=csrf),
        json={'expected_revision':revision, 'values':values or {}, 'document_refs':refs or []})


def test_saved_draft_preview_no_provider_or_database_mutations(client, login, db_fixture):
    f=db_fixture
    aid=create(client,login,f,body={'client_request_id':str(uuid4()),'config':config(instructions='설명 {{audience}}')}).json()['data']['asset_id']
    def counts():
        with f.db.admin_connection() as conn:
            return [conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('portal.assets','portal.asset_versions','portal.runs','ops.call_attempts','ops.audit_events')]
    before=counts()
    reply=preview(client,f,aid,{'audience':'<script>{{secret}}</script>'})
    assert reply.status_code==200
    data=reply.json()['data']
    assert data['instructions']=='설명 <script>{{secret}}</script>' and data['variables']==['audience']
    assert data['kind']=='composition_preview' and data['provider_called'] is False and data['sources']==[]
    assert len(data['composition_hash'])==64
    assert preview(client,f,aid,{'audience':'<script>{{secret}}</script>'}).json()['data']['composition_hash']==data['composition_hash']
    assert preview(client,f,aid,{'audience':'다름'}).json()['data']['composition_hash']!=data['composition_hash']
    assert preview(client,f,aid,revision=2).status_code==409
    assert preview(client,f,aid).status_code==422
    assert counts()==before


@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('P_READ_ONLY','A',403),('B-ADM','B',404)])
def test_preview_scope(client,login,db_fixture,actor,tenant,status):
    f=db_fixture;aid=create(client,login,f).json()['data']['asset_id'];csrf=login(client,actor)['csrf_token']
    reply=client.post('/api/v1/admin/builder/assets/'+aid+'/preview',headers=headers(f,tenant,csrf),json={'expected_revision':1,'values':{}})
    assert reply.status_code==status and 'private-asset-instruction-marker' not in reply.text


def test_preview_csrf_legacy_extra_query_and_body_size(client,login,db_fixture):
    f=db_fixture;aid=create(client,login,f).json()['data']['asset_id'];path='/api/v1/admin/builder/assets/'+aid+'/preview'
    body={'expected_revision':1,'values':{}}
    assert client.post(path,headers=headers(f),json=body).status_code==403
    csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token'];h=headers(f,csrf=csrf)
    assert client.post(path+'?unexpected=1',headers=h,json=body).status_code==422
    assert client.post(path,headers=h,json={**body,'instructions':'bypass'}).status_code==422
    assert client.post(path,headers=h,json={**body,'values':{'x':'a'*33000}}).status_code==413
    legacy=next(x for x in client.get('/api/v1/admin/assets',headers=h).json()['data']['items'] if x['state']=='legacy')
    assert preview(client,f,legacy['asset_id']).status_code==409


def test_rag_refs_are_explicit_and_private_unpublished_documents_hidden(client,login,db_fixture):
    f=db_fixture
    aid=create(client,login,f,body={'client_request_id':str(uuid4()),'config':config(execution_kind='rules_rag')}).json()['data']['asset_id']
    assert preview(client,f,aid).json()['data']['sources']==[]
    assert preview(client,f,aid,refs=[{'document_id':str(uuid4()),'version_id':str(uuid4())}]).status_code==404
    general=create(client,login,f).json()['data']['asset_id']
    assert preview(client,f,general,refs=[{'document_id':str(uuid4()),'version_id':str(uuid4())}]).status_code==422


def test_published_rag_scope_then_revoked_is_hidden(client,login,ops_rows,auth_settings):
    from uuid import UUID
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from test_document_sharing import publish
    f=ops_rows
    repo=DocumentRepository(f.pool,SourceStorage(auth_settings.source_root),auth_settings.login_hmac_secret.get_secret_value())
    ctx=f.run(f.context('A-ADM','A'))
    ids=f.run(publish(f,repo,ctx))
    aid=create(client,login,f,body={'client_request_id':str(uuid4()),'config':config(execution_kind='rules_rag')}).json()['data']['asset_id']
    refs=[{k:ids[k] for k in ('document_id','version_id')}]
    reply=preview(client,f,aid,refs=refs)
    assert reply.status_code==200 and len(reply.json()['data']['sources'])==1
    assert preview(client,f,aid,refs=refs+refs).status_code==422
    f.run(repo.delete(ctx,UUID(ids['document_id']),1))
    assert preview(client,f,aid,refs=refs).status_code==404


def test_current_manager_role_revocation_blocks_preview(client,login,db_fixture):
    f=db_fixture;aid=create(client,login,f).json()['data']['asset_id']
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE security.memberships SET role='USER',revision=revision+1 WHERE tenant_id=%s AND user_id=%s",(f.tenant_ids['A'],f.actor_ids['A-ADM']))
    assert preview(client,f,aid).status_code==403
