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


def pdf_attachment(data,request_id):
    if data['state']!='completed' or data['content_status']!='final' or data['result'] is None:raise AppError('SUMMARY_NOT_READY',409)
    # Generate clean text content
    summary_text = data['result']['text']
    evidence_lines = []
    for e in data.get('evidence', []):
        loc = e.get('location', {})
        where = f"{loc.get('line_start', 1)}~{loc.get('line_end', 1)} lines"
        evidence_lines.append(f"- {e.get('title', 'Doc')} (v{e.get('version_no', 1)}, {where})")

    content_lines = ["Document Summary Report", "======================", ""]
    content_lines.extend(summary_text.splitlines())
    content_lines.extend(["", "Sources / Evidence:", "-------------------"])
    content_lines.extend(evidence_lines)

    # Simple valid PDF-1.4 generation
    stream_lines = []
    y = 750
    for line in content_lines[:45]:
        safe_line = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        ascii_line = ''.join(c if ord(c) < 128 else '?' for c in safe_line)
        stream_lines.append(f"1 0 0 1 50 {y} Tm ({ascii_line}) Tj")
        y -= 14

    stream_content = "BT\n/F1 10 Tf\n" + "\n".join(stream_lines) + "\nET\n"
    stream_bytes = stream_content.encode('latin-1', errors='replace')
    stream_len = len(stream_bytes)

    objects = [
        b"%PDF-1.4\n",
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {stream_len} >>\nstream\n".encode('ascii') + stream_bytes + b"\nendstream\nendobj\n",
    ]

    offsets = []
    curr = 0
    body = b""
    for i, obj in enumerate(objects):
        if i > 0:
            offsets.append(curr)
        body += obj
        curr += len(obj)

    xref = f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode('ascii')
    for offset in offsets:
        xref += f"{offset:010d} 00000 n \n".encode('ascii')

    trailer = f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{curr}\n%%EOF\n".encode('ascii')
    pdf_bytes = body + xref + trailer

    return Response(
        pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': 'attachment; filename="summary.pdf"',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
            'X-Request-ID': request_id
        }
    )
