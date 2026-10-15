"""Approved DAGs reference immutable assets; no client-selected provider or prompt."""
import heapq
from typing import Annotated,Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictStr,model_validator

Name=Annotated[StrictStr,Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,39}$')]
Text=Annotated[StrictStr,Field(max_length=4000)]

class StrictModel(BaseModel):model_config=ConfigDict(extra='forbid')
class NodeReference(StrictModel):
    node_id:Name
    path:list[Annotated[StrictStr,Field(min_length=1,max_length=40)]]=Field(default_factory=list,max_length=4)
Binding=Text|NodeReference
class InputConfig(StrictModel):input_key:Name='query'
class ToolConfig(StrictModel):
    tool_id:Literal['financial_product_lookup','kb_rule_query','data_view_reader']
    version_digest:Annotated[StrictStr,Field(pattern=r'^[0-9a-f]{64}$')]
    arguments:dict[Name,Binding]=Field(default_factory=dict,max_length=20)
class LlmConfig(StrictModel):
    asset_id:UUID
    version_id:UUID
    publication_revision:StrictInt=Field(ge=1,le=9223372036854775806)
    values:dict[Name,Binding]=Field(default_factory=dict,max_length=20)
class SourceConfig(StrictModel):source:NodeReference
CONFIGS={'input':InputConfig,'read_tool':ToolConfig,'llm':LlmConfig,'validate':SourceConfig,'output':SourceConfig}
class ApprovedNode(StrictModel):
    node_id:Name
    node_type:Literal['input','read_tool','llm','validate','output']
    title:Annotated[StrictStr,Field(min_length=1,max_length=128)]
    config:dict
    @model_validator(mode='after')
    def strict_config(self):
        self.config=CONFIGS[self.node_type].model_validate(self.config).model_dump(mode='json')
        return self
class ApprovedEdge(StrictModel):
    source_node:Name
    target_node:Name
class ApprovedWorkflow(StrictModel):
    workflow_id:UUID
    name:Annotated[StrictStr,Field(min_length=1,max_length=120)]
    description:Annotated[StrictStr,Field(max_length=500)]=''
    nodes:list[ApprovedNode]=Field(min_length=3,max_length=20)
    edges:list[ApprovedEdge]=Field(min_length=2,max_length=30)
    max_steps:StrictInt=Field(default=20,ge=3,le=20)
    @model_validator(mode='after')
    def graph(self):
        ids={n.node_id for n in self.nodes}
        if len(ids)!=len(self.nodes) or self.max_steps<len(self.nodes):raise ValueError('WORKFLOW_INVALID')
        edge_set={(e.source_node,e.target_node) for e in self.edges}
        if len(edge_set)!=len(self.edges) or any(a not in ids or b not in ids or a==b for a,b in edge_set):raise ValueError('WORKFLOW_INVALID')
        inputs=[n.node_id for n in self.nodes if n.node_type=='input'];outputs=[n.node_id for n in self.nodes if n.node_type=='output']
        if len(inputs)!=1 or len(outputs)!=1 or not any(n.node_type=='llm' for n in self.nodes):raise ValueError('WORKFLOW_INVALID')
        ancestors={i:set() for i in ids};ordered=self.order()
        if len(ordered)!=len(ids):raise ValueError('WORKFLOW_INVALID')
        for node_id in ordered:
            for a,b in edge_set:
                if b==node_id:ancestors[b].update(ancestors[a]|{a})
        if any(n!=inputs[0] and inputs[0] not in ancestors[n] for n in ids) or ancestors[outputs[0]]!=ids-{outputs[0]}:raise ValueError('WORKFLOW_DISCONNECTED')
        for node in self.nodes:
            bindings=(node.config.get('values') or node.config.get('arguments') or {})
            if 'source' in node.config:bindings={'source':node.config['source']}
            for value in bindings.values():
                if isinstance(value,dict) and value['node_id'] not in ancestors[node.node_id]:raise ValueError('WORKFLOW_REFERENCE_INVALID')
        return self
    def order(self):
        ids={n.node_id for n in self.nodes};degrees={i:0 for i in ids};adj={i:[] for i in ids}
        for e in self.edges:
            if e.source_node not in ids or e.target_node not in ids:return []
            adj[e.source_node].append(e.target_node);degrees[e.target_node]+=1
        queue=[i for i in ids if degrees[i]==0];heapq.heapify(queue);ordered=[]
        while queue:
            i=heapq.heappop(queue);ordered.append(i)
            for b in sorted(adj[i]):
                degrees[b]-=1
                if degrees[b]==0:heapq.heappush(queue,b)
        return ordered
