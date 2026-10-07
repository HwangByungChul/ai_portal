import io,zipfile,json
from pathlib import Path
import pytest
from xlsx_support import xlsx_bytes,cell,S,R,O,C
from app.documents.xlsx import extract_xlsx
from app.errors import AppError

def test_unicode_multisheet_and_real_cell_offsets():
 value=extract_xlsx(xlsx_bytes([('빈 시트',''),('규정',cell('한글\n줄바꿈','B2')+cell('12.50','C2','n')+cell('1','XFD1048576','b'))]))
 assert value['text']=='시트: 빈 시트\n\n시트: 규정\n\n셀 B2:\n한글\n줄바꿈\n\n셀 C2:\n12.50\n\n셀 XFD1048576:\nTRUE'
 assert value['locations'][2]['sheet_index']==2 and value['locations'][2]['cell']=='B2'
 for loc in value['locations']:assert value['text'][loc['start']:loc['end']]

@pytest.mark.parametrize('tag',['f','mergeCells','hyperlinks','drawing','autoFilter','extLst','tableParts','sheetProtection'])
def test_unsupported_semantics_rejected(tag):
 xml='<worksheet xmlns="'+S+'"><sheetData><row r="1">'+cell('safe')+'</row></sheetData><'+tag+'/></worksheet>'
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes(changes={'xl/worksheets/sheet1.xml':xml}))
 assert e.value.code=='XLSX_UNSUPPORTED'

@pytest.mark.parametrize('address',['XFE1','A1048577','A0','a1','A01'])
def test_invalid_cell_address(address):
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes([('규정',cell('safe',address))]))
 assert e.value.code=='XLSX_INVALID'

@pytest.mark.parametrize('value,kind',[('2','b'),('not-number','n'),('0','s'),('cache','str'),('#REF!','e'),('2026-02-30','d')])
def test_invalid_or_unsupported_value(value,kind):
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes([('규정',cell(value,kind=kind))]))
 assert e.value.status==422

@pytest.mark.parametrize('attr',['hidden="1"','collapsed="true"','zeroHeight="1"'])
def test_hidden_row_rejected(attr):
 raw='<worksheet xmlns="'+S+'"><sheetData><row r="1" '+attr+'>'+cell('safe')+'</row></sheetData></worksheet>'
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes(changes={'xl/worksheets/sheet1.xml':raw}))
 assert e.value.code=='XLSX_UNSUPPORTED'

@pytest.mark.parametrize('extra',[{'../evil.xml':'x'},{'xl/vbaProject.bin':b'x'},{'xl/externalLinks/externalLink1.xml':'x'},{'xl/media/image.png':b'x'}])
def test_unsafe_parts(extra):
 with pytest.raises(AppError):extract_xlsx(xlsx_bytes(extra=extra))

@pytest.mark.parametrize('attack',['formula_cache','duplicate','descending','mismatched_row','external','doctype','hidden_sheet','empty','too_many_sheets'])
def test_package_semantic_attacks(attack):
 changes={};sheets=None
 if attack=='formula_cache':changes['xl/worksheets/sheet1.xml']='<worksheet xmlns="'+S+'"><sheetData><row r="1"><c r="A1"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>'
 elif attack=='duplicate':sheets=[('규정',cell('a')+cell('b'))]
 elif attack=='descending':sheets=[('규정',cell('a','B1')+cell('b','A1'))]
 elif attack=='mismatched_row':changes['xl/worksheets/sheet1.xml']='<worksheet xmlns="'+S+'"><sheetData><row r="2">'+cell('safe')+'</row></sheetData></worksheet>'
 elif attack=='external':changes['xl/_rels/workbook.xml.rels']='<Relationships xmlns="'+R+'"><Relationship Id="rId1" Type="'+O+'worksheet" Target="https://example.invalid/" TargetMode="External"/></Relationships>'
 elif attack=='doctype':changes['xl/workbook.xml']='<!DOCTYPE x [<!ENTITY a "synthetic">]><x>&a;</x>'
 elif attack=='hidden_sheet':changes['xl/workbook.xml']='<workbook xmlns="'+S+'" xmlns:r="'+O[:-1]+'"><sheets><sheet name="규정" sheetId="1" r:id="rId1" state="hidden"/></sheets></workbook>'
 elif attack=='empty':sheets=[('규정','')]
 else:sheets=[('S'+str(i),cell('safe')) for i in range(11)]
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes(sheets,changes=changes))
 assert e.value.status==422

def test_date_lexical_value_preserved():
 v=extract_xlsx(xlsx_bytes([('규정',cell('2026-10-07T10:20:30','A1','d'))]));assert v['text'].endswith('2026-10-07T10:20:30')


