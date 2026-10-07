"""Private immutable UTF-8 sources. Authorization is required before calling read().

An atomic file addition and a database commit are separate operations. A failed
registration may leave a private orphan; it must never become a publication.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import time
from uuid import UUID, uuid4

MAX_BYTES = 128 * 1024
MAX_CHARACTERS = 40000
MEDIA_TYPES = frozenset({'text/plain', 'text/markdown'})


class SourceStorageError(ValueError):
    pass


def validate_source(content: bytes, title: str, media_type: str) -> str:
    if (type(content) is not bytes or not 1 <= len(content) <= MAX_BYTES
            or type(title) is not str or not 1 <= len(title) <= 200
            or not title.strip() or '\x00' in title or type(media_type) is not str or media_type not in MEDIA_TYPES):
        raise SourceStorageError('SOURCE_INVALID')
    try:
        text = content.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        raise SourceStorageError('SOURCE_INVALID') from None
    if not text.strip() or '\x00' in text or len(text) > MAX_CHARACTERS:
        raise SourceStorageError('SOURCE_INVALID')
    return text


def source_key(tenant_id: UUID, document_id: UUID, version_id: UUID) -> str:
    if not all(isinstance(v, UUID) for v in (tenant_id, document_id, version_id)):
        raise SourceStorageError('SOURCE_PATH_REJECTED')
    return f'tenants/{tenant_id}/documents/{document_id}/{version_id}/source'


@dataclass(frozen=True)
class StoredSource:
    object_key: str
    sha256: bytes
    byte_length: int
    character_length: int
    title: str
    media_type: str
    source_mapping: dict | None = None


class SourceStorage:
    def __init__(self, root: Path):
        self.root = Path(os.path.abspath(root))
        # Require canonical ancestors, rather than following a symlink to another store.
        if self.root.parent.resolve() != self.root.parent:
            raise SourceStorageError('SOURCE_PATH_REJECTED')
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError:
            raise SourceStorageError('SOURCE_PATH_REJECTED') from None
        fd = self._open_directory(self.root)
        os.close(fd)

    @staticmethod
    def _check(fd: int, directory: bool):
        info = os.fstat(fd)
        if (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
                or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
                or (not directory and info.st_nlink != 1)):
            raise SourceStorageError('SOURCE_PATH_REJECTED')

    @classmethod
    def _open_directory(cls, path, *, dir_fd=None):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
        except OSError:
            raise SourceStorageError('SOURCE_PATH_REJECTED') from None
        try:
            cls._check(fd, True)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @staticmethod
    def _parts(key: str):
        if type(key) is not str:
            raise SourceStorageError('SOURCE_PATH_REJECTED')
        parts = key.split('/')
        try:
            if (len(parts) != 6 or parts[0] != 'tenants' or parts[2] != 'documents' or parts[5] not in ('source','original')
                    or source_key(UUID(parts[1]), UUID(parts[3]), UUID(parts[4])) != "/".join(parts[:-1]+["source"])):
                raise ValueError()
        except (ValueError, TypeError):
            raise SourceStorageError('SOURCE_PATH_REJECTED') from None
        return parts

    def _version_directory(self, key: str, create: bool):
        parts = self._parts(key)
        fd = self._open_directory(self.root)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = self._open_directory(part, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except OSError:
            os.close(fd)
            raise SourceStorageError('SOURCE_PATH_REJECTED') from None
        except BaseException:
            os.close(fd)
            raise

    def write(self, tenant_id: UUID, document_id: UUID, version_id: UUID,
              content: bytes, title: str, media_type: str) -> StoredSource:
        text = validate_source(content, title, media_type)
        key = source_key(tenant_id, document_id, version_id)
        self._write_blob(key,content)
        return StoredSource(key, hashlib.sha256(content).digest(), len(content), len(text), title, media_type)

    def _write_blob(self,key,content):
        directory = self._version_directory(key, True)
        leaf=self._parts(key)[-1]
        temp = '.' + uuid4().hex + '.tmp'
        created = False
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            created = True
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # link is an atomic add-if-absent; rename would overwrite an existing source.
            try:
                os.link(temp, leaf, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            except FileExistsError:
                raise SourceStorageError('SOURCE_ALREADY_EXISTS') from None
            os.unlink(temp, dir_fd=directory)
            created = False
            os.fsync(directory)
        except SourceStorageError:
            raise
        except OSError:
            raise SourceStorageError('SOURCE_WRITE_FAILED') from None
        finally:
            if created:
                os.unlink(temp, dir_fd=directory)
            os.close(directory)

    def write_original(self,key,content,sha):
        if type(content) is not bytes or not 1<=len(content)<=MAX_BYTES or hashlib.sha256(content).digest()!=sha:raise SourceStorageError("SOURCE_INTEGRITY_FAILED")
        self._write_blob(key.rsplit("/",1)[0]+"/original",content)

    def _read_blob(self,key):
        directory=self._version_directory(key,False)
        try:
            fd=os.open(self._parts(key)[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            with os.fdopen(fd,"rb") as stream:
                self._check(stream.fileno(),False);return stream.read(MAX_BYTES+1)
        except OSError:raise SourceStorageError("SOURCE_UNAVAILABLE") from None
        finally:os.close(directory)

    def read_original(self,source):
        origin=validate_origin(source.source_mapping,source)
        if origin is None:raise SourceStorageError("SOURCE_INTEGRITY_FAILED")
        raw=self._read_blob(source.object_key.rsplit("/",1)[0]+"/original")
        if len(raw)!=origin["byte_length"] or hashlib.sha256(raw).hexdigest()!=origin["source_sha256"]:raise SourceStorageError("SOURCE_INTEGRITY_FAILED")
        return raw

    def read(self, source: StoredSource) -> bytes:
        directory = self._version_directory(source.object_key, False)
        try:
            try:
                fd = os.open('source', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            except OSError:
                raise SourceStorageError('SOURCE_UNAVAILABLE') from None
            with os.fdopen(fd, 'rb') as stream:
                self._check(stream.fileno(), False)
                content = stream.read(MAX_BYTES + 1)
            text = validate_source(content, source.title, source.media_type)
            if (len(content) != source.byte_length or len(text) != source.character_length
                    or hashlib.sha256(content).digest() != source.sha256):
                raise SourceStorageError('SOURCE_INTEGRITY_FAILED')
            if source.source_mapping and "origin" in source.source_mapping:
                validate_origin(source.source_mapping,source);self.read_original(source)
            return content
        finally:
            os.close(directory)

    def remove(self,key,*,minimum_age_seconds=0):
        """Remove both representations only after current deletion/orphan authorization."""
        directory=self._version_directory(key,False)
        try:
            existing=[]
            for leaf in ("source","original"):
                try:fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
                except FileNotFoundError:continue
                try:
                    self._check(fd,False)
                    if time.time()-os.fstat(fd).st_mtime<minimum_age_seconds:return 0
                    existing.append(leaf)
                finally:os.close(fd)
            for leaf in existing:
                try:os.unlink(leaf,dir_fd=directory)
                except FileNotFoundError:pass
            os.fsync(directory);return int(bool(existing))
        except OSError:raise SourceStorageError("SOURCE_REMOVE_FAILED") from None
        finally:os.close(directory)

    def source_keys(self, tenant_id: UUID):
        """Metadata-only inventory, no symlinks or source bytes. Caller must authorize tenant."""
        if type(tenant_id) is not UUID:raise SourceStorageError('SOURCE_PATH_REJECTED')
        root=self._open_directory(self.root);opened=[root]
        try:
            for part in ('tenants',str(tenant_id),'documents'):
                try:fd=self._open_directory(part,dir_fd=opened[-1])
                except SourceStorageError:
                    if part not in os.listdir(opened[-1]):return ()
                    raise
                opened.append(fd)
            result=[]
            for doc in sorted(os.listdir(opened[-1])):
                try:
                    if str(UUID(doc))!=doc:continue
                except ValueError:continue
                doc_fd=self._open_directory(doc,dir_fd=opened[-1])
                try:
                    for version in sorted(os.listdir(doc_fd)):
                        try:
                            if str(UUID(version))!=version:continue
                        except ValueError:continue
                        key=source_key(tenant_id,UUID(doc),UUID(version))
                        result.append(key)
                finally:os.close(doc_fd)
            return tuple(result)
        finally:
            for fd in reversed(opened):os.close(fd)


def validate_origin(mapping,source):
    from app.documents.formats import DOCX_MEDIA_TYPE,DOCX_PARSER_VERSION
    from app.documents.docx_locations import validate_docx_locations
    if not mapping or "origin" not in mapping:return None
    origin=mapping["origin"]
    try:
        if type(origin) is not dict:raise ValueError()
        media=origin.get("media_type")
        field="pages" if media=="application/pdf" else "locations" if media==DOCX_MEDIA_TYPE else None
        version="pypdf-6.19.0" if media=="application/pdf" else DOCX_PARSER_VERSION
        if field is None or set(origin)!={"media_type","source_sha256","byte_length","parser_version","text_sha256",field} or origin["parser_version"]!=version or origin["text_sha256"]!=source.sha256.hex() or type(origin["byte_length"]) is not int or not 1<=origin["byte_length"]<=MAX_BYTES or len(bytes.fromhex(origin["source_sha256"]))!=32:raise ValueError()
        if field=="locations":validate_docx_locations(origin["locations"],source.character_length)
        else:
            pages=origin["pages"];previous=-2
            if not 1<=len(pages)<=20:raise ValueError()
            for n,p in enumerate(pages,1):
                if set(p)!={"page","start","end"} or any(type(x) is not int for x in p.values()) or p["page"]!=n or p["start"]!=previous+2 or not p["start"]<p["end"]<=source.character_length:raise ValueError()
                previous=p["end"]
            if previous!=source.character_length:raise ValueError()
    except (ValueError,TypeError,KeyError):raise SourceStorageError("SOURCE_INTEGRITY_FAILED") from None
    return origin
