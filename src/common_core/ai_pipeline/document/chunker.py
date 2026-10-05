"""Sentence-first token chunks. No overlap, truncation or guessed offsets."""
import re
from .schemas import Unit,Chunk,ParsedSource,PlanError


def checked_count(tokenizer,text):
    value=tokenizer(text)
    if type(value) is not int or value<1:raise PlanError('TOKENIZER_INVALID')
    return value


def chunk_source(source: ParsedSource, tokenizer) -> tuple[Chunk,...]:
    units=[]
    for line in source.lines:
        text=source.text[line.start:line.end]
        for match in re.finditer(r'[^.!?。！？]+(?:[.!?。！？]+|$)',text):
            left=line.start+match.start();right=line.start+match.end()
            while left<right and source.text[left].isspace():left+=1
            while right>left and source.text[right-1].isspace():right-=1
            if left==right:continue
            complete=line.kind=='body'
            if checked_count(tokenizer,source.text[left:right])<=512:
                units.append(Unit(len(units),left,right,complete,line.kind));continue
            # Token count can merge at prefix boundaries; verify every selected prefix.
            while left<right:
                lo,hi,best=left+1,right,left
                while lo<=hi:
                    mid=(lo+hi)//2
                    if checked_count(tokenizer,source.text[left:mid])<=512:best=mid;lo=mid+1
                    else:hi=mid-1
                if best==left:raise PlanError('TOKENIZER_INVALID')
                if source.text[left:best].strip():units.append(Unit(len(units),left,best,False,line.kind))
                left=best
    chunks=[];group=[]
    def flush():
        if not group:return
        start,end=group[0].start,group[-1].end;text=source.text[start:end]
        chunks.append(Chunk(len(chunks),start,end,text,checked_count(tokenizer,text),tuple(group)))
        if len(chunks)>128:raise PlanError('INDEX_LIMIT_EXCEEDED')
    for unit in units:
        if group and checked_count(tokenizer,source.text[group[0].start:unit.end])>512:flush();group=[]
        group.append(unit)
    flush()
    if not chunks:raise PlanError('SOURCE_EMPTY_AFTER_PARSE')
    return tuple(chunks)
