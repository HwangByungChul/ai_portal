import type { ToolDescriptor } from './types';

export function toolReviewLabel(descriptor: Pick<ToolDescriptor, 'approval_scope' | 'risk_class'>): string {
  if (descriptor.approval_scope === 'registration_review_only') {
    return descriptor.risk_class === 'financial_side_effect' ? '동적 등록 검토 · 고위험' : '동적 등록 검토';
  }
  return descriptor.risk_class === 'financial_side_effect' ? '고위험 Tool 검토' : '읽기 전용';
}
