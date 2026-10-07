"""Fail-closed local PDF isolation. Caller must authorize/admit before parsing."""
import json, os, subprocess, sys, unicodedata, threading
from pathlib import Path
from app.errors import AppError
from app.documents.storage import MAX_BYTES

ERRORS={"PDF_INVALID","PDF_ENCRYPTED","PDF_PAGE_LIMIT","PDF_ACTIVE_CONTENT","PDF_OCR_UNSUPPORTED","PDF_STREAM_LIMIT","PDF_TEXT_LIMIT"}
def sandbox_command(worker):
 if sys.platform!="darwin" or not Path("/usr/bin/sandbox-exec").is_file():raise AppError("PDF_PARSER_UNAVAILABLE",503)
 # Allow only Python runtime and this worker; never project configuration/source stores.
 runtime=str(Path(sys.prefix).resolve())
 permitted=" ".join('(subpath '+json.dumps(x,ensure_ascii=False)+')' for x in {runtime,unicodedata.normalize("NFD",runtime)})
 scripts=" ".join('(literal '+json.dumps(x,ensure_ascii=False)+')' for x in {str(worker.resolve()),unicodedata.normalize("NFD",str(worker.resolve()))})
 profile='(version 1)(deny default)(allow process-exec)(allow sysctl-read)(allow mach-lookup)(allow file-read*)(deny file-read-data (require-all (subpath "/Users") (require-not (require-any '+permitted+' '+scripts+'))))(deny file-read-data (subpath "/private/tmp"))(deny network*)(deny file-write*)(deny process-fork)'

 return ["/usr/bin/sandbox-exec","-p",profile,sys.executable,"-I","-B",str(worker)]
def run_isolated(command, content):
 # macOS rejects the proposed RLIMIT_AS. Enforce measured resident memory
 # in the trusted parent instead, retaining the independent CPU/wall bounds.
 process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={"LANG":"C.UTF-8","PATH":"/usr/bin:/bin"},cwd="/private/tmp")
 stop=threading.Event();exceeded=threading.Event();unavailable=threading.Event()
 def watch():
  while not stop.wait(.05) and process.poll() is None:
   try:
    info=subprocess.run(["/bin/ps","-o","rss=","-p",str(process.pid)],capture_output=True,timeout=1,check=False)
    if info.returncode and process.poll() is not None:return
    rss=int(info.stdout.strip())
    if rss>512*1024:exceeded.set();process.kill();return
   except (OSError,ValueError,subprocess.TimeoutExpired):
    if process.poll() is not None:return
    unavailable.set();process.kill();return
 thread=threading.Thread(target=watch,daemon=True);thread.start()
 try:
  try:output,_=process.communicate(content,timeout=5)
  except subprocess.TimeoutExpired:
   process.kill();process.communicate();raise AppError("PDF_RESOURCE_LIMIT",422) from None
 finally:stop.set();thread.join(timeout=2)
 if unavailable.is_set():raise AppError("PDF_PARSER_UNAVAILABLE",503)
 if exceeded.is_set():raise AppError("PDF_RESOURCE_LIMIT",422)
 return subprocess.CompletedProcess(command,process.returncode,output)

def extract_pdf(content):
 if type(content) is not bytes or not 1<=len(content)<=MAX_BYTES or not content.startswith(b"%PDF-"):raise AppError("PDF_INVALID",422)
 worker=Path(__file__).with_name("pdf_worker.py")
 try:
  result=run_isolated(sandbox_command(worker),content)
 except subprocess.TimeoutExpired:raise AppError("PDF_RESOURCE_LIMIT",422) from None
 except OSError:raise AppError("PDF_PARSER_UNAVAILABLE",503) from None
 if result.returncode!=0:
  raise AppError("PDF_RESOURCE_LIMIT" if result.returncode<0 else "PDF_PARSER_UNAVAILABLE",422 if result.returncode<0 else 503)
 if len(result.stdout)>1048576:raise AppError("PDF_RESOURCE_LIMIT",422)
 try:
  value=json.loads(result.stdout)
  if set(value)=={"error"} and value["error"] in ERRORS:raise AppError(value["error"],422)
  if set(value)!={"text","pages","parser_version"} or value["parser_version"]!="pypdf-6.19.0" or not isinstance(value["text"],str) or not 1<=len(value["text"])<=40000 or len(value["text"].encode())>MAX_BYTES or not 1<=len(value["pages"])<=20:raise ValueError()
  previous=-2
  for n,page in enumerate(value["pages"],1):
   if set(page)!={"page","start","end"} or any(type(v) is not int for v in page.values()) or page["page"]!=n or page["start"]!=previous+2 or not page["start"]<page["end"]<=len(value["text"]):raise ValueError()
   previous=page["end"]
  if previous!=len(value["text"]):raise ValueError()
  return value
 except (ValueError,KeyError,TypeError):raise AppError("PDF_PARSER_UNAVAILABLE",503) from None
