"""Each citation is a real continuous original interval, not normalized prose."""
from ..document.mapping import original_spans,line_range
from ..document.schemas import PlanError
from .schemas import Evidence


def build_evidence(source,chunks,metadata):
    result=[]
    for chunk in chunks:
        for unit in chunk.units:
            if unit.kind=='heading':continue
            spans=original_spans(source,unit.start,unit.end)
            for start,end in spans:
                if not source.raw_text[start:end].strip():continue
                first,last=line_range(source,start,end)
                result.append(Evidence(len(result),chunk.ordinal,unit.ordinal,start,end,first,last,
                    source.raw_text[start:end],unit.complete and len(spans)==1,metadata))
                if len(result)>512:raise PlanError('INDEX_LIMIT_EXCEEDED')
    return tuple(result)
