from copy import deepcopy
import pytest
from app.environment import load_environment,validate_environment,ConfigurationError
from app.config import Settings

@pytest.mark.parametrize('name',['local','dev','tb','prd'])
def test_environment_schema_and_readiness(name):
    assert load_environment(name,ready=False)['environment']==name
    if name!='local':
        with pytest.raises(ConfigurationError,match='NOT_CONFIGURED'):load_environment(name)

def test_environment_does_not_fallback():
    with pytest.raises(ConfigurationError,match='UNKNOWN'):load_environment('../prd')

@pytest.mark.parametrize('path,value',[('secret','do-not-print'),('user.port',0),('user.port',True),('admin.port',5173),('user.origin','http://127.0.0.1:9999'),('user.origin','http://localhost:5173'),('user.origin','http://127.0.0.1:5173/'),('user.origin','http://key:secret@127.0.0.1:5173'),('user.origin','http://127.0.0.1:5173?x=y'),('user.origin','http://127.0.0.1:5173#x'),('user.origin','*'),('environment','prd'),('configured',False)])
def test_invalid_public_config_has_safe_error(path,value):
    data=deepcopy(load_environment());parts=path.split('.');target=data if len(parts)==1 else data[parts[0]];target[parts[-1]]=value
    with pytest.raises(ConfigurationError) as result:validate_environment(data,'local')
    assert str(result.value)=='PORTAL_CONFIGURATION_INVALID'

def test_remote_https_ip_can_be_configured_but_runtime_is_not_fixture(monkeypatch):
    data=load_environment('tb',ready=False);data['configured']=True
    for key in ['user','admin','api']:data[key]['origin']='https://192.0.2.10:'+str(data[key]['port'])
    assert validate_environment(data,'tb')['configured']
    data['user']['origin']='http://192.0.2.10:5173'
    with pytest.raises(ConfigurationError):validate_environment(data,'tb')
    monkeypatch.setenv('AI_ENVIRONMENT','prd')
    with pytest.raises(ConfigurationError,match='NOT_CONFIGURED'):Settings.from_environment()

def test_local_runtime_origins_are_exact_from_file(monkeypatch):
    monkeypatch.setenv('AI_ENVIRONMENT','local');value=Settings.from_environment()
    assert value.trusted_origins==('http://127.0.0.1:5173','http://127.0.0.1:5174')
    assert value.session_cookie_name=='ai_session_dev'

@pytest.mark.parametrize('origins',[('http://evil.invalid:5174',),('http://127.0.0.1:5173','http://127.0.0.1:5173'),('http://127.0.0.1:5173','http://127.0.0.1:5174/path')])
def test_invalid_origin_binding_is_rejected(origins):
    with pytest.raises(ValueError):Settings(portal_origins=origins)

def test_admin_port_accepts_registered_origin_but_not_missing_csrf(client,db_fixture,login):
    settings=Settings(portal_origins=('http://127.0.0.1:5173','http://127.0.0.1:5174'));client.app.state.settings=settings
    csrf=login(client,'A-U1')['csrf_token']
    for origin in ['http://127.0.0.1:5175','http://localhost:5174','http://evil.invalid:5174']:
        assert client.post('/api/v1/auth/logout',headers={'Origin':origin,'X-Requested-With':'ai-portal','X-CSRF-Token':csrf}).status_code==403
    assert client.post('/api/v1/auth/logout',headers=[('Origin','http://127.0.0.1:5173'),('Origin','http://127.0.0.1:5174'),('X-Requested-With','ai-portal'),('X-CSRF-Token',csrf)]).status_code==403
    assert client.post('/api/v1/auth/logout',headers={'Origin':'http://127.0.0.1:5174','X-Requested-With':'ai-portal'}).status_code==403
    assert client.get('/api/v1/auth/me').status_code==200
    assert client.post('/api/v1/auth/logout',headers={'Origin':'http://127.0.0.1:5174','X-Requested-With':'ai-portal','X-CSRF-Token':csrf}).status_code==200
