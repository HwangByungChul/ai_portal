"""Restricted UTF-8 TXT/Markdown parsing with original codepoint provenance."""
import hashlib
import re
from .schemas import ParsedSource,SourceLine,PlanError

NOTICE='개인 학습·MVP 시험용 합성 자료입니다. 실제 금융기관의 규정·법령·업무 지침이 아닙니다.'


def parse_source(raw_bytes: bytes, media_type: str) -> ParsedSource:
    if type(raw_bytes) is not bytes or not 1<=len(raw_bytes)<=131072 or media_type not in ('text/plain','text/markdown'):
        raise PlanError('SOURCE_INVALID')
    try:raw=raw_bytes.decode('utf-8')
    except UnicodeDecodeError:raise PlanError('SOURCE_INVALID') from None
    if not raw.strip('\ufeff \t\r\n') or len(raw)>40000 or '\0' in raw:raise PlanError('SOURCE_INVALID')
    lines=list(re.finditer(r'[^\r\n]*(?:\r\n|\r|\n|$)',raw));front=False;front_done=False;code=False
    out=[];mapping=[];records=[];warnings=[]
    for number,line in enumerate(lines):
        original=line.group();body=original.rstrip('\r\n');base=line.start();keep=list(range(len(body)));kind='body'
        if number==0 and body.startswith('\ufeff'):keep=keep[1:]
        clean=''.join(body[i] for i in keep)
        if media_type=='text/markdown':
            if number==0 and clean=='---':front=True;continue
            if front:
                if clean in ('---','...'):front=False;front_done=True
                continue
            if clean.strip()=='> '+NOTICE:continue
            if re.fullmatch(r'\s*<a\s+id=[\"\'][^\"\']+[\"\']\s*>\s*</a>\s*',clean):continue
            if clean.lstrip().startswith(('```','~~~')):
                code=not code;warnings.append('CODE_FENCE');continue
            if code:kind='code'
            heading=re.match(r'^\s{0,3}#{1,6}\s+',clean)
            prefix=re.match(r'^\s{0,3}(?:[-+*]|\d+[.)])\s+',clean) if not heading else heading
            if heading:kind='heading'
            if prefix:keep=keep[prefix.end():]
            clean=''.join(body[i] for i in keep)
            # Remove only known syntax; never resolve URLs or execute frontmatter.
            removed=set()
            for match in re.finditer(r'EV-[A-Za-z0-9-]+|<a\s+id=[\"\'][^\"\']+[\"\']\s*>\s*</a>|\*\*|__|`',clean):
                removed.update(range(match.start(),match.end()))
            keep=[index for pos,index in enumerate(keep) if pos not in removed]
        start=len(out)
        for index in keep:out.append(body[index]);mapping.append((base+index,base+index+1))
        end=len(out)
        if ''.join(out[start:end]).strip():records.append(SourceLine(start,end,kind))
        if original.endswith(('\r','\n')):
            left=base+len(body);out.append('\n');mapping.append((left,line.end()))
    if front or code:raise PlanError('SOURCE_FORMAT_INVALID')
    text=''.join(out)
    if not text.strip():raise PlanError('SOURCE_EMPTY_AFTER_PARSE')
    return ParsedSource(raw,hashlib.sha256(raw_bytes).digest(),text,tuple(mapping),tuple(records),tuple(sorted(set(warnings))),media_type=media_type)
