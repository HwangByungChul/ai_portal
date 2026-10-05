"""Validate exact per-relation provenance before any persistence/provider step."""
from ..document.mapping import original_spans,line_range
from ..document.schemas import PlanError
from .extractor import extract_graph,semantic_key,DIRECTIONS


def validate_graph(source,chunks,evidence,graph):
    if len(graph.entities)>512 or len(evidence)>512 or len(graph.relations)>1024 or sum(len(r.evidence_ordinals) for r in graph.relations)>2048:
        raise PlanError('INDEX_LIMIT_EXCEEDED')
    units={u.ordinal:(c,u) for c in chunks for u in c.units}
    for ordinal,ev in enumerate(evidence):
        if ev.ordinal!=ordinal or ev.scope!=graph.metadata or ev.unit_ordinal not in units:raise PlanError('GRAPH_EVIDENCE_INVALID')
        chunk,unit=units[ev.unit_ordinal]
        if (ev.chunk_ordinal!=chunk.ordinal or ev.complete!=(unit.complete and len(original_spans(source,unit.start,unit.end))==1) or (ev.start_offset,ev.end_offset) not in original_spans(source,unit.start,unit.end)
                or ev.exact_quote!=source.raw_text[ev.start_offset:ev.end_offset]
                or (ev.line_start,ev.line_end)!=line_range(source,ev.start_offset,ev.end_offset)):
            raise PlanError('GRAPH_EVIDENCE_INVALID')
    for ordinal,entity in enumerate(graph.entities):
        if entity.ordinal!=ordinal or entity.scope!=graph.metadata or entity.semantic_key!=semantic_key(graph.metadata,entity.entity_type,entity.label):raise PlanError('GRAPH_SCOPE_INVALID')
    for ordinal,rel in enumerate(graph.relations):
        if (rel.ordinal!=ordinal or rel.scope!=graph.metadata or not rel.evidence_ordinals
                or not 0<=rel.from_ordinal<len(graph.entities) or not 0<=rel.to_ordinal<len(graph.entities)
                or DIRECTIONS.get(rel.predicate)!=(graph.entities[rel.from_ordinal].entity_type,graph.entities[rel.to_ordinal].entity_type)
                or any(not 0<=x<len(evidence) or not evidence[x].complete for x in rel.evidence_ordinals)):
            raise PlanError('GRAPH_SCOPE_INVALID')
    # Merely referencing a real quote is insufficient: it must prove *this* relation.
    expected=extract_graph(source,chunks,evidence,graph.metadata)
    if graph!=expected:raise PlanError('GRAPH_EVIDENCE_INVALID')
