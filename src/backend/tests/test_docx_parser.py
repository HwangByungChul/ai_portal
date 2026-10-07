import io,zipfile,stat,json,sys
from pathlib import Path
import pytest
from docx_support import docx_bytes,p,table,W,R,T,MAIN
from app.documents.docx import extract_docx
from app.errors import AppError

def test_document_order_unicode_empty_paragraph_and_cells():
 texts=['첫 문단','여신심사의 담당 부서는 DOCX심사팀이다.','가상 셀','마지막 문단']
 value=extract_docx(docx_bytes(p(texts[0])+p('')+table([[texts[1],texts[2]]])+p(texts[3])))
 assert value['text']=='\n\n'.join(texts)
 assert value['locations'][0]['paragraph']==1 and value['locations'][3]['paragraph']==3
 assert value['locations'][1]['kind']=='table_cell' and value['locations'][1]['table']==1 and value['locations'][1]['column']==1
 for loc,text in zip(value['locations'],texts):assert value['text'][loc['start']:loc['end']]==text

@pytest.mark.parametrize('extra',[{'../evil.xml':'x'},{'/evil.xml':'x'},{'word\\evil.xml':'x'},{'word/vbaProject.bin':b'x'},{'word/header1.xml':'x'},{'word/media/image1.png':b'x'}])
def test_unsafe_or_unsupported_package_parts(extra):
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(extra=extra))
 assert e.value.status==422

@pytest.mark.parametrize('tag',['ins','del','drawing','hyperlink','fldSimple','sdt','object','footnoteReference','commentRangeStart'])
def test_unsupported_body_structures_are_not_silently_dropped(tag):
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(p('safe')+f'<w:{tag}/>' ))
 assert e.value.code=='DOCX_UNSUPPORTED'

@pytest.mark.parametrize('body',[ '<w:p><w:pPr><w:numPr/></w:pPr><w:r><w:t>safe</w:t></w:r></w:p>', '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>'+p('safe')+'</w:tc></w:tr></w:tbl>', '<w:tbl><w:tr><w:tc>'+table([['safe']])+'</w:tc></w:tr></w:tbl>'])
def test_numbering_merged_and_nested_tables_rejected(body):
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(body))
 assert e.value.code=='DOCX_UNSUPPORTED'

def test_external_relationship_rejected():
 xml=f'<Relationships xmlns="{R}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="https://example.invalid/" TargetMode="External"/></Relationships>'
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(changes={'_rels/.rels':xml}))
 assert e.value.code=='DOCX_ACTIVE_CONTENT'

@pytest.mark.parametrize('xml',['<!DOCTYPE x [<!ENTITY a "synthetic">]><x>&a;</x>','<!DOCTYPE x SYSTEM "file:///synthetic"><x/>'])
def test_xml_dtd_entities_rejected(xml):
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(changes={'word/document.xml':xml}))
 assert e.value.code=='DOCX_ACTIVE_CONTENT'

def test_duplicate_and_symlink_zip_entries():
 for kind in ('duplicate','symlink'):
  stream=io.BytesIO(docx_bytes())
  with zipfile.ZipFile(stream,'a') as z:
   if kind=='duplicate':z.writestr('word/document.xml','x')
   else:
    info=zipfile.ZipInfo('word/settings.xml');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'/synthetic')
  with pytest.raises(AppError) as e:extract_docx(stream.getvalue())
  assert e.value.code=='DOCX_INVALID'

@pytest.mark.parametrize('raw',[b'garbage',b'PK\x03\x04broken',docx_bytes(p(''))])
def test_invalid_or_empty_documents(raw):
 with pytest.raises(AppError) as e:extract_docx(raw)
 assert e.value.status==422

def test_zip_expansion_limit():
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(extra={'word/settings.xml':'x'*1048577}))
 assert e.value.code=='DOCX_ZIP_LIMIT'

def test_xml_depth_limit():
 body='<w:p>'+'<w:r>'*51+'<w:t>safe</w:t>'+'</w:r>'*51+'</w:p>'
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(body))
 assert e.value.code=='DOCX_XML_LIMIT'

def test_isolation_unavailable_fails_closed(monkeypatch):
 import app.documents.pdf as runner
 monkeypatch.setattr(runner.sys,'platform','unsupported')
 with pytest.raises(AppError) as e:extract_docx(docx_bytes())
 assert e.value.code=='DOCX_PARSER_UNAVAILABLE'

@pytest.mark.parametrize('body',[ '<w:p><w:pPr><w:t>hidden</w:t></w:pPr><w:r><w:t>safe</w:t></w:r></w:p>', '<w:p><w:r><w:t>safe</w:t><w:tab><w:t>hidden</w:t></w:tab></w:r></w:p>'])
def test_content_inside_metadata_not_silently_ignored(body):
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(body))
 assert e.value.code=='DOCX_UNSUPPORTED'

def test_xml_processing_instruction_rejected():
 with pytest.raises(AppError) as e:extract_docx(docx_bytes(changes={'word/document.xml':'<?xml-stylesheet href="https://example.invalid/"?>'+f'<w:document xmlns:w="{W}"><w:body>'+p('safe')+'</w:body></w:document>'}))
 assert e.value.code=='DOCX_ACTIVE_CONTENT'
