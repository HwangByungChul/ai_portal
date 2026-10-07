"""Immediate literal Markdown attachment; no public URL or export cache."""
import re,string
from starlette.responses import Response
from app.errors import AppError

def escaped(value):
    return ''.join('\\'+c if c in string.punctuation else c for c in str(value))
def literal_block(value):
    longest=max((len(x) for x in re.findall(r'`+',value)),default=0)
    fence='`'*max(3,longest+1)
    return fence+'text\n'+value+'\n'+fence

def structure_label(location):
    if location['kind']=='paragraph':return f'본문 {location["paragraph"]}문단'
    if location['kind']=='table_cell':return f'표 {location["table"]} · {location["row"]}행 {location["column"]}열'
    if location['kind']=='cell':return f'{location["sheet_name"]} 시트 · {location["cell"]}셀'
    raise AppError('STORAGE_UNAVAILABLE',503)

def markdown_attachment(data,request_id):
    if data['state']!='completed' or data['content_status']!='final' or data['result'] is None:raise AppError('SUMMARY_NOT_READY',409)
    text='# 원문 발췌 요약\n\n'+literal_block(data['result']['text'])+'\n\n## 출처\n'
    for e in data['evidence']:
        loc=e['location'];where=f'{loc["line_start"]}~{loc["line_end"]}행'
        if 'page_start' in e:where+=f' · {e["page_start"]}~{e["page_end"]}페이지'
        if 'structure_locations' in e:where+=' · '+', '.join(structure_label(x) for x in e['structure_locations'])
        text+=f'\n{e["ordinal"]+1}. {escaped(e["title"])} — 버전 {e["version_no"]} · {escaped(where)}\n'
    return Response(text.encode('utf-8'),media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':'attachment; filename="summary.md"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Request-ID':request_id})
