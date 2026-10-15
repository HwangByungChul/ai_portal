---
title: 동적 Agent 즐겨찾기 및 My Agent 연동 상세 구현 계획
date: 2026-10-13
tags: [AI플랫폼, 동적에이전트, 즐겨찾기, MyAgent, 카탈로그, 계획]
status: draft
---
# 동적 Agent 즐겨찾기 및 My Agent 연동 상세 구현 계획
본 계획서는 DP10(고정 카탈로그/즐겨찾기)과 DP12(동적 Agent 승인 게시 및 실행)를 결합하여, 사용자가 승인 게시된 동적 Agent에 대해서도 개인 즐겨찾기(My Agent)를 등록·해제하고 홈 화면 및 My Agent 뷰에서 통합 탐색·실행할 수 있도록 하는 기능 연동 상세 계획입니다.

## 1. 배경 및 목표
- **현행 상태**:
  - DP10-01에서 구현된 `portal.agent_favorites`는 고정 운영 Agent 2종(`general`, `rules_rag`)의 `agent_key`만 참조 가능.
  - DP12에서 도입된 동적 게시 Agent(`portal.agent_publications`, `portal.agent_assets`)는 `asset_id`(UUID) 기반으로 별도 조회·실행되나, 개인 즐겨찾기 및 My Agent 연동이 미비함.
  - 사용자 홈 화면(3단 도우미 카드) 및 `/user/my-agents` 화면에서 동적 승인 Agent의 즐겨찾기 반영이 누락됨.
- **핵심 목표**:
  - 동적 게시 Agent에 대한 개인 즐겨찾기 영속화(PostgreSQL RLS, CAS 낙관적 락, audit 로그).
  - 즐겨찾기 등록/해제 API 및 카탈로그/게시 목록 통합 반환 API 구현.
  - 프론트엔드 `PublishedAgents`, `CatalogPage`(My Agent 모드), `HomePage` 연동.
  - 엄격한 보안 원칙: 즐겨찾기는 권한을 생성하지 않으며, 게시 철회되거나 권한이 없는 자산은 개인 목록에서 은닉하되 레코드는 보존.

## 2. 데이터베이스 및 보안 계약 (Migration 040)
- **대상 테이블**: `portal.dynamic_agent_favorites`
  - `tenant_id uuid NOT NULL`: 조직 격리
  - `user_id uuid NOT NULL`: 사용자 격리 (RLS 적용)
  - `asset_id uuid NOT NULL`: 게시된 Agent 자산 ID (`portal.agent_assets` FK)
  - `active boolean NOT NULL`: 즐겨찾기 활성 여부
  - `revision bigint NOT NULL CHECK(revision > 0)`: CAS 동시성 제어용 버전
  - `updated_at timestamptz NOT NULL DEFAULT clock_timestamp()`
  - 제약조건: `PRIMARY KEY (tenant_id, user_id, asset_id)`
- **RLS 및 권한 정책**:
  - RLS 활성화 및 `FORCE ROW LEVEL SECURITY` 적용.
  - 오직 `ai_policy_executor` 역할에만 제한적 DML 허용, `PUBLIC`, `ai_web`, `ai_index`, `ai_meter` 권한 박탈.
  - 정책 함수 `security.can_read_own_conversation(tenant_id, user_id)`를 통한 본인 및 조직 범위 검증.
- **감사 로그 (ops.audit_events)**:
  - 즐겨찾기 변경 시 `action = 'catalog.dynamic_favorite'` 기록.

## 3. 백엔드 API 계약
- **PUT `/api/v1/published-agents/{asset_id}/favorite`**:
  - Request Body: `client_request_id`, `expected_revision`, `active`
  - CAS 검증: 버전 불일치 시 409 Conflict, 정상 반영 시 새 `revision` 반환.
  - Idempotency: `portal.catalog_mutations`를 통한 동일 요청 재시도 보장.
- **GET `/api/v1/published-agents` 및 GET `/api/v1/published-agents/{asset_id}`**:
  - 응답 DTO에 `favorite: boolean`, `favorite_revision: number` 포함.
- **GET `/api/v1/catalog/assets?mine=true`**:
  - 고정 Agent 즐겨찾기 목록과 동적 Agent 즐겨찾기 목록을 통합하여 반환.

## 4. 프론트엔드 연동 계획
- **`PublishedAgents.tsx`**:
  - 동적 Agent 카드에 즐겨찾기 토글 버튼(`★ 즐겨찾기 해제` / `☆ 즐겨찾기 추가`) 추가.
  - CAS 불일치 처리 및 409 재조회 흐름 반영.
- **`CatalogPage.tsx`**:
  - `mine=true` (My Agent 모드) 진입 시 고정 및 동적 즐겨찾기 자산이 통합 렌더링되도록 뷰 정돈.
- **`HomePage.tsx`**:
  - 3단 업무별 AI 도우미 영역에서 사용자가 즐겨찾기한 동적 Agent가 우선 노출되도록 지원.

## 5. 단계별 검증 및 보존 계획
- **Phase 1: DB 스키마 및 보안 함수 (040 migration)**:
  - Checksum 000~039 보존, 신규 040 마이그레이션 적용.
- **Phase 2: 백엔드 API 및 단위/통합 테스트**:
  - `pytest`를 통한 즐겨찾기 추가/해제/CAS/RLS/회수 시 은닉 검증.
- **Phase 3: 프론트엔드 UI 연동 및 빌드 경계 검증**:
  - `build:user`, `build:admin`, `verify:builds` 통과.
- **Phase 4: 브라우저 E2E 검증 및 작업 기록 문서 갱신**:
  - 실제 사용자 계정(`a-u1`)으로 즐겨찾기 토글 및 홈/My Agent 노출 검증.
  - `02 포털 UI UX 작업 기록.md` 갱신.
