import io
import pytest
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,DictionaryObject,ArrayObject,TextStringObject,DecodedStreamObject
from app.documents.pdf import extract_pdf
from app.errors import AppError
from pdf_support import pdf_bytes

def rewrite(raw,mutate):
 writer=PdfWriter(clone_from=PdfReader(io.BytesIO(raw)))
 mutate(writer);output=io.BytesIO();writer.write(output);return output.getvalue()

@pytest.mark.parametrize('kind',['attachment','form','uri','automatic_action'])
def test_active_features_fail_before_extraction(kind):
 def mutate(writer):
  if kind=='attachment':writer.add_attachment('synthetic.txt',b'synthetic')
  elif kind=='form':writer.root_object[NameObject('/AcroForm')]=DictionaryObject()
  elif kind=='automatic_action':writer.root_object[NameObject('/AA')]=DictionaryObject()
  else:
   action=DictionaryObject({NameObject('/S'):NameObject('/URI'),NameObject('/URI'):TextStringObject('https://example.invalid/')})
   writer.pages[0][NameObject('/Annots')]=ArrayObject([DictionaryObject({NameObject('/Subtype'):NameObject('/Link'),NameObject('/A'):action})])
 raw=rewrite(pdf_bytes(['safe']),mutate)
 with pytest.raises(AppError) as e:extract_pdf(raw)
 assert e.value.code=='PDF_ACTIVE_CONTENT'

def test_exact_twenty_pages_supported():
 value=extract_pdf(pdf_bytes(['합성 문서']*20));assert len(value['pages'])==20

def test_compressed_text_expansion_rejected():
 raw=rewrite(pdf_bytes(['x'*40001]),lambda writer:writer.pages[0].compress_content_streams())
 assert len(raw)<131072
 with pytest.raises(AppError) as e:extract_pdf(raw)
 assert e.value.code in ('PDF_TEXT_LIMIT','PDF_RESOURCE_LIMIT')

def test_compressed_stream_expansion_rejected():
 def mutate(writer):
  stream=DecodedStreamObject();stream.set_data(b' '*4194305)
  writer.pages[0][NameObject('/Contents')]=writer._add_object(stream.flate_encode())
 raw=rewrite(pdf_bytes(['safe']),mutate);assert len(raw)<131072
 with pytest.raises(AppError) as e:extract_pdf(raw)
 assert e.value.status==422 and e.value.code in ('PDF_INVALID','PDF_STREAM_LIMIT','PDF_RESOURCE_LIMIT')

def test_mixed_text_and_blank_pages_rejected():
 with pytest.raises(AppError) as e:extract_pdf(pdf_bytes(['safe','']))
 assert e.value.code=='PDF_OCR_UNSUPPORTED'
