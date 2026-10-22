import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { toolReviewLabel } from '../src/toolReviewLabel.ts';

test('dynamic financial requests identify registration review and high risk', () => {
  assert.equal(toolReviewLabel({
    approval_scope: 'registration_review_only', risk_class: 'financial_side_effect',
  }), '동적 등록 검토 · 고위험');
});

test('registration review with missing risk classification never claims read only', () => {
  assert.equal(toolReviewLabel({ approval_scope: 'registration_review_only' }), '동적 등록 검토');
});

test('financial risk without a registration scope still never claims read only', () => {
  assert.equal(toolReviewLabel({ risk_class: 'financial_side_effect' }), '고위험 Tool 검토');
});

test('existing static Tool request label is preserved', () => {
  assert.equal(toolReviewLabel({}), '읽기 전용');
});

test('detail fallback uses the descriptor label and preserves mode and timeout', () => {
  const panel = readFileSync(new URL('../src/ApprovalReviewPanel.tsx', import.meta.url), 'utf8');
  assert.match(panel, /\) : \(\s*<div>\s*<p>\{toolReviewLabel\(detail\.request\.descriptor\)\} · \{modeLabel\(detail\.request\.descriptor\.mode\)\} · 제한 시간 \{detail\.request\.descriptor\.timeout_seconds\}초<\/p>/);
});

test('list uses descriptor label while approval retains server capability and validation guards', () => {
  const panel = readFileSync(new URL('../src/ApprovalReviewPanel.tsx', import.meta.url), 'utf8');
  assert.match(panel, /isTool\(item\)\?toolReviewLabel\(item\.descriptor\):modeLabel\(item\.execution_mode\)/);
  assert.match(panel, /disabled=\{busy\|\|!validComment\|\|!detail\.can_approve\|\|!detail\.validation\.valid\}/);
  assert.match(panel, /등록 검토 요청만 접수 · PADMIN 결정 차단/);
});
