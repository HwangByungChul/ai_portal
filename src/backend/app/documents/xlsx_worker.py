"""Isolated SpreadsheetML reader. Bounded in-memory ZIP/XML; no project imports."""
import io
import json
import logging
import posixpath
import re
import resource
import stat
import sys
import zipfile
resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
from defusedxml import ElementTree as XML
from defusedxml.common import DefusedXmlException
logging.disable(logging.CRITICAL)
from datetime import datetime
import math
S="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL="http://schemas.openxmlformats.org/package/2006/relationships"
CT="http://schemas.openxmlformats.org/package/2006/content-types"
OFFICE="http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
TYPES={"xl/workbook.xml":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml","xl/styles.xml":"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml","xl/sharedStrings.xml":"application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml","xl/theme/theme1.xml":"application/vnd.openxmlformats-officedocument.theme+xml","docProps/core.xml":"application/vnd.openxmlformats-package.core-properties+xml","docProps/app.xml":"application/vnd.openxmlformats-officedocument.extended-properties+xml"}
TYPES.update({"xl/worksheets/sheet"+str(i)+".xml":"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml" for i in range(1,11)})
ALLOWED=set(TYPES)|{"[Content_Types].xml","_rels/.rels","xl/_rels/workbook.xml.rels"}

def fail(code):raise ValueError(code)
def local(e):return e.tag.split('}')[-1]
def integer(value,minimum=0,maximum=2147483647):
 if type(value) is not str or not re.fullmatch(r'0|[1-9][0-9]*',value):fail('XLSX_INVALID')
 result=int(value)
 if not minimum<=result<=maximum:fail('XLSX_INVALID')
 return result

def address(value):
 m=re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})',value or '')
 if not m:fail('XLSX_INVALID')
 col=0
 for c in m[1]:col=col*26+ord(c)-64
 row=int(m[2])
 if col>16384 or row>1048576:fail('XLSX_INVALID')
 return row,col

def valid_name(name):
 return type(name) is str and 1<=len(name)<=31 and not re.search(r'[\x00-\x1f\x7f:/\\?*\[\]]',name) and not name.startswith("'") and not name.endswith("'")

