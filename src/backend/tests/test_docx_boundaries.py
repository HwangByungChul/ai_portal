import io,zipfile,json,subprocess
from pathlib import Path
import pytest
from docx_support import docx_bytes,p,W
from app.documents.docx import extract_docx
from app.documents.docx_locations import validate_docx_locations
from app.errors import AppError

@pytest.mark.parametrize('case',['entries','nodes','units','text','utf16'])
def test_bounded_document_limits(case):
 if case=='entries':
  stream=io.BytesIO(docx_bytes())
  with zipfile.ZipFile(stream,'a') as z:
   for n in range(201):z.writestr('unexpected'+str(n),'x')
  raw=stream.getvalue();code='DOCX_ZIP_LIMIT'
 elif case=='nodes':raw=docx_bytes(p('safe')+'<w:pPr>'+''.join('<w:b w:val="'+str(n)+'"/>' for n in range(20001))+'</w:pPr>');code='DOCX_XML_LIMIT'
 elif case=='units':raw=docx_bytes(p('x')*2001,compression=zipfile.ZIP_STORED);code='DOCX_TEXT_LIMIT'
 elif case=='text':raw=docx_bytes(p('x'*40001),compression=zipfile.ZIP_STORED);code='DOCX_TEXT_LIMIT'
 else:
  xml=(f'<w:document xmlns:w="{W}"><w:body>'+p('safe')+'</w:body></w:document>').encode('utf-16')
  raw=docx_bytes(changes={'word/document.xml':xml});code='DOCX_INVALID'
 with pytest.raises(AppError) as e:extract_docx(raw)
 assert e.value.code==code

@pytest.mark.parametrize('change',[{'start':1},{'end':2},{'paragraph':True},{'paragraph':0},{'extra':1}])
def test_invalid_locator_fails_closed(change):
 loc={'kind':'paragraph','paragraph':1,'start':0,'end':4};loc.update(change)
 with pytest.raises(ValueError):validate_docx_locations([loc],4)

@pytest.mark.parametrize('source_code,expected,status',[('PDF_RESOURCE_LIMIT','DOCX_RESOURCE_LIMIT',422),('PDF_PARSER_UNAVAILABLE','DOCX_PARSER_UNAVAILABLE',503)])
def test_runner_failure_is_safe_docx_error(monkeypatch,source_code,expected,status):
 import app.documents.docx as module
 def fail(*a):raise AppError(source_code,503)
 monkeypatch.setattr(module,'run_isolated',fail)
 with pytest.raises(AppError) as e:extract_docx(docx_bytes())
 assert e.value.code==expected and e.value.status==status

def test_docx_worker_sandbox_denies_private_data_write_network_child():
 import app.documents.pdf as module
 sentinel=Path(__file__).resolve().parents[1]/'.runtime/docx-isolation-sentinel'
 sentinel.write_text('synthetic');sentinel.chmod(0o600)
 try:
  code="""import json,os,socket,subprocess
checks={}
try:open(%r).read();checks['read']=False
except PermissionError:checks['read']=True
try:open('/private/tmp/docx-denied-write','w').write('synthetic');checks['write']=False
except PermissionError:checks['write']=True
try:socket.create_connection(('127.0.0.1',55432),timeout=.2);checks['network']=False
except OSError:checks['network']=True
try:subprocess.run(['/bin/echo','synthetic'],check=True);checks['child']=False
except (OSError,subprocess.SubprocessError):checks['child']=True
checks['no_secrets']=not any(k in os.environ for k in ['OPENAI_API_KEY','PGPASSWORD','LOGIN_HMAC_SECRET'])
print(json.dumps(checks))
""" % str(sentinel)
  cmd=module.sandbox_command(Path(__file__).resolve().parents[1]/'app/documents/docx_worker.py');cmd[-1:]=['-c',code]
  result=module.run_isolated(cmd,b'');assert result.returncode==0
  checks=json.loads(result.stdout);assert len(checks)==5 and all(checks.values())
 finally:sentinel.unlink(missing_ok=True)


def test_xml_node_count_is_aggregate_across_parts():
 content='<root>'+''.join('<node n="'+str(n)+'"/>' for n in range(7000))+'</root>'
 raw=docx_bytes(extra={name:content for name in ['word/settings.xml','word/styles.xml','word/webSettings.xml']})
 with pytest.raises(AppError) as e:extract_docx(raw)
 assert e.value.code=='DOCX_XML_LIMIT'
