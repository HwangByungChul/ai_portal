import {ApprovalReviewPanel} from './ApprovalReviewPanel';
import type {Tenant,User} from './types';
export function ToolApprovals(props:{tenant:Tenant;user:User;initialId?:string}){return <ApprovalReviewPanel {...props} kind="tool"/>;}
