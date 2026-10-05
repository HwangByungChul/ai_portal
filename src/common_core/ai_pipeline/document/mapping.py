"""Translate derived coordinates to checked contiguous original spans."""
from .schemas import ParsedSource,PlanError


def original_spans(source: ParsedSource, start: int, end: int) -> tuple[tuple[int,int], ...]:
    if not 0<=start<end<=len(source.text) or len(source.text)!=len(source.mapping):
        raise PlanError('SOURCE_MAPPING_INVALID')
    spans=[]
    for pos in range(start,end):
        left,right=source.mapping[pos]
        if (not 0<=left<right<=len(source.raw_text)
                or source.raw_text[left:right].replace('\r\n','\n').replace('\r','\n')!=source.text[pos]
                or (spans and left<spans[-1][1])):
            raise PlanError('SOURCE_MAPPING_INVALID')
        if spans and left==spans[-1][1]:spans[-1]=(spans[-1][0],right)
        else:spans.append((left,right))
    return tuple(spans)


def line_range(source: ParsedSource,start: int,end: int) -> tuple[int,int]:
    if not 0<=start<end<=len(source.raw_text):raise PlanError('SOURCE_MAPPING_INVALID')
    # CRLF is one line break; offsets remain original Unicode codepoints.
    def breaks(text):return text.count('\n')+text.count('\r')-text.count('\r\n')
    return breaks(source.raw_text[:start])+1,breaks(source.raw_text[:end-1])+1
