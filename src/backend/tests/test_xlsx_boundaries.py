import io,zipfile,json,subprocess
from pathlib import Path
import pytest
from xlsx_support import xlsx_bytes,cell,S
from app.documents.xlsx import extract_xlsx
from app.documents.xlsx_locations import validate_xlsx_locations
from app.errors import AppError

@pytest.mark.parametrize('case',['entries','nodes','units','text','utf16'])
def test_bounded_document_limits(case):
 if case=='entries':
  stream=io.BytesIO(xlsx_bytes())
  with zipfile.ZipFile(stream,'a') as z:
   for n in range(201):z.writestr('unexpected'+str(n),'x')
  raw=stream.getvalue();code='XLSX_ZIP_LIMIT'
 elif case=='nodes':raw=xlsx_bytes(extra={'xl/styles.xml':'<root>'+''.join('<node n="'+str(n)+'"/>' for n in range(20001))+'</root>'});code='XLSX_XML_LIMIT'
 elif case=='units':raw=xlsx_bytes([('규정',''.join(cell('x','A'+str(i)) for i in range(1,2002)))]);code='XLSX_TEXT_LIMIT'
 elif case=='text':raw=xlsx_bytes([('규정',cell('x'*40001))],compression=zipfile.ZIP_STORED);code='XLSX_TEXT_LIMIT'
 else:
  xml=('<workbook xmlns="'+S+'"/>').encode('utf-16')
  raw=xlsx_bytes(changes={'xl/workbook.xml':xml});code='XLSX_INVALID'
 with pytest.raises(AppError) as e:extract_xlsx(raw)
 assert e.value.code==code

@pytest.mark.parametrize('change',[{'start':9},{'end':17},{'sheet_index':True},{'cell':'XFE1'},{'extra':1}])
def test_invalid_locator_fails_closed(change):
 locs=[{'kind':'sheet','sheet_index':1,'sheet_name':'규정','start':0,'end':6},{'kind':'cell','sheet_index':1,'sheet_name':'규정','cell':'A1','start':8,'end':18}];locs[1].update(change)
 with pytest.raises(ValueError):validate_xlsx_locations(locs,18)

@pytest.mark.parametrize('source_code,expected,status',[('PDF_RESOURCE_LIMIT','XLSX_RESOURCE_LIMIT',422),('PDF_PARSER_UNAVAILABLE','XLSX_PARSER_UNAVAILABLE',503)])
def test_runner_failure_is_safe_xlsx_error(monkeypatch,source_code,expected,status):
 import app.documents.xlsx as module
 def fail(*a):raise AppError(source_code,503)
 monkeypatch.setattr(module,'run_isolated',fail)
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes())
 assert e.value.code==expected and e.value.status==status

def test_xlsx_worker_sandbox_denies_private_data_write_network_child():
 import app.documents.pdf as module
 sentinel=Path(__file__).resolve().parents[1]/'.runtime/xlsx-isolation-sentinel'
 sentinel.write_text('synthetic');sentinel.chmod(0o600)
 try:
  code="""import json,os,socket,subprocess
checks={}
try:open(%r).read();checks['read']=False
except PermissionError:checks['read']=True
try:open('/private/tmp/xlsx-denied-write','w').write('synthetic');checks['write']=False
except PermissionError:checks['write']=True
try:socket.create_connection(('127.0.0.1',55432),timeout=.2);checks['network']=False
except OSError:checks['network']=True
try:subprocess.run(['/bin/echo','synthetic'],check=True);checks['child']=False
except (OSError,subprocess.SubprocessError):checks['child']=True
checks['no_secrets']=not any(k in os.environ for k in ['OPENAI_API_KEY','PGPASSWORD','LOGIN_HMAC_SECRET'])
print(json.dumps(checks))
""" % str(sentinel)
  cmd=module.sandbox_command(Path(__file__).resolve().parents[1]/'app/documents/xlsx_worker.py');cmd[-1:]=['-c',code]
  result=module.run_isolated(cmd,b'');assert result.returncode==0
  checks=json.loads(result.stdout);assert len(checks)==5 and all(checks.values())
 finally:sentinel.unlink(missing_ok=True)


def test_xml_node_count_is_aggregate_across_parts():
 content='<root>'+''.join('<node n="'+str(n)+'"/>' for n in range(7000))+'</root>'
 raw=xlsx_bytes(extra={name:content for name in ['xl/styles.xml','xl/sharedStrings.xml','xl/theme/theme1.xml']})
 with pytest.raises(AppError) as e:extract_xlsx(raw)
 assert e.value.code=='XLSX_XML_LIMIT'
