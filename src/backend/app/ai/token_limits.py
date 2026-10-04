"""Offline encodings pinned to tiktoken 0.14.0; no lazy network download."""
import hashlib
from pathlib import Path
from functools import lru_cache
import tiktoken
from tiktoken.load import load_tiktoken_bpe

CACHE = Path(__file__).resolve().parents[2] / '.runtime' / 'tokenizer-cache'
# Metadata extracted from pinned tiktoken_ext.openai_public; hashes are its public BPE checksums.
ENCODINGS = {'o200k_base': {'url': 'https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken', 'sha256': '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d', 'pattern': "[^\\r\\n\\p{L}\\p{N}]?[\\p{Lu}\\p{Lt}\\p{Lm}\\p{Lo}\\p{M}]*[\\p{Ll}\\p{Lm}\\p{Lo}\\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?|[^\\r\\n\\p{L}\\p{N}]?[\\p{Lu}\\p{Lt}\\p{Lm}\\p{Lo}\\p{M}]+[\\p{Ll}\\p{Lm}\\p{Lo}\\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?|\\p{N}{1,3}| ?[^\\s\\p{L}\\p{N}]+[\\r\\n/]*|\\s*[\\r\\n]+|\\s+(?!\\S)|\\s+", 'special_tokens': {'<|endoftext|>': 199999, '<|endofprompt|>': 200018}}, 'cl100k_base': {'url': 'https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken', 'sha256': '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7', 'pattern': "'(?i:[sdmt]|ll|ve|re)|[^\\r\\n\\p{L}\\p{N}]?+\\p{L}++|\\p{N}{1,3}+| ?[^\\s\\p{L}\\p{N}]++[\\r\\n]*+|\\s++$|\\s*[\\r\\n]|\\s+(?!\\S)|\\s", 'special_tokens': {'<|endoftext|>': 100257, '<|fim_prefix|>': 100258, '<|fim_middle|>': 100259, '<|fim_suffix|>': 100260, '<|endofprompt|>': 100276}}}


class TokenizerNotReady(ValueError):
    pass


@lru_cache(maxsize=4)
def _construct(name: str, file: str, digest: str) -> tiktoken.Encoding:
    metadata = ENCODINGS[name]
    return tiktoken.Encoding(name=name, pat_str=metadata['pattern'], special_tokens=metadata['special_tokens'],
        mergeable_ranks=load_tiktoken_bpe(file, expected_hash=digest))


def encoding(name: str, cache: Path = CACHE) -> tiktoken.Encoding:
    if name not in ENCODINGS:
        raise TokenizerNotReady('TOKENIZER_NOT_READY')
    file = cache / (name + '.tiktoken')
    try:
        # Validate on every use, even if an encoding was previously constructed in this process.
        if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != ENCODINGS[name]['sha256']:
            raise TokenizerNotReady('TOKENIZER_NOT_READY')
    except OSError:
        raise TokenizerNotReady('TOKENIZER_NOT_READY') from None
    return _construct(name, str(file), ENCODINGS[name]['sha256'])


def _text(value: str, *, maximum: int | None = None, bytes_maximum: int | None = None) -> None:
    if not isinstance(value, str) or not value.strip() or (maximum is not None and len(value) > maximum):
        raise ValueError('INPUT_REJECTED')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise ValueError('INPUT_REJECTED') from None
    if bytes_maximum is not None and size > bytes_maximum:
        raise ValueError('INPUT_REJECTED')


def general_token_count(messages: list[dict], *, cache: Path = CACHE) -> int:
    codec = encoding('o200k_base', cache)
    # Official chat framing estimate plus 32 conservative tokens; real usage is authoritative.
    return 3 + 32 + sum(3 + sum(len(codec.encode(value, disallowed_special=()))
        for value in (m['role'], m['content'])) for m in messages)


def validate_general_input(instructions: str, history: list[dict], prompt: str, *, cache: Path = CACHE) -> list[dict]:
    _text(instructions, maximum=2000)
    _text(prompt, maximum=4000, bytes_maximum=16384)
    if not isinstance(history, list):
        raise ValueError('INPUT_REJECTED')
    for message in history:
        if (not isinstance(message, dict) or set(message) != {'role','content'}
                or message['role'] not in ('user','assistant')):
            raise ValueError('INPUT_REJECTED')
        _text(message['content'], bytes_maximum=65536)
    selected = [dict(m) for m in history[-6:]]
    mandatory = [{'role':'system','content':instructions},{'role':'user','content':prompt}]
    if general_token_count(mandatory, cache=cache) > 6000:
        raise ValueError('INPUT_TOKEN_LIMIT')
    while True:
        messages = [mandatory[0], *selected, mandatory[1]]
        if general_token_count(messages, cache=cache) <= 6000:
            return messages
        selected.pop(0)  # Drop only whole old messages; never cut the instructions/current prompt.


def count_embedding_tokens(text: str, *, cache: Path = CACHE) -> int:
    _text(text)
    return len(encoding('cl100k_base', cache).encode(text, disallowed_special=()))
