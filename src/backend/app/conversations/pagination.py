"""Opaque signed positions bound to the validated owner, tenant and list target."""
import base64
from datetime import datetime
import hashlib
import hmac
import json
from uuid import UUID
from app.errors import AppError


def binding(ctx,kind,target):
    return [str(ctx.user_id),str(ctx.tenant_id),kind,str(target) if target else None]


def encode_cursor(secret,ctx,kind,target,row):
    key='conversation_id' if kind=='conversations' else 'message_id'
    data={'binding':binding(ctx,kind,target),'position':{'created_at':row['created_at'],'id':row[key]}}
    raw=json.dumps(data,ensure_ascii=True,separators=(',',':'),sort_keys=True).encode()
    payload=base64.urlsafe_b64encode(raw).rstrip(b'=')
    digest=hmac.new(secret.encode('ascii'),b'conversation-cursor-v1:'+payload,hashlib.sha256).digest()
    return (payload+b'.'+base64.urlsafe_b64encode(digest).rstrip(b'=')).decode('ascii')


def decode_cursor(secret,ctx,kind,target,cursor):
    if cursor is None:return None
    try:
        if len(cursor)>1024 or not cursor.isascii():raise ValueError()
        payload,signature=cursor.encode('ascii').split(b'.')
        expected=hmac.new(secret.encode('ascii'),b'conversation-cursor-v1:'+payload,hashlib.sha256).digest()
        supplied=base64.b64decode(signature+b'='*(-len(signature)%4),altchars=b'-_',validate=True)
        if not hmac.compare_digest(expected,supplied):raise ValueError()
        data=json.loads(base64.b64decode(payload+b'='*(-len(payload)%4),altchars=b'-_',validate=True))
        if set(data)!={'binding','position'} or data['binding']!=binding(ctx,kind,target):raise ValueError()
        position=data['position']
        if set(position)!={'created_at','id'} or not isinstance(position['created_at'],str):raise ValueError()
        if datetime.fromisoformat(position['created_at']).tzinfo is None:raise ValueError()
        UUID(position['id'])
        return position
    except (ValueError,TypeError,KeyError,AttributeError,UnicodeError):
        raise AppError('REQUEST_INVALID',422) from None
