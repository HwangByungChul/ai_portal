import pytest
from app.documents.pdf import extract_pdf
from app.errors import AppError
from pdf_support import pdf_bytes

def test_unicode_pages_and_offsets():
 texts=['여신심사의 담당 부서는 가상 심사팀이다.','합성 문서 두 번째 페이지.']
 value=extract_pdf(pdf_bytes(texts))
 assert value['text']=="\n\n".join(texts)
 for page,text in zip(value['pages'],texts):assert value['text'][page['start']:page['end']]==text

@pytest.mark.parametrize('raw,code',[(b'garbage','PDF_INVALID'),(b'%PDF-1.7 broken','PDF_INVALID'),(pdf_bytes(['safe'],encrypt=True),'PDF_ENCRYPTED'),(pdf_bytes(['safe'],active=True),'PDF_ACTIVE_CONTENT'),(pdf_bytes(['']),'PDF_OCR_UNSUPPORTED'),(pdf_bytes(['safe']*21),'PDF_PAGE_LIMIT')])
def test_unsafe_pdf_rejected(raw,code):
 with pytest.raises(AppError) as e:extract_pdf(raw)
 assert e.value.code==code

def test_isolation_unavailable_fails_closed(monkeypatch):
 import app.documents.pdf as module
 monkeypatch.setattr(module.sys,'platform','other')
 with pytest.raises(AppError) as e:extract_pdf(pdf_bytes(['safe']))
 assert e.value.code=='PDF_PARSER_UNAVAILABLE'

def test_memory_guard_terminates_on_measured_limit(monkeypatch):
 import app.documents.pdf as module
 import sys, subprocess
 monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a,0,b'524289\n'))
 with pytest.raises(AppError) as e:module.run_isolated([sys.executable,'-I','-c','import time;time.sleep(10)'],b'')
 assert e.value.code=='PDF_RESOURCE_LIMIT'

def test_memory_monitor_failure_terminates_closed(monkeypatch):
 import app.documents.pdf as module
 import sys
 def broken(*a,**k):raise OSError()
 monkeypatch.setattr(module.subprocess,'run',broken)
 with pytest.raises(AppError) as e:module.run_isolated([sys.executable,'-I','-c','import time;time.sleep(10)'],b'')
 assert e.value.code=='PDF_PARSER_UNAVAILABLE'

def test_actual_sandbox_denies_project_read_write_network_and_child(tmp_path,monkeypatch):
 import app.documents.pdf as module
 import json,os
 from pathlib import Path
 sentinel=Path(__file__).resolve().parents[1]/'.runtime/dp06-isolation-sentinel'
 sentinel.write_text('synthetic sentinel');sentinel.chmod(0o600)
 try:
  code="""import json,os,socket,subprocess
checks={}
try:open(%r).read();checks['project_read']=False
except PermissionError:checks['project_read']=True
try:open('/private/tmp/dp06-denied-write','w').write('synthetic');checks['file_write']=False
except PermissionError:checks['file_write']=True
try:socket.create_connection(('127.0.0.1',55432),timeout=.2);checks['network']=False
except OSError:checks['network']=True
try:subprocess.run(['/bin/echo','synthetic'],check=True);checks['child']=False
except (OSError,subprocess.SubprocessError):checks['child']=True
checks['credentials_absent']=not any(k in os.environ for k in ['OPENAI_API_KEY','PGPASSWORD','LOGIN_HMAC_SECRET'])
print(json.dumps(checks))
""" % str(sentinel)
  command=module.sandbox_command(Path(module.__file__).with_name('pdf_worker.py'));command[-1:]=['-c',code]
  result=module.run_isolated(command,b'');assert result.returncode==0
  checks=json.loads(result.stdout);assert all(checks.values()) and len(checks)==5
 finally:sentinel.unlink(missing_ok=True)