def extract(raw):
    if not raw.startswith(b"PK\x03\x04") or not 1 <= len(raw) <= 131072:
        fail("XLSX_INVALID")
    parts = {}
    total = 0
    directories = {p[:i+1] for p in ALLOWED for i,c in enumerate(p) if c == "/"}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        items = archive.infolist()
        if not 1 <= len(items) <= 200:
            fail("XLSX_ZIP_LIMIT")
        seen = set()
        for item in items:
            name = item.filename
            if name in seen or name.startswith("/") or "\\" in name or ".." in name.split("/") or item.orig_filename != name or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
                fail("XLSX_INVALID")
            seen.add(name)
            if item.flag_bits & 1:
                fail("XLSX_ENCRYPTED")
            if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                fail("XLSX_INVALID")
            if item.is_dir():
                if name not in directories or item.file_size:
                    fail("XLSX_INVALID")
                continue
            if name not in ALLOWED:
                fail("XLSX_UNSUPPORTED")
            if item.file_size > 1048576 or item.file_size > max(1, item.compress_size)*100:
                fail("XLSX_ZIP_LIMIT")
            total += item.file_size
            if total > 4194304:
                fail("XLSX_ZIP_LIMIT")
            with archive.open(item) as stream:
                content = stream.read(1048577)
            if len(content) != item.file_size or len(content) > 1048576:
                fail("XLSX_ZIP_LIMIT")
            parts[name] = content
    if not {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"} <= parts.keys():
        fail("XLSX_INVALID")
    nodes = 0
    def xml(content):
        nonlocal nodes
        decoded = content.decode("utf-8-sig")
        if re.search(r"<\?(?!xml(?:\s|\?>))", decoded):
            fail("XLSX_ACTIVE_CONTENT")
        depth = 0
        parser = XML.iterparse(io.BytesIO(content), events=("start", "end"), forbid_dtd=True, forbid_entities=True, forbid_external=True)
        for event, element in parser:
            if event == "start":
                depth += 1
                nodes += 1
                if depth > 50 or nodes > 20000:
                    fail("XLSX_XML_LIMIT")
            else:
                depth -= 1
        return parser.root
    roots = {name: xml(content) for name, content in parts.items()}
    types = roots["[Content_Types].xml"]
    if types.tag != "{"+CT+"}Types":
        fail("XLSX_INVALID")
    defaults = {}; overrides = {}
    for entry in types:
        if entry.tag == "{"+CT+"}Default":
            if set(entry.attrib) != {"Extension", "ContentType"}:
                fail("XLSX_INVALID")
            ext = entry.get("Extension"); value = entry.get("ContentType")
            expected = {"xml": "application/xml", "rels": "application/vnd.openxmlformats-package.relationships+xml"}
            if ext in defaults or expected.get(ext) != value:
                fail("XLSX_UNSUPPORTED")
            defaults[ext] = value
        elif entry.tag == "{"+CT+"}Override":
            if set(entry.attrib) != {"PartName", "ContentType"}:
                fail("XLSX_INVALID")
            name = entry.get("PartName"); value = entry.get("ContentType")
            if not name.startswith("/") or name in overrides or name[1:] not in parts or TYPES.get(name[1:]) != value:
                fail("XLSX_UNSUPPORTED")
            overrides[name] = value
        else:
            fail("XLSX_INVALID")
    if overrides.get("/xl/workbook.xml") != TYPES["xl/workbook.xml"] or defaults.get("rels") != "application/vnd.openxmlformats-package.relationships+xml":
        fail("XLSX_INVALID")
    for name in set(TYPES) & parts.keys():
        if overrides.get("/"+name) != TYPES[name]:
            fail("XLSX_INVALID")
    def relations(name,allowed,base):
        root=roots[name]
        if root.tag!='{'+REL+'}Relationships':fail('XLSX_INVALID')
        result={};targets=set()
        for rel in root:
            if rel.tag!='{'+REL+'}Relationship' or set(rel.attrib)-{'Id','Type','Target','TargetMode'} or not {'Id','Type','Target'}<=rel.attrib.keys():fail('XLSX_INVALID')
            if rel.get('TargetMode','Internal')!='Internal':fail('XLSX_ACTIVE_CONTENT')
            target=rel.get('Target');kind=rel.get('Type');rid=rel.get('Id')
            if not rid or rid in result or target.startswith('//') or '\\' in target or '..' in target.split('/') or ':' in target or '#' in target:fail('XLSX_INVALID')
            path=target[1:] if target.startswith('/') else posixpath.join(base,target)
            if path not in allowed.get(kind,set()) or path not in parts:fail('XLSX_ACTIVE_CONTENT')
            if path in targets:fail('XLSX_INVALID')
            targets.add(path);result[rid]=(kind,path)
        return result
    root_allowed={OFFICE+'officeDocument':{'xl/workbook.xml'},REL+'/metadata/core-properties':{'docProps/core.xml'},OFFICE+'extended-properties':{'docProps/app.xml'}}
    outer=relations('_rels/.rels',root_allowed,'')
    if sum(v[0]==OFFICE+'officeDocument' for v in outer.values())!=1:fail('XLSX_INVALID')
    body_allowed={OFFICE+'worksheet':{n for n in TYPES if n.startswith('xl/worksheets/')},OFFICE+'styles':{'xl/styles.xml'},OFFICE+'sharedStrings':{'xl/sharedStrings.xml'},OFFICE+'theme':{'xl/theme/theme1.xml'}}
    links=relations('xl/_rels/workbook.xml.rels',body_allowed,'xl')
    if {v[1] for v in links.values()}!={n for n in parts if n.startswith('xl/') and n not in ('xl/workbook.xml','xl/_rels/workbook.xml.rels')}:fail('XLSX_INVALID')
    semantic_names=['xl/workbook.xml','xl/styles.xml','xl/sharedStrings.xml']+[n for n in parts if n.startswith('xl/worksheets/')]
    for name in semantic_names:
        if name not in roots:continue
        for e in roots[name].iter():
            if not e.tag.startswith('{'+S+'}'):fail('XLSX_UNSUPPORTED')
            if name=='xl/styles.xml' and local(e) in ('t','v'):fail('XLSX_UNSUPPORTED')
            if local(e) not in ('t','v') and (e.text or '').strip() or (e.tail or '').strip():fail('XLSX_UNSUPPORTED')
            for attr in ('hidden','collapsed','zeroHeight','filterMode'):
                if e.get(attr,'0') not in ('0','false'):fail('XLSX_UNSUPPORTED')
    # Only simple numerical formats. Never interpret a cached formula or date serial.
    style_ids=[0]
    if 'xl/styles.xml' in roots:
        styles=roots['xl/styles.xml']
        if local(styles)!='styleSheet':fail('XLSX_INVALID')
        allowed_style={'numFmts','fonts','fills','borders','cellStyleXfs','cellXfs','cellStyles','dxfs','tableStyles','colors'}
        if any(local(e) not in allowed_style for e in styles):fail('XLSX_UNSUPPORTED')
        if len({local(e) for e in styles})!=len(styles):fail('XLSX_INVALID')
        for e in styles:
            if local(e) in ('numFmts','dxfs') and len(e):fail('XLSX_UNSUPPORTED')
            if local(e) in ('cellStyleXfs','cellXfs'):
                if e.get('count') is not None and integer(e.get('count'))!=len(e):fail('XLSX_INVALID')
                for xf in e:
                    if local(xf)!='xf' or integer(xf.get('numFmtId','0')) not in (0,1,2,49):fail('XLSX_UNSUPPORTED')
                    if any(local(x) not in ('alignment','protection') or len(x) for x in xf):fail('XLSX_UNSUPPORTED')
        xfs=styles.find('{'+S+'}cellXfs')
        if xfs is None or not len(xfs):fail('XLSX_INVALID')
        style_ids=[integer(x.get('numFmtId','0')) for x in xfs]
    def check_size(value):
        if value is None:return
        try:size=float(value)
        except ValueError:fail('XLSX_INVALID')
        if not math.isfinite(size):fail('XLSX_INVALID')
        if size<=0:fail('XLSX_UNSUPPORTED')
    def check_style(value):
        index=integer(value)
        if index>=len(style_ids):fail('XLSX_INVALID')
    def rich(element):
        text=[]
        for child in element:
            if local(child)=='t' and not len(child):text.append(child.text or '')
            elif local(child)=='r':
                for token in child:
                    if local(token)=='t' and not len(token):text.append(token.text or '')
                    elif local(token)=='rPr':
                        if any(local(x) in ('t','v','r','si','is') for x in token.iter()):fail('XLSX_UNSUPPORTED')
                    else:fail('XLSX_UNSUPPORTED')
            else:fail('XLSX_UNSUPPORTED')
        return ''.join(text)
    shared=[]
    if 'xl/sharedStrings.xml' in roots:
        sst=roots['xl/sharedStrings.xml']
        if local(sst)!='sst' or len(sst)>10000:fail('XLSX_TEXT_LIMIT')
        if sst.get('uniqueCount') is not None and integer(sst.get('uniqueCount'))!=len(sst):fail('XLSX_INVALID')
        for si in sst:
            if local(si)!='si':fail('XLSX_UNSUPPORTED')
            shared.append(rich(si))
    book=roots['xl/workbook.xml']
    if local(book)!='workbook':fail('XLSX_INVALID')
    allowed_book={'fileVersion','workbookPr','workbookProtection','bookViews','sheets','definedNames','calcPr'}
    if any(local(e) not in allowed_book for e in book) or len({local(e) for e in book})!=len(book):fail('XLSX_UNSUPPORTED')
    for e in book:
        if local(e)=='workbookProtection' and (len(e) or e.attrib):fail('XLSX_UNSUPPORTED')
        if local(e) in ('fileVersion','workbookPr','calcPr','definedNames') and len(e):fail('XLSX_UNSUPPORTED')
        if local(e)=='bookViews' and any(local(v)!='workbookView' or len(v) or v.get('visibility','visible')!='visible' for v in e):fail('XLSX_UNSUPPORTED')
    sheets=book.find('{'+S+'}sheets')
    if sheets is None or not 1<=len(sheets)<=10:fail('XLSX_SHEET_LIMIT')
    values=[];locations=[];offset=0;cell_count=0;names=set();used=set();sheet_ids=set()
    def add(text,loc):
        nonlocal offset
        if values:values.append('\n\n');offset+=2
        start=offset;values.append(text);offset+=len(text)
        if offset>40000:fail('XLSX_TEXT_LIMIT')
        locations.append(dict(loc,start=start,end=offset))
    for i,sh in enumerate(sheets,1):
        name=sh.get('name');rid=sh.get('{'+OFFICE[:-1]+'}id');sid=integer(sh.get('sheetId'),1)
        if local(sh)!='sheet' or len(sh) or set(sh.attrib)-{'name','sheetId','state','{'+OFFICE[:-1]+'}id'}:fail('XLSX_UNSUPPORTED')
        if sh.get('state','visible')!='visible':fail('XLSX_UNSUPPORTED')
        if not valid_name(name) or name.casefold() in names or sid in sheet_ids or rid not in links or links[rid][0]!=OFFICE+'worksheet':fail('XLSX_INVALID')
        path=links[rid][1]
        if path in used:fail('XLSX_INVALID')
        used.add(path);names.add(name.casefold());sheet_ids.add(sid)
        loc={'sheet_index':i,'sheet_name':name}
        add('시트: '+name,dict(loc,kind='sheet'))
        sheet=roots[path]
        if local(sheet)!='worksheet':fail('XLSX_INVALID')
        allowed_sheet={'sheetPr','dimension','sheetViews','sheetFormatPr','cols','sheetData','printOptions','pageMargins','pageSetup'}
        if any(local(e) not in allowed_sheet for e in sheet) or len({local(e) for e in sheet})!=len(sheet):fail('XLSX_UNSUPPORTED')
        for e in sheet:
            tag=local(e)
            if tag in ('dimension','sheetFormatPr','printOptions','pageMargins','pageSetup') and len(e):fail('XLSX_UNSUPPORTED')
            if tag=='sheetFormatPr':check_size(e.get('defaultRowHeight'))
            if tag=='sheetPr' and any(local(x) not in ('outlinePr','pageSetUpPr','tabColor') or len(x) for x in e):fail('XLSX_UNSUPPORTED')
            if tag=='sheetViews':
                for view in e:
                    if local(view)!='sheetView' or any(local(x) not in ('pane','selection') or len(x) for x in view):fail('XLSX_UNSUPPORTED')
            if tag=='cols':
                for col in e:
                    if local(col)!='col' or len(col):fail('XLSX_UNSUPPORTED')
                    if integer(col.get('min'),1,16384)>integer(col.get('max'),1,16384):fail('XLSX_INVALID')
                    check_style(col.get('style','0'));check_size(col.get('width'))
        data=sheet.find('{'+S+'}sheetData')
        if data is None:fail('XLSX_INVALID')
        previous_row=0
        for row in data:
            if local(row)!='row':fail('XLSX_UNSUPPORTED')
            number=integer(row.get('r'),1,1048576)
            if number<=previous_row:fail('XLSX_INVALID')
            previous_row=number;previous_col=0;check_style(row.get('s','0'));check_size(row.get('ht'))
            for c in row:
                if local(c)!='c' or set(c.attrib)-{'r','s','t'}:fail('XLSX_UNSUPPORTED')
                rowno,colno=address(c.get('r'))
                if rowno!=number or colno<=previous_col:fail('XLSX_INVALID')
                previous_col=colno;check_style(c.get('s','0'))
                kind=c.get('t','n')
                if kind not in ('inlineStr','s','n','b','d'):fail('XLSX_UNSUPPORTED')
                if any(local(x) not in ('v','is') for x in c):fail('XLSX_UNSUPPORTED')
                if len(c)>1:fail('XLSX_INVALID')
                if not len(c):continue
                value=c[0]
                if kind=='inlineStr':
                    if local(value)!='is':fail('XLSX_INVALID')
                    text=rich(value)
                else:
                    if local(value)!='v' or len(value):fail('XLSX_INVALID')
                    text=value.text or ''
                    if not text:
                        if kind in ('n',):continue
                        fail('XLSX_INVALID')
                    if kind=='s':
                        index=integer(text)
                        if index>=len(shared):fail('XLSX_INVALID')
                        text=shared[index]
                    elif kind=='n':
                        if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',text):fail('XLSX_INVALID')
                    elif kind=='b':
                        if text not in ('0','1'):fail('XLSX_INVALID')
                        text='TRUE' if text=='1' else 'FALSE'
                    else:
                        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?',text):fail('XLSX_INVALID')
                        datetime.fromisoformat(text.replace('Z','+00:00'))
                if not text.strip():continue
                cell_count+=1
                if cell_count>2000:fail('XLSX_TEXT_LIMIT')
                add('셀 '+c.get('r')+':\n'+text,dict(loc,kind='cell',cell=c.get('r')))
    if used!={p for k,p in links.values() if k==OFFICE+'worksheet'}:fail('XLSX_INVALID')
    text=''.join(values)
    if not cell_count:fail('XLSX_EMPTY')
    if len(text.encode())>131072:fail('XLSX_TEXT_LIMIT')
    return {'text':text,'locations':locations,'parser_version':'xlsx-v1+defusedxml-0.7.1'}
try:
    result = extract(sys.stdin.buffer.read(131073))
except DefusedXmlException:
    result = {"error": "XLSX_ACTIVE_CONTENT"}
except ValueError as error:
    safe = {"XLSX_INVALID", "XLSX_UNSUPPORTED", "XLSX_ENCRYPTED", "XLSX_ZIP_LIMIT", "XLSX_XML_LIMIT", "XLSX_TEXT_LIMIT", "XLSX_EMPTY", "XLSX_SHEET_LIMIT", "XLSX_ACTIVE_CONTENT"}
    result = {"error": str(error) if str(error) in safe else "XLSX_INVALID"}
except Exception:
    result = {"error": "XLSX_INVALID"}
sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
