"""Public deployment config only; no credentials, no fallback to another environment."""
import json
from pathlib import Path
from urllib.parse import urlsplit
ENVIRONMENTS=('local','dev','tb','prd')
CONFIG_ROOT=Path(__file__).resolve().parents[3]/'config/environments'
class ConfigurationError(ValueError):pass

def validate_environment(data,expected,*,ready=True):
 def require(condition):
  if not condition:raise ConfigurationError('PORTAL_CONFIGURATION_INVALID')
 require(type(data) is dict and set(data)=={'version','environment','configured','bind_host','session_mode','user','admin','api'})
 require(data['version']==1 and type(data['version']) is int and data['environment']==expected and expected in ENVIRONMENTS)
 require(type(data['configured']) is bool and data['bind_host']=='127.0.0.1')
 require(data['session_mode']==('shared-host-development' if expected=='local' else 'site-sessions-required'))
 ports=[]
 for key,entry in [('user','/user/home'),('admin','/manage/admin'),('api','/api/v1')]:
  item=data[key];require(type(item) is dict and set(item)=={'origin','port','entry'} and item['entry']==entry)
  port=item['port'];require(type(port) is int and 1<=port<=65535);ports.append(port)
  origin=item['origin']
  if origin is None:require(not data['configured'] and expected!='local');continue
  require(type(origin) is str)
  try:
   url=urlsplit(origin);effective_port=url.port or (443 if url.scheme=='https' else 80)
  except ValueError:raise ConfigurationError('PORTAL_CONFIGURATION_INVALID') from None
  require(url.scheme==('http' if expected=='local' else 'https') and bool(url.hostname) and not url.username and not url.password and not url.path and not url.query and not url.fragment and effective_port==port)
  host=('['+url.hostname+']') if url.hostname and ':' in url.hostname else url.hostname
  canonical=url.scheme+'://'+str(host)+((':'+str(effective_port)) if effective_port!=(443 if url.scheme=='https' else 80) else '')
  require(origin.isascii() and origin==canonical and not any(c.isspace() for c in origin) and '*' not in origin)
  if expected=='local':require(url.hostname=='127.0.0.1')
 require(len(set(ports))==3 and (expected!='local' or data['configured']))
 if ready and not data['configured']:raise ConfigurationError('PORTAL_ENVIRONMENT_NOT_CONFIGURED')
 return data

def load_environment(environment='local',*,ready=True):
 if environment not in ENVIRONMENTS:raise ConfigurationError('PORTAL_ENVIRONMENT_UNKNOWN')
 try:data=json.loads((CONFIG_ROOT/(environment+'.json')).read_text())
 except (OSError,ValueError):raise ConfigurationError('PORTAL_CONFIGURATION_INVALID') from None
 return validate_environment(data,environment,ready=ready)
