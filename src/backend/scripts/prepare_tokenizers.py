"""Explicit public BPE preparation; never invoked automatically by the application."""
import hashlib
import json
import os
from urllib.request import urlopen
from app.ai.token_limits import CACHE, ENCODINGS, encoding


def prepare() -> dict:
    CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if CACHE.is_symlink():
        raise ValueError('TOKENIZER_CACHE_REJECTED')
    os.chmod(CACHE, 0o700)
    rows = []
    for name, metadata in ENCODINGS.items():
        file = CACHE / (name + '.tiktoken')
        if file.is_symlink():
            raise ValueError('TOKENIZER_CACHE_REJECTED')
        try:
            valid = hashlib.sha256(file.read_bytes()).hexdigest() == metadata['sha256']
        except OSError:
            valid = False
        if not valid:
            with urlopen(metadata['url'], timeout=30) as response:
                data = response.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != metadata['sha256']:
                raise ValueError('TOKENIZER_HASH_REJECTED')
            temporary = file.with_suffix('.pending')
            fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.replace(temporary, file)
        os.chmod(file, 0o600)
        codec = encoding(name)
        rows.append({'encoding':name,'sha256':metadata['sha256'],'vocabulary':codec.n_vocab,'status':'ready'})
    return {'status':'ready','tiktoken':'0.14.0','encodings':rows,'paid_ai_calls':0}

if __name__ == '__main__':
    try:
        print(json.dumps(prepare()))
    except Exception:
        print(json.dumps({'status':'failed','code':'TOKENIZER_PREPARATION_FAILED'}))
        raise SystemExit(1)
