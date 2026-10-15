---
title: Agent Builder 모델 바인딩 상세 구현 계획
created: 2026-10-13
status: in_progress
purpose: Agent Builder 프로필에 DP13 승인 모델 바인딩 및 선택 UI 연동
tags: [ai-platform, agent-builder, model-binding, dp13, ui-ux]
---

# Agent Builder 모델 바인딩 상세 구현 계획
본 계획서는 Agent Builder에서 구조화 프롬프트 프로필(`BuilderProfile`)을 작성하거나 수정할 때, DP-13 모델 레지스트리에 등록된 승인 모델(`ModelRef`)을 선택하여 불변 버전에 명시적으로 바인딩할 수 있도록 백엔드 계약과 프론트엔드 UI를 연동하기 위한 상세 계획입니다.

## 1. 배경 및 목표
- **고정 기본 모델 탈피**: 기존의 `default_general` / `default_rules_rag` 고정 바인딩에서 벗어나, 제작자가 작업 목적에 맞는 LLM(예: `gpt-4o-mini`, `gpt-4o`, `mock-fast`)을 선택할 수 있도록 지원합니다.
- **불변 스키마 및 해시 무결성 보존**: 바인딩된 `model_ref`는 버전 생성 시 `profile_hash`에 원자적으로 봉인되며, 임의의 미승인 모델 조작을 차단합니다.
- **제작자 친화적 UI 제공**: Agent Builder 화면에서 각 모델의 예상 토큰 단가, 문맥 한도(Context Window), 추천 용도를 한눈에 확인하고 직관적으로 선택할 수 있는 드롭다운 및 스펙 카드를 제공합니다.

## 2. 인터페이스 및 계약 설계
- **`model_contracts.py` 확장**:
  - `MODEL_CONTRACTS`에 `APPROVED_MODELS`의 모델들을 등록하고, `contract(model_ref, execution_kind)`를 통해 모델별 토큰 한도, 가격표 버전, 임베딩 모델 바인딩을 반환합니다.
- **`schemas.py` 검증 강화**:
  - `Profile.model_ref`: 기존의 `default_general`, `default_rules_rag`뿐만 아니라 DP-13 승인 모델 ID(`gpt-4o-mini`, `gpt-4o`, `mock-fast` 등)를 수용하도록 검증 로직을 확장합니다.
  - 비활성화되었거나 존재하지 않는 모델은 `PROFILE_INVALID`로 거부합니다.
- **프론트엔드 `BuilderProfileEditor.tsx`**:
  - `BuilderProfile.model_ref` 타입을 확장하고, 모델 선택 드롭다운 컴포넌트를 추가합니다.
  - `/api/v1/models` 엔드포인트를 호출하여 승인된 모델 목록을 조회하고 실시간으로 스펙과 단가를 표시합니다.

## 3. 변경 및 생성 파일 목록
- **백엔드**:
  - 수정: [`src/backend/app/builder/model_contracts.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/builder/model_contracts.py) — 승인 모델 계약 및 단가/문맥 해석 확장
  - 수정: [`src/backend/app/builder/schemas.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/builder/schemas.py) — `model_ref` 허용 목록 및 유효성 검증 확장
  - 수정/신규: [`src/backend/tests/test_builder_models.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_builder_models.py) — Builder 모델 바인딩 검증 테스트
- **프론트엔드**:
  - 수정: [`src/frontend/src/BuilderProfileEditor.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/BuilderProfileEditor.tsx) — 모델 선택기 드롭다운 및 스펙 카드 추가
  - 수정: [`src/frontend/packages/api-contract/src/types.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/api-contract/src/types.ts) — `BuilderProfile` 타입 정의 정렬

## 4. 단계별 실행 계획
1. **1단계**: 백엔드 `model_contracts.py` 및 `schemas.py` 확장 — DP-13 모델 레지스트리 기반 모델 허용
2. **2단계**: 백엔드 검증 테스트 `test_builder_models.py` 작성 및 통과 확인
3. **3단계**: 프론트엔드 `BuilderProfileEditor.tsx` 모델 선택 UI 구현 및 `/api/v1/models` 연동
4. **4단계**: 프론트엔드 분리 빌드 (`build:user`, `build:admin`) 및 전체 회귀 테스트 통과 확인
5. **5단계**: Obsidian 작업 기록 갱신 및 완료 보고
