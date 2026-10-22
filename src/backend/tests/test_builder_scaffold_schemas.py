"""Pure proposal contracts: no database, provider, or service fixtures."""
import json
from copy import deepcopy
from dataclasses import replace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.ai.model_registry import APPROVED_MODELS
from app.builder.schemas import SaveProfile
from app.builder.scaffold_schemas import (
    AgentProposal, ScaffoldRequest, WorkflowProposal, validate_proposal,
)

ID = '00000000-0000-4000-8000-000000000001'
REF = {'document_id': ID, 'version_id': ID}


def request(**changes):
    return {'client_request_id': ID, 'target': 'agent', 'intent': '내부 업무 도우미', **changes}


def agent(rag=False):
    kind = 'rules_rag' if rag else 'general'
    return {
        'config': {'name': '업무 도우미', 'description': '검토용 초안',
                   'instructions': '친절하게 답변하세요.', 'execution_kind': kind},
        'profile': {'schema_version': 1, 'system_prompt': '친절하게 답변하세요.',
                    'developer_prompt': '', 'user_template': '{{question}}',
                    'model_ref': 'default_' + kind, 'document_refs': [dict(REF)] if rag else []},
        'missing_questions': ['대상 사용자는 누구인가요?'], 'warnings': ['저장 전 검토하세요.'],
    }


def workflow(count=3):
    kinds = ['input', 'llm'] + ['validate'] * (count - 3) + ['output']
    return {
        'name': '업무 처리', 'description': '검토용 흐름',
        'nodes': [{'node_id': f'n{i}', 'node_type': kind, 'title': f'단계 {i}',
                   'config': {'input_key': 'query'} if kind == 'input' else {}}
                  for i, kind in enumerate(kinds)],
        'edges': [{'source_node': f'n{i}', 'target_node': f'n{i+1}'} for i in range(count - 1)],
    }


@pytest.mark.parametrize('rag', [False, True])
def test_agent_roundtrips_json_refs_and_matches_save_contract(rag):
    raw = agent(rag)
    before = deepcopy(raw)
    proposal = validate_proposal('agent', json.loads(json.dumps(raw)))
    assert isinstance(proposal, AgentProposal)
    assert raw == before
    SaveProfile(client_request_id=ID, config=proposal.config, profile=proposal.profile)
    assert validate_proposal('agent', proposal.model_dump(mode='json')) == proposal
    if rag:
        assert isinstance(proposal.profile.document_refs[0].document_id, UUID)


def test_request_uuid_and_utf8_boundary():
    value = ScaffoldRequest.model_validate(request(intent='한' * 1333 + 'a', document_refs=[REF]))
    assert isinstance(value.client_request_id, UUID)
    assert isinstance(value.document_refs[0].version_id, UUID)
    # Normal leading/trailing user whitespace is data, not a normalization error.
    assert ScaffoldRequest.model_validate(request(intent=' 업무 ')).intent == ' 업무 '


@pytest.mark.parametrize('changes', [
    {'intent': ''}, {'intent': '   '}, {'intent': 2}, {'intent': True},
    {'intent': '한' * 1334}, {'intent': 'a' * 4001}, {'intent': '\0'}, {'intent': '\ud800'},
    {'client_request_id': 'invalid'}, {'target': 'tool'}, {'provider_url': 'https://invalid.test'},
    {'answers': {str(i): 'x' for i in range(21)}}, {'answers': {'x': 1}},
    {'answers': {'': 'x'}}, {'answers': {' ': 'x'}}, {'answers': {'x': '\0'}},
    {'answers': {'x': '\ud800'}}, {'answers': {'x': 'a' * 2001}},
    {'answers': {'x': '한' * 667}}, {'answers': {'a' * 81: 'x'}},
    {'answers': {'한' * 54: 'x'}}, {'answers': {1: 'x'}},
    {'document_refs': [REF, REF]}, {'document_refs': [REF] * 6},
    {'document_refs': [{**REF, 'tenant_id': ID}]},
])
def test_invalid_request(changes):
    with pytest.raises(ValidationError):
        ScaffoldRequest.model_validate(request(**changes))


