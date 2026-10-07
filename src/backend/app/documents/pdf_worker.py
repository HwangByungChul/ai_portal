"""Isolated subprocess: stdin PDF -> bounded JSON; no app imports or credentials."""
import io, json, logging, resource, sys
resource.setrlimit(resource.RLIMIT_CPU,(2,2))

resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
from pypdf import PdfReader, apply_configuration
from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject, StreamObject
logging.disable(logging.CRITICAL)

DANGEROUS={"/JavaScript","/JS","/OpenAction","/AA","/EmbeddedFiles","/EF","/Filespec","/AcroForm","/XFA","/Launch","/URI","/GoToR","/GoToE","/RichMedia","/Movie","/Sound","/SubmitForm","/ImportData","/Link"}
def extract(raw):
 if not raw.startswith(b"%PDF-") or not 1<=len(raw)<=131072:raise ValueError("PDF_INVALID")
 with apply_configuration(maximum_declared_stream_length=4194304,zlib_maximum_output_length=4194304,array_based_stream_maximum_output_length=4194304,lzw_maximum_output_length=4194304,run_length_maximum_output_length=4194304,page_tree_maximum_entries=100,page_tree_maximum_depth=20,xform_maximum_invocations_per_extraction=100):
  reader=PdfReader(io.BytesIO(raw),strict=True)
  if reader.is_encrypted:raise ValueError("PDF_ENCRYPTED")
  if not 1<=len(reader.pages)<=20:raise ValueError("PDF_PAGE_LIMIT")
  # Walk reachable objects without executing or fetching any action/resource.
  seen=set();budget=20000
  def visit(obj,depth=0):
   nonlocal budget
   budget-=1
   if budget<0 or depth>50:raise ValueError("PDF_INVALID")
   if isinstance(obj,IndirectObject):
    key=(obj.idnum,obj.generation)
    if key in seen:return
    seen.add(key);obj=obj.get_object()
   if isinstance(obj,DictionaryObject):
    if DANGEROUS.intersection(map(str,obj.keys())) or str(obj.get("/S","")) in DANGEROUS or str(obj.get("/Subtype","")) in DANGEROUS or str(obj.get("/Type","")) in DANGEROUS:raise ValueError("PDF_ACTIVE_CONTENT")
    for value in obj.values():visit(value,depth+1)
   elif isinstance(obj,ArrayObject):
    for value in obj:visit(value,depth+1)
  visit(reader.trailer)
  pages=[];parts=[];offset=0;stream_total=0
  for number,page in enumerate(reader.pages,1):
   streams=page.get("/Contents")
   if streams is not None:
    streams=streams.get_object()
    for stream in streams if isinstance(streams,ArrayObject) else [streams]:
     stream_total+=len(stream.get_object().get_data())
     if stream_total>4194304:raise ValueError("PDF_STREAM_LIMIT")
   text=page.extract_text()
   if not text or not text.strip():raise ValueError("PDF_OCR_UNSUPPORTED")
   if "\x00" in text:raise ValueError("PDF_INVALID")
   if parts:parts.append("\n\n");offset+=2
   start=offset;parts.append(text);offset+=len(text)
   if offset>40000:raise ValueError("PDF_TEXT_LIMIT")
   pages.append({"page":number,"start":start,"end":offset})
  text="".join(parts)
  if len(text.encode())>131072:raise ValueError("PDF_TEXT_LIMIT")
  return {"text":text,"pages":pages,"parser_version":"pypdf-6.19.0"}
try:
 result=extract(sys.stdin.buffer.read(131073))
except ValueError as e:
 code=str(e)
 result={"error":code if code in {"PDF_INVALID","PDF_ENCRYPTED","PDF_PAGE_LIMIT","PDF_ACTIVE_CONTENT","PDF_OCR_UNSUPPORTED","PDF_STREAM_LIMIT","PDF_TEXT_LIMIT"} else "PDF_INVALID"}
except Exception:result={"error":"PDF_INVALID"}
sys.stdout.write(json.dumps(result,ensure_ascii=True,separators=(",",":")))