def test_shared_rich_string_and_tab_text():
 from xlsx_support import add_part
 raw=xlsx_bytes([('규정',cell('0',kind='s'))])
 xml='<sst xmlns="'+S+'" uniqueCount="1"><si><r><rPr><b/></rPr><t>한글</t></r><r><t>\t본문</t></r></si></sst>'
 raw=add_part(raw,'xl/sharedStrings.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml','sharedStrings',xml)
 assert extract_xlsx(raw)['text']=='시트: 규정\n\n셀 A1:\n한글\t본문'

@pytest.mark.parametrize('format_id',[0,1,2,49,14,9,164])
def test_numerical_style_whitelist(format_id):
 from xlsx_support import add_part
 xml='<styleSheet xmlns="'+S+'"><cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="'+str(format_id)+'" xfId="0"/></cellXfs></styleSheet>'
 raw=add_part(xlsx_bytes([('규정',cell('12.500',kind='n'))]),'xl/styles.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml','styles',xml)
 if format_id in (0,1,2,49):assert extract_xlsx(raw)['text'].endswith('12.500')
 else:
  with pytest.raises(AppError) as e:extract_xlsx(raw)
  assert e.value.code=='XLSX_UNSUPPORTED'

def test_hidden_column_and_metadata_content_rejected():
 for content in ('<cols><col min="1" max="1" hidden="true"/></cols>','<sheetPr><t>hidden data</t></sheetPr>'):
  xml='<worksheet xmlns="'+S+'">'+content+'<sheetData><row r="1">'+cell('safe')+'</row></sheetData></worksheet>'
  with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes(changes={'xl/worksheets/sheet1.xml':xml}))
  assert e.value.code=='XLSX_UNSUPPORTED'

def test_duplicate_sheet_names_rejected():
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes([('Data',cell('safe')),('data',cell('safe'))]))
 assert e.value.code=='XLSX_INVALID'

def test_absolute_internal_package_relationship():
 raw='<Relationships xmlns="'+R+'"><Relationship Id="rId1" Type="'+O+'worksheet" Target="/xl/worksheets/sheet1.xml"/></Relationships>'
 assert extract_xlsx(xlsx_bytes(changes={'xl/_rels/workbook.xml.rels':raw}))['text'].endswith('XLSX심사팀이다.')

def test_duplicate_and_symlink_zip_entries_rejected():
 import stat
 for kind in ('duplicate','symlink'):
  stream=io.BytesIO(xlsx_bytes())
  with zipfile.ZipFile(stream,'a') as z:
   if kind=='duplicate':z.writestr('xl/workbook.xml','x')
   else:
    item=zipfile.ZipInfo('xl/styles.xml');item.create_system=3;item.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(item,'synthetic')
  with pytest.raises(AppError) as e:extract_xlsx(stream.getvalue())
  assert e.value.code=='XLSX_INVALID'

def test_ordinary_excel_generated_fixture():
 raw=Path(__file__).with_name('fixtures').joinpath('xlsx-excel-compatible.xlsx').read_bytes()
 value=extract_xlsx(raw)
 assert value['text']=='시트: 규정\n\n셀 B2:\n여신심사의 담당 부서는 XLSX심사팀이다.\n\n셀 C2:\n12.5\n\n셀 D2:\nTRUE\n\n시트: 안내\n\n셀 A1:\n합성 문서'
 assert [x.get('cell') for x in value['locations'] if x['kind']=='cell']==['B2','C2','D2','A1']


@pytest.mark.parametrize('metadata',['<cols><col min="1" max="1" width="0"/></cols>','<sheetFormatPr defaultRowHeight="0"/>'])
def test_zero_size_hidden_data_rejected(metadata):
 xml='<worksheet xmlns="'+S+'">'+metadata+'<sheetData><row r="1">'+cell('safe')+'</row></sheetData></worksheet>'
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes(changes={'xl/worksheets/sheet1.xml':xml}))
 assert e.value.code=='XLSX_UNSUPPORTED'

def test_zero_height_row_rejected():
 xml='<worksheet xmlns="'+S+'"><sheetData><row r="1" ht="0">'+cell('safe')+'</row></sheetData></worksheet>'
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes(changes={'xl/worksheets/sheet1.xml':xml}))
 assert e.value.code=='XLSX_UNSUPPORTED'

def test_nonempty_workbook_protection_rejected():
 xml='<workbook xmlns="'+S+'"><workbookProtection lockStructure="1"/><sheets/></workbook>'
 with pytest.raises(AppError) as e:extract_xlsx(xlsx_bytes(changes={'xl/workbook.xml':xml}))
 assert e.value.code=='XLSX_UNSUPPORTED'
