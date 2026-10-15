import {ApprovalReviewPanel} from './ApprovalReviewPanel';
import type {Tenant,User} from './types';
export function WorkflowApprovals(props:{tenant:Tenant;user:User;initialId?:string}){return <ApprovalReviewPanel {...props} kind="workflow"/>;}
