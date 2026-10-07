import pytest
from common_core.ai_pipeline.summary.selection import validate_selection
from common_core.ai_pipeline.summary.render import render_extracts

@pytest.mark.parametrize("raw", ['{"selected_ids":["U0"],"extra":"금액 999억원"}', '{"selected_ids":["invented"]}', '{"selected_ids":["U0","U0"]}', '{"selected_ids":[1]}', '{"selected_ids":null}', '{"selected_ids":["U0"]} trailing', '{"selected_ids":[],"selected_ids":["U0"]}', '[]', '{"selected_ids":["U0","U1","U2","U3"]}'])
def test_selection_rejects_invented_payload(raw):
    with pytest.raises(ValueError):validate_selection(raw, ('U0','U1','U2','U3'), 3)

def test_selection_orders_literal_quotes_and_accepts_empty():
    assert validate_selection('{"selected_ids":["U3","U0"]}', ('U0','U1','U2','U3'), 3)==('U0','U3')
    assert validate_selection('{"selected_ids":[]}', ('U0',), 5)==()
    assert render_extracts(('원문 100억원이다.', '기한은 10월 7일이다.'))=='1. 원문 100억원이다.\n2. 기한은 10월 7일이다.'


def test_export_literal_fences_and_human_structural_locations():
    from app.execution.exports import markdown_attachment,escaped,structure_label
    original='1. <script>active()</script> ![image](https://invalid.test/a)\n```text\n````\n2. 원문이다.'
    row={'ordinal':0,'title':'<img> ![title](x) &amp;','version_no':2,'location':{'line_start':1,'line_end':5},'page_start':1,'page_end':2}
    data={'state':'completed','content_status':'final','result':{'text':original},'evidence':[row]}
    content=markdown_attachment(data,'safe').body.decode()
    assert '`````text\n'+original+'\n`````' in content
    assert escaped(row['title']) in content and '\n## 출처\n' in content
    assert '<script>' not in content.split('`````text\n',1)[0]
    assert '1\\~2페이지' in content
    assert structure_label({'kind':'paragraph','paragraph':4})=='본문 4문단'
    assert structure_label({'kind':'table_cell','table':2,'row':3,'column':4})=='표 2 · 3행 4열'
    assert structure_label({'kind':'cell','sheet_name':'계획','cell':'A1'})=='계획 시트 · A1셀'
    data['evidence'][0].pop('page_start');data['evidence'][0].pop('page_end')
    data['evidence'][0]['structure_locations']=[{'kind':'paragraph','paragraph':4},{'kind':'table_cell','table':2,'row':3,'column':4},{'kind':'cell','sheet_name':'계획','cell':'A1'}]
    content=markdown_attachment(data,'safe').body.decode()
    assert '본문 4문단' in content and '표 2 · 3행 4열' in content and '계획 시트 · A1셀' in content
    assert 'structure_locations' not in content and "'kind'" not in content
