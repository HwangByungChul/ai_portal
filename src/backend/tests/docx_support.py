import io,zipfile
from xml.sax.saxutils import escape
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/package/2006/relationships'
T='http://schemas.openxmlformats.org/package/2006/content-types'
DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
MAIN='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
def p(text):return '<w:p><w:r><w:t>'+escape(text)+'</w:t></w:r></w:p>'
def table(rows):return '<w:tbl>'+''.join('<w:tr>'+''.join('<w:tc>'+p(cell)+'</w:tc>' for cell in row)+'</w:tr>' for row in rows)+'</w:tbl>'
def docx_bytes(body=None,*,changes=None,extra=None,compression=zipfile.ZIP_DEFLATED):
 parts={'[Content_Types].xml':f'<Types xmlns="{T}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="{MAIN}"/></Types>',
 '_rels/.rels':f'<Relationships xmlns="{R}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
 'word/document.xml':f'<w:document xmlns:w="{W}"><w:body>'+ (body if body is not None else p('여신심사의 담당 부서는 DOCX심사팀이다.'))+'</w:body></w:document>'}
 parts.update(changes or {});parts.update(extra or {})
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',compression=compression) as z:
  for name,data in parts.items():z.writestr(name,data.encode() if isinstance(data,str) else data)
 return out.getvalue()
