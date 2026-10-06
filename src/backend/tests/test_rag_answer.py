import json
import pytest
from common_core.ai_pipeline.graphrag.answer import FactPacket,render_answer,select_relevant,AnswerInvalid

def packet(fid='F0',value='팀',namespace='A',predicate='담당부서',subject='업무',properties=()):return FactPacket(fid,predicate,subject,value,properties,{'quote':'합성 원문','evidence_id':fid},namespace)
@pytest.mark.parametrize('raw',['{}','{"answer_kind":"answer","selected_fact_ids":["unknown"]}','{"answer_kind":"answer","selected_fact_ids":["F0","F0"]}','{"answer_kind":"answer","selected_fact_ids":[true]}','{"answer_kind":"answer","selected_fact_ids":["F0"],"text":"invented"}','{"answer_kind":"answer","answer_kind":"insufficient_evidence","selected_fact_ids":[]}'])
def test_unbound_or_duplicate_provider_output_rejected(raw):
    with pytest.raises(AnswerInvalid):render_answer(raw,(packet(),),('담당부서',))
def test_conflicts_and_namespace_path_never_guessed():
    assert not select_relevant('업무 담당은?',(packet(),packet('F1','다른팀')))[0]
    first=packet(predicate='접수담당');second=packet('F1','1일','B','접수확인기한','팀')
    assert not select_relevant('업무 접수 확인 기한은?',(first,second))[0]
    second=packet('F1','1일','A','접수확인기한','팀');selected,required=select_relevant('업무 접수 확인 기한은?',(first,second));assert len(selected)==2
    with pytest.raises(AnswerInvalid):render_answer(json.dumps({'answer_kind':'answer','selected_fact_ids':['F1']}),selected,required)
