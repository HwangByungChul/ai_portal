import io,zipfile,re
from xml.sax.saxutils import escape
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/package/2006/relationships'
O='http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
C='http://schemas.openxmlformats.org/package/2006/content-types'
XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
def cell(text,address='A1',kind='inlineStr',extra=''):
 value='<is><t>'+escape(text)+'</t></is>' if kind=='inlineStr' else '<v>'+escape(text)+'</v>'
 return '<c r="'+address+'" t="'+kind+'" '+extra+'>'+value+'</c>'
def xlsx_bytes(sheets=None,*,changes=None,extra=None,compression=zipfile.ZIP_DEFLATED):
 sheets=sheets if sheets is not None else [('규정',cell('여신심사의 담당 부서는 XLSX심사팀이다.'))]
 parts={};book=[];rels=[];types=[]
 for i,(name,cells) in enumerate(sheets,1):
  path='xl/worksheets/sheet'+str(i)+'.xml';rid='rId'+str(i)
  book.append('<sheet name="'+escape(name,{'"':'&quot;'})+'" sheetId="'+str(i)+'" r:id="'+rid+'"/>')
  rels.append('<Relationship Id="'+rid+'" Type="'+O+'worksheet" Target="worksheets/sheet'+str(i)+'.xml"/>')
  types.append('<Override PartName="/'+path+'" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
  groups={}
  for c in re.findall(r'<c\b.*?</c>',cells,flags=re.S):
   row=re.search(r'r="[A-Za-z]+([0-9]+)"',c).group(1);groups.setdefault(row,[]).append(c)
  rows=''.join('<row r="'+n+'">'+''.join(cs)+'</row>' for n,cs in groups.items())
  parts[path]='<worksheet xmlns="'+S+'"><sheetData>'+rows+'</sheetData></worksheet>'
 parts['xl/workbook.xml']='<workbook xmlns="'+S+'" xmlns:r="'+O[:-1]+'"><sheets>'+''.join(book)+'</sheets></workbook>'
 parts['xl/_rels/workbook.xml.rels']='<Relationships xmlns="'+R+'">'+''.join(rels)+'</Relationships>'
 parts['_rels/.rels']='<Relationships xmlns="'+R+'"><Relationship Id="root" Type="'+O+'officeDocument" Target="xl/workbook.xml"/></Relationships>'
 parts['[Content_Types].xml']='<Types xmlns="'+C+'"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(types)+'</Types>'
 parts.update(extra or {});parts.update(changes or {})
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',compression=compression) as z:
  for n,v in parts.items():z.writestr(n,v.encode() if isinstance(v,str) else v)
 return out.getvalue()


def add_part(raw,name,content_type,relation_type,content):
 from xml.etree import ElementTree as E
 with zipfile.ZipFile(io.BytesIO(raw)) as z:parts={n:z.read(n) for n in z.namelist()}
 types=E.fromstring(parts['[Content_Types].xml']);E.SubElement(types,'{'+C+'}Override',{'PartName':'/'+name,'ContentType':content_type})
 rels=E.fromstring(parts['xl/_rels/workbook.xml.rels']);E.SubElement(rels,'{'+R+'}Relationship',{'Id':'extra'+str(len(rels)),'Type':O+relation_type,'Target':name.removeprefix('xl/')})
 parts['[Content_Types].xml']=E.tostring(types);parts['xl/_rels/workbook.xml.rels']=E.tostring(rels);parts[name]=content.encode() if isinstance(content,str) else content
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for n,data in parts.items():z.writestr(n,data)
 return out.getvalue()