def test_request_collection_boundaries():
    refs = [{'document_id': str(UUID(int=i+1)), 'version_id': ID} for i in range(5)]
    value = ScaffoldRequest.model_validate(request(
        answers={str(i): 'a' * 2000 for i in range(20)}, document_refs=refs))
    assert len(value.answers) == 20 and len(value.document_refs) == 5


@pytest.mark.parametrize('case', ['unknown', 'disabled', 'mismatched_default', 'instructions',
                                  'general_refs', 'duplicate_refs', 'profile_extra', 'config_extra',
                                  'top_extra', 'wrong_schema_type', 'invalid_template'])
def test_invalid_agent(case):
    raw = agent()
    if case == 'unknown': raw['profile']['model_ref'] = 'invented-model'
    elif case == 'disabled': raw['profile']['model_ref'] = 'mock-disabled'
    elif case == 'mismatched_default': raw['profile']['model_ref'] = 'default_rules_rag'
    elif case == 'instructions': raw['profile']['system_prompt'] = '다른 지시문'
    elif case == 'general_refs': raw['profile']['document_refs'] = [REF]
    elif case == 'duplicate_refs':
        raw = agent(True)
        raw['profile']['document_refs'] *= 2
    elif case == 'profile_extra': raw['profile']['credential'] = 'placeholder'
    elif case == 'config_extra': raw['config']['model_url'] = 'https://invalid.test'
    elif case == 'top_extra': raw['tenant_id'] = ID
    elif case == 'wrong_schema_type': raw['profile']['schema_version'] = '1'
    elif case == 'invalid_template': raw['profile']['user_template'] = '{{question.foo}}'
    with pytest.raises(ValueError):
        validate_proposal('agent', raw)


@pytest.mark.parametrize('rag,capability', [(False, 'chat'), (True, 'rag')])
def test_approved_model_requires_matching_execution_capability(monkeypatch, rag, capability):
    raw = agent(rag)
    raw['profile']['model_ref'] = 'mock-fast'
    validate_proposal('agent', raw)
    model = APPROVED_MODELS['mock-fast']
    monkeypatch.setitem(APPROVED_MODELS, 'mock-fast', replace(model, capabilities=(capability,)))
    validate_proposal('agent', raw)
    monkeypatch.setitem(APPROVED_MODELS, 'mock-fast', replace(model, capabilities=()))
    with pytest.raises(ValueError):
        validate_proposal('agent', raw)


@pytest.mark.parametrize('target', ['agent', 'workflow'])
@pytest.mark.parametrize('text', [
    'https://invalid.test', 'ftp://invalid.test', 'www.invalid.test', 'Bearer placeholder',
    'api_key=placeholder', 'password: placeholder', 'client_secret = placeholder',
    'token=placeholder', 'secret: placeholder', 'authorization: placeholder',
    'endpoint=internal.invalid', 'sk-00000000000000000000', '\0', '\ud800',
])
def test_proposal_rejects_sensitive_or_invalid_text_everywhere(target, text):
    raw = agent() if target == 'agent' else workflow()
    raw['warnings'] = [text]
    with pytest.raises(ValueError):
        validate_proposal(target, raw)
    raw.pop('warnings')
    if target == 'agent': raw['config']['description'] = text
    else: raw['nodes'][1]['title'] = text
    with pytest.raises(ValueError):
        validate_proposal(target, raw)


@pytest.mark.parametrize('field,count', [('missing_questions', 8), ('warnings', 12)])
def test_notice_limits(field, count):
    raw = agent()
    raw[field] = ['검토'] * count
    validate_proposal('agent', raw)
    for bad in (['검토'] * (count + 1), ['a' * 501], [' '], [''], [1]):
        raw[field] = bad
        with pytest.raises(ValueError):
            validate_proposal('agent', raw)


