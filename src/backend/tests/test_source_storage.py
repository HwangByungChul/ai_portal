from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import os
import stat
from uuid import uuid4
import pytest
from app.documents.storage import SourceStorage,SourceStorageError,StoredSource,validate_source,source_key

@pytest.fixture
def storage(tmp_path):
    # pytest temporary ancestors may be '/tmp'; the storage contract uses canonical paths.
    return SourceStorage(tmp_path.resolve()/'private-sources')


def write(storage,content=b'synthetic',title='sample',media_type='text/plain',ids=None):
    return storage.write(*(ids or (uuid4(),uuid4(),uuid4())),content,title,media_type)

@pytest.mark.parametrize('media',['text/plain','text/markdown'])
def test_roundtrip_private_permissions_and_literal_text(storage,media):
    content='<script>never executed</script>\n---\nrole: admin\n가나다'.encode()
    src=write(storage,content,media_type=media)
    assert storage.read(src)==content
    path=storage.root/src.object_key
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    for p in [storage.root,*list(path.parents)[:5]]:assert stat.S_IMODE(p.stat().st_mode)==0o700

@pytest.mark.parametrize('content,title,media',[ (b'', 't','text/plain'),(b' '*4,'t','text/plain'),(b'\xff','t','text/plain'),(b'a\x00b','t','text/plain'),(b'a'*40001,'t','text/plain'),('😀'.encode()*32769,'t','text/plain'),(b'a','', 'text/plain'),(b'a','t'*201,'text/plain'),(b'a','t','text/html'),(b'a','t\x00','text/plain')])
def test_reject_invalid_before_any_files(storage,content,title,media):
    with pytest.raises(SourceStorageError,match='SOURCE_INVALID'):write(storage,content,title,media)
    assert list(storage.root.iterdir())==[]

@pytest.mark.parametrize('content',['가'*40000,'😀'*32768,'a'*40000])
def test_valid_size_and_character_boundaries(storage,content):
    src=write(storage,content.encode());assert storage.read(src)==content.encode()


def test_overwrite_and_concurrent_write_leave_no_temp(storage):
    ids=(uuid4(),uuid4(),uuid4())
    def attempt():
        try:return write(storage,ids=ids)
        except SourceStorageError as e:return str(e)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    assert sum(isinstance(x,StoredSource) for x in results)==1 and 'SOURCE_ALREADY_EXISTS' in results
    src=next(x for x in results if isinstance(x,StoredSource));assert storage.read(src)==b'synthetic'
    assert [p.name for p in (storage.root/src.object_key).parent.iterdir()]==['source']
    with pytest.raises(SourceStorageError,match='SOURCE_ALREADY_EXISTS'):write(storage,b'changed',ids=ids)
    assert storage.read(src)==b'synthetic'

@pytest.mark.parametrize('key',['../../outside','/absolute','tenants/invalid/documents/invalid/invalid/source','tenants/00000000000000000000000000000000/documents/00000000-0000-0000-0000-000000000000/00000000-0000-0000-0000-000000000000/source'])
def test_noncanonical_paths_rejected(storage,key):
    src=write(storage)
    with pytest.raises(SourceStorageError,match='SOURCE_PATH_REJECTED'):storage.read(replace(src,object_key=key))

@pytest.mark.parametrize('attack',['directory_link','source_link','hard_link','broad_mode','corruption'])
def test_filesystem_bypass_and_integrity(storage,tmp_path,attack):
    src=write(storage);path=storage.root/src.object_key
    if attack=='directory_link':
        directory=path.parent;relocated=directory.with_name('relocated');directory.rename(relocated);directory.symlink_to(relocated,target_is_directory=True)
    elif attack=='source_link':
        relocated=path.with_name('other');path.rename(relocated);path.symlink_to(relocated)
    elif attack=='hard_link':os.link(path,path.with_name('other'))
    elif attack=='broad_mode':path.chmod(0o644)
    else:path.write_bytes(b'corrupted')
    with pytest.raises(SourceStorageError):storage.read(src)


def test_storage_root_symlink_and_untrusted_permissions_rejected(tmp_path):
    root=tmp_path.resolve()/'target';root.mkdir(mode=0o700);link=tmp_path.resolve()/'link';link.symlink_to(root,target_is_directory=True)
    with pytest.raises(SourceStorageError):SourceStorage(link)
    root.chmod(0o755)
    with pytest.raises(SourceStorageError):SourceStorage(root)


def test_private_orphan_has_no_publication_side_effect(storage):
    src=write(storage)
    # File storage has no DB/HTTP/provider dependency. A failed registration stays private.
    assert storage.read(src)==b'synthetic'
    assert not list(storage.root.rglob('*.tmp'))
