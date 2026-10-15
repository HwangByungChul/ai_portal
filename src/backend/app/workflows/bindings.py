"""Bounded values from immutable literals or successful predecessor checkpoints."""
import json
from uuid import UUID
import hashlib
from app.errors import AppError


def child_request_id(parent,node,kind):
    return UUID(hashlib.md5((str(parent)+':'+node+':'+kind).encode(),usedforsecurity=False).hexdigest())


def resolve(binding,results):
    if isinstance(binding,str):return binding
    try:
        value=results[binding['node_id']]
        for key in binding.get('path',[]):
            if isinstance(value,dict):value=value[key]
            elif isinstance(value,list) and key.isdecimal():value=value[int(key)]
            else:raise KeyError(key)
        encoded=json.dumps(value,ensure_ascii=False,allow_nan=False)
        if len(encoded.encode())>16384:raise ValueError('limit')
        return value
    except (KeyError,IndexError,TypeError,ValueError):raise AppError('WORKFLOW_BINDING_INVALID',422) from None


def resolve_mapping(mapping,results):
    return {key:resolve(value,results) for key,value in mapping.items()}
