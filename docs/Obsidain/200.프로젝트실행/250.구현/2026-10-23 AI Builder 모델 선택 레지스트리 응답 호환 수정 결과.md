---
title: AI Builder 모델 선택 레지스트리 응답 호환 수정 결과
created: 2026-10-23
status: implemented
tags: [ai-builder, dp13, model-registry, frontend]
---

# AI Builder 모델 선택 레지스트리 응답 호환 수정 결과

## 요청·결정
AI Builder 편집기의 모델 선택 목록이 비어 있거나 DB 기반 등록 모델이 렌더링되지 않는 원인을 확인했다. `ApiClient`는 공통 응답의 `data`를 반환하고, 현재 `/models`는 그 안에 `{items: [...]}`를 담는다. 레거시 인메모리 모델과 DB 등록 모델의 공개 필드도 서로 다르다. 두 응답 형태를 UI 경계에서 정규화하고, 서버가 제공하지 않는 DB 가격을 임의로 표시하지 않기로 했다.

## 변경 파일
- `src/frontend/packages/api-contract/src/types.ts`: 레거시 및 DB 모델 공개 DTO 구분
- `src/frontend/src/BuilderProfileEditor.tsx`: `items` 응답 처리, 표시 이름·사양 정규화, 누락된 가격·한도 안전 표시
- `src/frontend/tests/builder-models.spec.ts`: DB 계약, 레거시 모델, 빈/실패 응답, RAG 호환성 회귀 사례

## 검증 결과
- `npx tsc --noEmit`: 통과 (bundled Node v24.19.0)
- `git diff --check`: 통과
- Playwright 브라우저 실행: 미완료. 구성된 backend webServer가 시작 단계에서 종료했고, 기본 결과 파일 경로 접근도 `EPERM`을 반환했다. 기존 로컬 서비스는 중지하거나 교체하지 않았다.
- 프론트엔드 빌드: 미완료. Vite 임시 설정 번들 쓰기에서 `EPERM`이 발생했다.

## 권한·상태·미완료 범위
모델의 활성 상태와 capability를 UI 목록에 반영한다. API가 공개하지 않는 credential 및 가격 정보를 추가하지 않았다. 모델 선택은 초안 설정이며 그 자체로 승인, 게시, 시험 실행 또는 운영 배포를 수행하지 않는다. 기관 UAT와 브라우저 회귀 수용은 미완료다. 관리 모델 페이지의 DB DTO 정합성은 별도 후속 검토 대상으로 남긴다.

## 연결
[[200.프로젝트실행/240.설계/2026-10-21 AI Builder 고도화 통합 Studio 설계]] · [[100.프로젝트계획/20 DP13 모델 레지스트리 및 다중 모델 계약 상세 구현 계획]] · [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
