from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,StrictStr,StrictInt,model_validator
from app.assets.routes import AssetConfig
from app.conversations.routes import DocumentRef
from app.builder.templates import TOKEN,compile_template


class Profile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:StrictInt=1
    system_prompt:StrictStr=Field(min_length=1,max_length=2000)
    developer_prompt:StrictStr=Field(default='',max_length=2000)
    user_template:StrictStr=Field(min_length=1,max_length=2000)
    model_ref:StrictStr
    document_refs:list[DocumentRef]=Field(default_factory=list,max_length=5)

    @model_validator(mode='after')
    def validate_profile(self):
        if self.schema_version!=1:raise ValueError('PROFILE_INVALID')
        from app.builder.model_contracts import MODEL_CONTRACTS
        from app.ai.model_registry import APPROVED_MODELS
        if self.model_ref not in MODEL_CONTRACTS and self.model_ref not in APPROVED_MODELS:
            raise ValueError('PROFILE_INVALID')
        if self.model_ref in APPROVED_MODELS and not APPROVED_MODELS[self.model_ref].enabled:
            raise ValueError('PROFILE_INVALID')
        names=set()
        for text in (self.system_prompt,self.developer_prompt,self.user_template):
            if '\x00' in text:raise ValueError('PROFILE_INVALID')
            try:text.encode('utf-8')
            except UnicodeError:raise ValueError('PROFILE_INVALID') from None
            if not text and text==self.developer_prompt:continue
            bindings=set(TOKEN.findall(text));names.update(bindings)
            compile_template(text,{name:'검증' for name in bindings})
        if len(names)>20 or len({(ref.document_id,ref.version_id) for ref in self.document_refs})!=len(self.document_refs):raise ValueError('PROFILE_INVALID')
        return self


class SaveProfile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    config:AssetConfig
    profile:Profile

    @model_validator(mode='after')
    def match_config(self):
        if self.config.instructions!=self.profile.system_prompt:
            raise ValueError('PROFILE_INVALID')
        expected_default = 'default_' + self.config.execution_kind
        from app.ai.model_registry import APPROVED_MODELS
        if self.profile.model_ref != expected_default and self.profile.model_ref not in APPROVED_MODELS:
            raise ValueError('PROFILE_INVALID')
        if self.profile.model_ref in APPROVED_MODELS:
            m = APPROVED_MODELS[self.profile.model_ref]
            if not m.enabled:
                raise ValueError('PROFILE_INVALID')
            if self.config.execution_kind == 'rules_rag' and 'rag' not in m.capabilities:
                raise ValueError('PROFILE_INVALID')
            if self.config.execution_kind == 'general' and 'chat' not in m.capabilities:
                raise ValueError('PROFILE_INVALID')
        if self.config.execution_kind=='general' and self.profile.document_refs:raise ValueError('PROFILE_INVALID')
        return self


class AppendProfile(SaveProfile):
    expected_revision:StrictInt=Field(ge=1,le=1000)


class CloneProfile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    source_version_id:UUID


class ProfilePreview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    values:dict[str,StrictStr]=Field(default_factory=dict,max_length=20)


def compose(profile:dict,values:dict[str,str]):
    fields=(('system','system_prompt'),('developer','developer_prompt'),('user','user_template'))
    names=sorted({name for _,key in fields for name in TOKEN.findall(profile[key])})
    from app.errors import AppError
    if set(values)!=set(names):raise AppError('BUILDER_TEMPLATE_INVALID',422)
    messages=[]
    for role,key in fields:
        template=profile[key]
        if template:
            _,content=compile_template(template,{name:values[name] for name in set(TOKEN.findall(template))})
            messages.append({'role':role,'content':content})
    text=''.join(x['content'] for x in messages)
    if len(text)>8000 or len(text.encode('utf-8'))>24000:raise AppError('BUILDER_TEMPLATE_INVALID',422)
    return names,messages
