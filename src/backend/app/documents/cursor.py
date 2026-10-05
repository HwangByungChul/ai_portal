"""Opaque cursor bound to current tenant, principal and list kind."""
import base64
import hashlib
import hmac
import json
from uuid import UUID
from app.errors import AppError

def encode_cursor(secret,ctx,kind,value):
    if value is None:return None
    data=json.dumps([str(ctx.tenant_id),str(ctx.user_id),kind,str(value)],separators=(',',':')).encode()
    mac=hmac.new(secret.encode(),b'document-cursor:'+data,hashlib.sha256).digest()
    return base64.urlsafe_b64encode(data+mac).decode().rstrip('=')

def decode_cursor(secret,ctx,kind,value):
    if value is None:return None
    try:
        if len(value)>512:raise ValueError()
        raw=base64.b64decode(value+'='*((-len(value))%4),altchars=b'-_',validate=True);data,mac=raw[:-32],raw[-32:]
        if not hmac.compare_digest(hmac.new(secret.encode(),b'document-cursor:'+data,hashlib.sha256).digest(),mac):raise ValueError()
        row=json.loads(data)
        if row[:3]!=[str(ctx.tenant_id),str(ctx.user_id),kind] or len(row)!=4:raise ValueError()
        return UUID(row[3])
    except (ValueError,TypeError,UnicodeError):raise AppError('REQUEST_INVALID',422) from None
