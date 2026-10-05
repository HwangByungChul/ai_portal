from pathlib import Path
import ast
import pytest
from c02_corpus_support import corpus_plans,compare_corpus,ROOT

@pytest.fixture(scope='module')
def corpus():return corpus_plans()

@pytest.mark.parametrize('index',range(7),ids=['A-R1','A-R2','A-private','B-R1','B-private','shared-v1','shared-v2'])
def test_actual_raw_document_outputs_match_evaluator_after_processing(corpus,index):
    manifest,rows=corpus;doc,raw,plan=rows[index]
    result=compare_corpus(manifest,doc,raw,plan)
    assert result['expected_relations_match'] and result['original_intervals_match']
    assert len(plan.batches)==1 and sum(c.token_count for c in plan.chunks)<=4096
    assert all('EV-' not in c.text and '<a ' not in c.text for c in plan.chunks)


def test_core_has_no_authority_provider_file_or_evaluator_dependency():
    prohibited={'openai','psycopg','psycopg_pool','httpx','httpx2','requests','socket','os','pathlib','app','tests'}
    for file in (ROOT/'src/common_core').rglob('*.py'):
        tree=ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[a.name.split('.')[0] for a in node.names] if isinstance(node,ast.Import) else [(node.module or '').split('.')[0]]
                assert not prohibited.intersection(names)
            if isinstance(node,ast.Call):
                assert not (isinstance(node.func,ast.Name) and node.func.id=='open')
                assert not (isinstance(node.func,ast.Attribute) and node.func.attr in {'read_text','read_bytes','connect','request','getenv'})
        assert 'document_manifest' not in file.read_text() and 'EV-A-' not in file.read_text() and 'Q-001' not in file.read_text()
