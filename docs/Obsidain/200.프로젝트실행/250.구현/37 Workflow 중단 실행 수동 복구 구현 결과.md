---
title: Workflow 중단 실행 수동 복구 구현 결과
date: 2026-10-16
status: 구현 완료 · 수용 미검증
tags: [workflow, recovery, implementation]
---
# Workflow 중단 실행 수동 복구 구현 결과

관련 상세 실행 계획: [[100.프로젝트계획/37 미완료 기능 잔여 개발 통합 상세 계획]]

## 범위와 동작

사용자 지시에 따라 Workflow 장기 실행 장애 시 무인 재시도를 피하고 사람이 검토하는 재개 흐름을 구현했다. 소유자가 중단 단계와 사유를 제출하고, 다른 PADMIN이 승인/반려하며, 승인 후 소유자가 재개를 확정한다. 재개는 exact 승인 version, workflow head, 현재 owner 권한, revision과 현재 정책 gate를 다시 확인한다.

성공한 단계는 내부 checkpoint에서 복구하고 건너뛴다. 알 수 없는 Tool receipt 또는 아직 끝나지 않은 Agent child가 있으면 worker를 재호출하지 않고 재개를 차단한다. 이 범위는 알려진 checkpoint를 통한 재개만 구현했으며, 외부 시스템 결과를 자동으로 조회·조정하는 reconciliation은 포함하지 않는다.

## 변경 파일

- `src/backend/migrations/054_workflow_manual_recovery.sql`: append-only 회복 이벤트, FORCE RLS, 신청/결정/재개 제어와 성공 checkpoint read를 추가했다.
- `src/backend/migrations/055_workflow_recovery_retry_guards.sql`: idempotent request replay, 현재 head 검증, replay 상태 및 enqueue 중복을 보완했다. migration 054의 원본 checksum은 변경하지 않았다.
- `src/backend/app/workflows/repository.py`, `service.py`, `routes.py`: DB/API, checkpoint resume과 HTTP endpoints를 연결했다.
- `src/frontend/packages/api-contract/src/types.ts`, `src/frontend/src/WorkflowCanvasPage.tsx`: 소유자 요청/재개 및 관리자 검토 목록 UI를 연결했다.

## DB 이행과 증거

055 적용 전 활성 local fixture DB custom-format backup을 생성하고 별도 fixture DB로 복원했다. clone에 migration을 먼저 적용한 뒤 활성 DB로 이행했다. 기존 74개 테이블 행 digest 및 기존 migration 55개 SHA256은 clone/활성 DB 모두 보존됐다. backend 및 두 frontend의 실제 listener를 재기동했다. 최종 API8000 health, 사용자5173 `/user/home`, 관리자5174 `/manage/admin`은 HTTP 200이다.

- migration 055 SHA256: `b4b23c6cde5d27cd2640b51fa8ea93b8698c89b11e30871d0468aa4bddf8e958`
- backup: 1,177,453 bytes; SHA256 `e50a873323ec37df56f9f5ac70aa6f4d7d4d4a3ad9837922be209d5e5bf7aead`
- 비공개 적용 증거: `src/backend/.runtime/backups/workflow-recovery-guards-20261016/apply-proof.json`

## 검증

- `python3 -m compileall -q src/backend/app/workflows`: 통과
- `npm run build:admin`: 통과, portal 52 modules, boundary verified; 712.24 kB 번들 크기 경고
- `npm run build:user`: 통과, portal 28 modules, boundary verified
- 테스트 suite와 인증된 소유자/PADMIN 왕복·브라우저 수용은 실행하지 않았다. 해당 결과는 구현 검증으로 오인하지 않는다.

## 미완료 및 다음

1. 별도 계정으로 소유자 신청, 타인 PADMIN 승인·반려, 소유자 재개와 권한 거부/중복·revision 충돌을 확인한다.
2. Tool/Agent 외부 시스템 receipt 조회 및 취소/반영 reconciliation 계약은 기관별 외부 receipt 기능이 준비된 뒤 추가한다.
3. Workflow 정상 종료/취소/실패 원장, 회의록 업무 품질, T-035 실기관 Tool, 전체 F/IA/T 수용을 독립 검증한다.

작업 기록: [[400.프로젝트관리/02 포털 UI UX 작업 기록]] · 진행 보고: [[200.프로젝트실행/250.구현/2026-10-16 잔여 기능 개발 중간 보고서]]
