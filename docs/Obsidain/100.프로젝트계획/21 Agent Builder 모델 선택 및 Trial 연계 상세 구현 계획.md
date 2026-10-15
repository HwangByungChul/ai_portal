---
title: DP11-DP13 Agent Builder 모델 선택 및 Trial 연계 상세 구현 계획
created: 2026-10-13
status: in_progress
purpose: Agent Builder 프로필 내 다중 승인 모델 선택 UI 바인딩 및 Trial 실행 연동
tags: [ai-platform, agent-builder, model-registry, multi-model, trial]
---
# DP11-DP13 Agent Builder 모델 선택 및 Trial 연계 상세 구현 계획
본 계획서는 DP-13에서 구축된 모델 레지스트리(`ModelRegistry`)의 승인 모델 목록을 Agent Builder(DP-11)의 프로필 편집 화면에 연동하고, 시험 실행(`builder_trial`) 시 선택된 모델로 정확히 디스패치 및 정산되도록 연계하는 상세 구현 계획입니다.

## 1. 배경 및 목표
- **승인 모델 선택권 제공**: Agent 제작자(PADMIN)가 Agent의 목적(고속 응답, 심층 추론, 모의 테스트 등)에 맞게 서버가 승인한 모델(`gpt-4o-mini`, `gpt-4o`, `mock-fast` 등)을 직접 선택하여 프로필에 저장할 수 있도록 지원합니다.
- **임의 모델 및 비활성 모델 차단**: 클라이언트가 임의의 모델 ID나 비활성화된 모델(`mock-disabled`)을 주입하는 것을 서버 검증(`schemas.py`, `model_registry.py`)에서 원천 거부(`PROFILE_INVALID`)합니다.
- **레거시 호환성 보존**: 기존 저장된 `default_general`, `default_rules_rag` 참조는 시스템 기본 승인 모델(`gpt-4o-mini`)로 안전하게 fallback resolve되어 기존 자산 버전 및 시험 이력이 100% 정상 작동하도록 보장합니다.
- **Trial 실행 시 모델 동적 디스패치**: 시험 실행(`TrialExecutor`) 시 저장된 프로필의 `model_ref`를 티켓에 바인딩하고, `AiGateway`가 `ModelRouter`를 통해 지정된 모델 Provider로 발사 및 가격 스냅샷 정산을 완료합니다.

## 2. 인터페이스 및 계약 변경 설계
- **프론트엔드 모델 선택 UI (`BuilderProfileEditor.tsx`)**:
  - `BuilderProfile.model_ref`를 `string`으로 확장하여 구체적 `model_id` 수용
  - `GET /api/v1/models` API를 비동기 호출하여 승인된 활성 모델 목록(`ModelInfo[]`) 수신
  - 모델 선택 드롭다운(`select`) 컴포넌트 추가: 모델명, 제공자, 문맥 한도, 예상 토큰 단가 정보 표시
  - 선택 모델이 현재 자산의 실행 유형(`execution_kind`)에 필요한 capability(`chat`, `rag`)를 지원하는지 안내
- **백엔드 레지스트리 및 라우터 보완**:
  - `model_registry.py`: `resolve(model_id)`에서 `default_general`, `default_rules_rag`를 `DEFAULT_MODEL_ID`(`gpt-4o-mini`)로 안전 매핑
  - `schemas.py`: `SaveProfile` 검증에서 `execution_kind`별 필수 기능(예: RAG의 경우 `rag` capability)과의 정합성 확인
  - `execution.py` (`TrialExecutor`): `ticket.model_id`에 저장된 프로필의 `model_ref`를 바인딩하여 `AiGateway`로 전달
- **수용 검증 케이스**:
  - `C01`: Agent Builder에서 승인 모델(`gpt-4o`, `mock-fast`) 지정 프로필 저장 및 복제 성공
  - `C02`: 비승인 또는 비활성 모델(`mock-disabled`, `unknown-llm`) 지정 시 422 `PROFILE_INVALID` 거부
  - `C03`: 레거시 `default_general` / `default_rules_rag` 프로필의 안전 fallback resolve 검증
  - `C04`: `builder_trial` 실행 시 선택된 모델의 `generation_model` 및 계약 정보 정확히 반환
  - `C05`: 프론트엔드 독립 빌드(`build:user`, `build:admin`) 통과 및 화면 렌더링 확인

## 3. 작업 대상 파일 목록
- **백엔드**:
  - 수정: `src/backend/app/ai/model_registry.py` (레거시 alias fallback 처리)
  - 수정: `src/backend/app/builder/schemas.py` (모델 유효성 및 capability 호환 검증)
  - 수정: `src/backend/app/builder/execution.py` (TrialExecutor 내 ticket.model_id 바인딩)
  - 생성: `src/backend/tests/test_builder_models.py` (다중 모델 프로필 저장 및 Trial 연동 수용 테스트)
- **프론트엔드**:
  - 수정: `src/frontend/src/BuilderProfileEditor.tsx` (모델 목록 조회 및 선택 UI 연동)
  - 수정: `src/frontend/src/types.ts` (`BuilderProfile` 타입 호환)
  - 생성: `src/frontend/tests/builder-models.spec.ts` (E2E 화면 검증)
- **문서**:
  - 기록: `docs/Obsidain/400.프로젝트관리/02 포털 UI UX 작업 기록.md`

## 4. 단계별 실행 계획
1. **1단계**: 백엔드 모델 레지스트리 fallback 보정 및 `TrialExecutor`의 `ticket.model_id` 바인딩 구현
2. **2단계**: 백엔드 수용 테스트 `test_builder_models.py` 작성 및 C01~C04 통과 검증
3. **3단계**: 프론트엔드 `BuilderProfileEditor.tsx` 모델 선택 드롭다운 및 정보 뱃지 구현
4. **4단계**: 프론트엔드 분리 빌드 (`build:user`, `build:admin`) 및 전체 회귀 검증
5. **5단계**: 로컬 가동 상태 확인 및 Obsidian 작업 기록 갱신