def test_connected_acyclic_workflow_with_all_supported_types():
    raw = workflow(5)
    raw['nodes'][2]['node_type'] = 'read_tool'
    before = deepcopy(raw)
    result = validate_proposal('workflow', raw)
    assert isinstance(result, WorkflowProposal)
    assert raw == before
    assert result.nodes[2].config == {}  # User must select the actual Tool in Canvas.


def test_graph_at_maximum_and_over_limits():
    raw = workflow(20)
    raw['edges'] += [{'source_node': 'n0', 'target_node': f'n{i}'} for i in range(2, 13)]
    assert len(validate_proposal('workflow', raw).edges) == 30
    raw['edges'].append({'source_node': 'n0', 'target_node': 'n13'})
    with pytest.raises(ValueError): validate_proposal('workflow', raw)
    with pytest.raises(ValueError): validate_proposal('workflow', workflow(21))


@pytest.mark.parametrize('case', ['cycle', 'self_loop', 'duplicate_node', 'duplicate_edge',
    'unknown_endpoint', 'disconnected', 'unsupported_node', 'missing_llm', 'extra_input',
    'extra_output', 'invented_agent', 'invented_tool', 'secret_config', 'url_config',
    'nested_config', 'input_type', 'input_blank', 'input_invalid', 'node_nul', 'node_blank',
    'title_blank', 'extra_node_field', 'extra_edge_field', 'extra_top_field'])
def test_invalid_workflow(case):
    raw = workflow(5)
    if case == 'cycle': raw['edges'].append({'source_node': 'n3', 'target_node': 'n1'})
    elif case == 'self_loop': raw['edges'][0]['target_node'] = 'n0'
    elif case == 'duplicate_node': raw['nodes'][2]['node_id'] = 'n1'
    elif case == 'duplicate_edge': raw['edges'].append(dict(raw['edges'][0]))
    elif case == 'unknown_endpoint': raw['edges'][0]['target_node'] = 'missing'
    elif case == 'disconnected': raw['edges'].pop()
    elif case == 'unsupported_node': raw['nodes'][2]['node_type'] = 'shell'
    elif case == 'missing_llm': raw['nodes'][1]['node_type'] = 'validate'
    elif case == 'extra_input': raw['nodes'][2]['node_type'] = 'input'
    elif case == 'extra_output': raw['nodes'][2]['node_type'] = 'output'
    elif case == 'invented_agent': raw['nodes'][1]['config'] = {'asset_id': ID}
    elif case == 'invented_tool':
        raw['nodes'][2]['node_type'] = 'read_tool'
        raw['nodes'][2]['config'] = {'tool_id': 'invented'}
    elif case == 'secret_config': raw['nodes'][1]['config'] = {'api_key': 'placeholder'}
    elif case == 'url_config': raw['nodes'][1]['config'] = {'url': 'https://invalid.test'}
    elif case == 'nested_config': raw['nodes'][0]['config'] = {'input_key': {'password': 'placeholder'}}
    elif case == 'input_type': raw['nodes'][0]['config']['input_key'] = 1
    elif case == 'input_blank': raw['nodes'][0]['config']['input_key'] = ''
    elif case == 'input_invalid': raw['nodes'][0]['config']['input_key'] = 'some.path'
    elif case == 'node_nul': raw['nodes'][1]['node_id'] = '\0'
    elif case == 'node_blank': raw['nodes'][1]['node_id'] = ' '
    elif case == 'title_blank': raw['nodes'][1]['title'] = ' '
    elif case == 'extra_node_field': raw['nodes'][1]['provider'] = 'openai'
    elif case == 'extra_edge_field': raw['edges'][0]['condition'] = 'true'
    elif case == 'extra_top_field': raw['execute'] = True
    with pytest.raises(ValueError): validate_proposal('workflow', raw)


def test_invalid_target():
    with pytest.raises(ValueError, match='SCAFFOLD_TARGET_INVALID'):
        validate_proposal('tool', {})
