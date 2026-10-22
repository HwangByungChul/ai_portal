export * from '../packages/api-contract/src/types';
import type {AssetConfig,DocumentRef,WorkflowNodeInfo,WorkflowEdgeInfo} from '../packages/api-contract/src/types';

export interface BuilderScaffoldProfile {
  schema_version:1;
  system_prompt:string;
  developer_prompt:string;
  user_template:string;
  model_ref:string;
  document_refs:DocumentRef[];
}
export interface AgentScaffoldProposal {
  config:AssetConfig;
  profile:BuilderScaffoldProfile;
  missing_questions:string[];
  warnings:string[];
}
export interface BuilderScaffoldReceipt {
  proposal_id:string;
  state:'admitted'|'generating'|'ready'|'failed'|'discarded';
  revision:number;
  proposal?:AgentScaffoldProposal|null;
  error_code?:string|null;
}

export interface WorkflowScaffoldProposal {
  name:string;
  description:string;
  nodes:WorkflowNodeInfo[];
  edges:WorkflowEdgeInfo[];
  missing_questions:string[];
  warnings:string[];
}

export interface WorkflowScaffoldReceipt {
  proposal_id:string;
  target:'workflow';
  state:'admitted'|'generating'|'ready'|'failed'|'discarded';
  revision:number;
  proposal?:WorkflowScaffoldProposal|null;
  error_code?:string|null;
}
