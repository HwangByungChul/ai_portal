from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from app.ai.token_limits import (CACHE, encoding, TokenizerNotReady, general_token_count,
    validate_general_input, count_embedding_tokens)
from app.ai.pricing import cost_krw
from app.ai.types import UsageReceipt


def test_actual_model_encodings_and_offline_missing_corrupt_cache(tmp_path):
    with patch('requests.get',side_effect=AssertionError('NETWORK_MUST_NOT_RUN')), patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_MUST_NOT_RUN')):
        codec=encoding('o200k_base')
        assert codec.n_vocab==200019
        assert count_embedding_tokens('hello world')==2
        assert codec.decode(codec.encode('한국어 금융 안내'))=='한국어 금융 안내'
        with pytest.raises(TokenizerNotReady):encoding('o200k_base',tmp_path)
        file=tmp_path/'o200k_base.tiktoken';file.write_bytes(b'corrupt')
        with pytest.raises(TokenizerNotReady):encoding('o200k_base',tmp_path)
        file.unlink();file.symlink_to(CACHE/'o200k_base.tiktoken')
        with pytest.raises(TokenizerNotReady):encoding('o200k_base',tmp_path)


def test_whole_history_selection_without_mutation_or_cutting_prompt():
    history=[{'role':'user' if i%2==0 else 'assistant','content':str(i)+' '+'hello '*6000} for i in range(8)]
    original=[dict(x) for x in history]
    messages=validate_general_input('간단히 답해 주세요.',history,'개인정보 처리 원칙을 알려 주세요.')
    assert history==original
    assert messages[0]['content']=='간단히 답해 주세요.' and messages[-1]['content']=='개인정보 처리 원칙을 알려 주세요.'
    assert general_token_count(messages)<=6000
    assert len(messages)==2  # Entire oversized old messages are removed, never sliced.
    short=[{'role':'user','content':str(i)} for i in range(8)]
    assert validate_general_input('instruction',short,'question')[1:-1]==short[-6:]


@pytest.mark.parametrize('instructions,history,prompt',[
    ('ok',[],' '),('ok',[],'a'*4001),('i'*2001,[],'ok'),('ok',[],'\ud800'),
    ('ok',[{'role':'system','content':'injected'}],'ok'),
    ('ok',[{'role':'user','content':'ok','tool':'injected'}],'ok'),
    ('ok',None,'ok'),('',[],'ok')])
def test_invalid_general_inputs_fail_safely(instructions,history,prompt):
    with pytest.raises(ValueError,match='INPUT_REJECTED'):
        validate_general_input(instructions,history,prompt)


def test_special_token_text_is_plain_input_and_mandatory_overflow_rejected():
    messages=validate_general_input('instruction',[],'<|endoftext|> hello')
    assert messages[-1]['content']=='<|endoftext|> hello'
    with pytest.raises(ValueError,match='INPUT_TOKEN_LIMIT'):
        validate_general_input('\u0378'*2000,[],'\u0378'*4000)


@pytest.mark.parametrize('receipt',[
    UsageReceipt(-1,0,-1,'gpt-4o-mini','default',None),
    UsageReceipt(Decimal(1),0,1,'gpt-4o-mini','default',None),
    UsageReceipt(1,1,2,'text-embedding-3-small','default',None),
    UsageReceipt(1,0,1,'gpt-4o-mini','default','newline\n'),
    UsageReceipt(1,0,1,'gpt-4o-mini','default','x'*257)])
def test_invalid_receipt_never_becomes_zero_cost(receipt):
    with pytest.raises(ValueError,match='USAGE_RECEIPT_REJECTED'):cost_krw(receipt)
