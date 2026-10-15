from uuid import uuid4
import copy
import pytest
from pydantic import ValidationError
from app.workflows.approved_models import ApprovedWorkflow

def definition():
    return {'workflow_id':str(uuid4()),'name':'승인 업무 흐름','nodes':[
        {'node_id':'input','node_type':'input','title':'질문','config':{'input_key':'query'}},
        {'node_id':'model','node_type':'llm','title':'승인 Agent','config':{'asset_id':str(uuid4()),'version_id':str(uuid4()),'publication_revision':1,'values':{'question':{'node_id':'input'}}}},
        {'node_id':'output','node_type':'output','title':'결과','config':{'source':{'node_id':'model','path':['text']}}}
    ],'edges':[{'source_node':'input','target_node':'model'},{'source_node':'model','target_node':'output'}]}

@pytest.mark.parametrize('case',['arbitrary_model','arbitrary_prompt','cycle','unreachable','duplicate_edge','future_reference','boolean_steps','too_few_steps','extra_config','bad_path'])
def test_approved_definition_rejects_unsafe_or_ambiguous_nodes(case):
    body=definition()
    if case=='arbitrary_model':body['nodes'][1]['config']['model_id']='other'
    if case=='arbitrary_prompt':body['nodes'][1]['config']['system_prompt']='client prompt'
    if case=='cycle':body['edges'].append({'source_node':'output','target_node':'input'})
    if case=='unreachable':body['edges']=body['edges'][:1]
    if case=='duplicate_edge':body['edges'].append(body['edges'][0].copy())
    if case=='future_reference':body['nodes'][1]['config']['values']['question']={'node_id':'output'}
    if case=='boolean_steps':body['max_steps']=True
    if case=='too_few_steps':body['max_steps']=2
    if case=='extra_config':body['nodes'][0]['config']['url']='http://example.invalid'
    if case=='bad_path':body['nodes'][2]['config']['source']['path']=['x']*5
    with pytest.raises(ValidationError):ApprovedWorkflow.model_validate(body)

def test_order_is_deterministic_and_preserves_literal_values():
    body=definition();body['nodes'][1]['config']['values']['literal']='{{query}}'
    parsed=ApprovedWorkflow.model_validate(body)
    assert parsed.order()==['input','model','output']
    assert parsed.nodes[1].config['values']['literal']=='{{query}}'
