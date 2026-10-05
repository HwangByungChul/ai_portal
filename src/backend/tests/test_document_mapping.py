from dataclasses import replace
import pytest
from common_core.ai_pipeline.document.parser import parse_source
from common_core.ai_pipeline.document.mapping import original_spans,line_range
from common_core.ai_pipeline.document.schemas import PlanError
from c02_support import make_plan

@pytest.mark.parametrize('separator',['\n','\r\n','\r'],ids=['LF','CRLF','CR'])
def test_original_unicode_position_is_preserved(separator):
    raw='\ufeff# 제목'+separator+separator+'동일 문장이다.'+separator+'동일 문장이다.'
    source=parse_source(raw.encode(),'text/markdown')
    assert source.raw_text==raw and '\r' not in source.text
    assert len(source.mapping)==len(source.text)
    for i,(start,end) in enumerate(source.mapping):
        assert raw[start:end].replace('\r\n','\n').replace('\r','\n')==source.text[i]
    _,plan=make_plan(raw,media='text/markdown')
    assert [e.start_offset for e in plan.evidence]==[raw.index('동일'),raw.rindex('동일')]
    assert [e.line_start for e in plan.evidence]==[3,4]


def test_markers_metadata_notice_removed_but_heading_text_kept():
    raw='---\nowner_tenant_id: OTHER\n---\n# 업무 제목\n<a id="EV-X-01"></a>\n## EV-X-01 책임\n가상 여신심사의 담당 부서는 팀이다.\n'
    source,plan=make_plan(raw,media='text/markdown')
    assert all(x not in source.text for x in ['OTHER','EV-X','<a','owner_tenant'])
    assert '업무 제목' in source.text and '책임' in source.text
    assert plan.graph.relations[0].predicate=='담당부서'
    assert source.raw_text[plan.evidence[0].start_offset:plan.evidence[0].end_offset]==plan.evidence[0].exact_quote


def test_discontinuous_formatting_is_not_one_quote_or_relation():
    source,plan=make_plan('가상 여신심사의 담당 부서는 **팀**이다.',media='text/markdown')
    assert len(plan.evidence)>1 and not any(e.complete for e in plan.evidence)
    assert plan.graph.relations==() and plan.graph.coverage=='partial'
    for ev in plan.evidence:assert source.raw_text[ev.start_offset:ev.end_offset]==ev.exact_quote

@pytest.mark.parametrize('raw,media',[(b'', 'text/plain'),(b'\xff','text/plain'),(b'\0','text/plain'),(b'a'*40001,'text/plain'),('😀'.encode()*32769,'text/plain'),(b'---\nx: y','text/markdown'),(b'```\ncode','text/markdown'),(b'abc','text/html')],ids=['empty','utf8','nul','charlimit','bytelimit','frontmatter','codefence','mime'])
def test_invalid_input_rejected(raw,media):
    with pytest.raises(PlanError):parse_source(raw,media)


def test_bad_mapping_and_raw_text_digest_are_rejected():
    source,plan=make_plan('가상 여신심사의 담당 부서는 팀이다.')
    with pytest.raises(PlanError):original_spans(replace(source,mapping=((999,1000),)*len(source.text)),0,1)
    from common_core.ai_pipeline.document.pipeline import build_document_plan
    with pytest.raises(PlanError):build_document_plan(replace(source,raw_text=source.raw_text.replace('팀','X')),plan.metadata,len)


def test_code_fence_text_does_not_become_regulatory_relation():
    source,plan=make_plan('```\n가상 여신심사의 담당 부서는 팀이다.\n```',media='text/markdown')
    assert not plan.graph.relations and plan.graph.coverage=='partial'
