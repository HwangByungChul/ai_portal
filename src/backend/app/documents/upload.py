"""Bounded two-part multipart form. Filename and external location are not authority."""
import json
from email.parser import BytesParser
from email.policy import default
from uuid import UUID
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictStr,ValidationError
from app.errors import AppError

MAX_UPLOAD_BODY=147456

class UploadMetadata(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_upload_id:UUID
    title:StrictStr=Field(min_length=1,max_length=200)
    media_type:Literal['text/plain','text/markdown','application/pdf']
    visibility:Literal['org','private']='org'
    owner_user_id:UUID|None=None
    reader_ids:list[UUID]=Field(default_factory=list,max_length=20)

class UserUploadMetadata(BaseModel):
    model_config=ConfigDict(extra="forbid")
    client_upload_id:UUID
    title:StrictStr=Field(min_length=1,max_length=200)
    media_type:Literal["text/plain","text/markdown","application/pdf"]

class VersionMetadata(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_upload_id:UUID
    title:StrictStr=Field(min_length=1,max_length=200)
    media_type:Literal['text/plain','text/markdown','application/pdf']
    expected_revision:StrictInt=Field(ge=1,le=9223372036854775807)


def parse_upload(body,content_type,version=False,*,personal=False):
    if type(body) is not bytes or len(body)>MAX_UPLOAD_BODY or '\r' in content_type or '\n' in content_type:
        raise AppError('PAYLOAD_TOO_LARGE',413)
    try:
        message=BytesParser(policy=default).parsebytes(b'Content-Type: '+content_type.encode('ascii')+b'\r\nMIME-Version: 1.0\r\n\r\n'+body)
        if message.get_content_type()!='multipart/form-data' or message.defects or not message.is_multipart():raise ValueError()
        parts=list(message.iter_parts())
        if len(parts)!=2:raise ValueError()
        values={};filename=None
        for part in parts:
            if part.defects or part.is_multipart() or part.get_content_disposition()!='form-data' or part.get_all('Content-Disposition') is None or len(part.get_all('Content-Disposition'))!=1 or part.get('Content-Transfer-Encoding') is not None:raise ValueError()
            name=part.get_param('name',header='Content-Disposition')
            if name not in ('file','metadata') or name in values:raise ValueError()
            values[name]=part.get_payload(decode=True)
            if name=='file':filename=part.get_filename();file_media=part.get_content_type()
        if set(values)!= {'file','metadata'} or len(values['metadata'])>8192:raise ValueError()
        data=json.loads(values['metadata'],object_pairs_hook=_unique)
        meta=(UserUploadMetadata if personal else VersionMetadata if version else UploadMetadata).model_validate(data)
        if meta.media_type=='application/pdf' and (type(filename) is not str or not filename.lower().endswith('.pdf') or file_media!='application/pdf' or not values['file'].startswith(b'%PDF-')):raise ValueError()
        if meta.media_type!='application/pdf' and values['file'].startswith(b'%PDF-'):raise ValueError()
        return meta.model_dump(),values['file']
    except (ValueError,UnicodeError,TypeError,ValidationError,KeyError):raise AppError('REQUEST_INVALID',422) from None


def _unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError()
        result[k]=v
    return result
