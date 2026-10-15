---
created: 2026-10-12
status: actual-app-local-verified
scope: DP11-01 only
---
# 27 DP11-01 Builder 템플릿 조합 검증 구현 결과

사용자 요청: Agent Builder·프롬프트·RAG Playground를 모델 관리 전체보다 먼저 개발하고 상세 계획서를 보고한다. [[28 DP11 Agent Builder 프롬프트 RAG Playground 상세 개발 계획서]]를 먼저 Obsidian에 저장한 뒤 첫 독립 묶음을 구현했다. 기존 승인·게시 경계를 유지하며 상세 계획 Task2~4는 아직 구현되지 않았다.

## 실제 구현

관리 `/manage/admin/builder` 메뉴에서 기존 초안 저장·불변 버전·CAS·동일ID재시도·감사 UI를 재사용한다. instructions는 `{{variable_name}}` 템플릿을 지원하며 서버 parser가 단일 치환·정확한 변수 집합·수/길이/UTF-8/NULL/괄호를 검증한다. 변수값은 코드 실행/재귀 치환을 하지 않는다.

POST `/api/v1/admin/builder/assets/{asset_id}/preview`는 현재 관리 권한/조직/CSRF/32KiB/읽기 rate limit와 정확한 저장 revision을 확인한다. 초안만 수용하고 legacy409·stale409·다른조직404·일반user403다. 조합 SHA256은 저장 asset/version/config 지문·치환 결과·현재 선택 sources를 묶는다. 이는 실행 snapshot 또는 품질평가 증적이 아니다.

RAG는 기존 읽을 수 있는 자료 선택기를 재사용하며 이름/버전/조직·개인·공유 범위를 보여준다. 최대5개 정확한 refs를 서버 현재 ACL/게시/색인으로 확인하고 회수시404다. 빈 선택은 범위를 암묵 확대하지 않는다. 자료 원문·검색 chunk·모델 답변을 제공하는 단계는 아직 아니다. 기존 채팅의 미선택 검색 동작은 유지한다.

화면은 저장하지 않은 수정 시 검증 차단·결과 제거, 조직/자산/버전 변경 시 입력·결과 제거, 늦은 응답 무시를 적용한다. 명칭은 조합 검증이며 “모델 호출 없음”을 명시한다. 실제 DB의 기존 초안/버전을 재사용하는 API·React 구현이며 별도 시연 HTML이 아니다.

## 파일

- `src/backend/app/builder/__init__.py`
- `src/backend/app/builder/templates.py`
- `src/backend/app/builder/routes.py`
- `src/backend/app/main.py`
- `src/backend/app/errors.py`
- `src/backend/tests/test_builder.py`
- `src/frontend/src/AssetsPage.tsx`
- `src/frontend/src/BuilderPreview.tsx`
- `src/frontend/src/ReadableDocuments.tsx`
- `src/frontend/apps/admin-web/src/App.tsx`
- `src/frontend/packages/api-contract/src/api.ts`
- `src/frontend/scripts/verify-portal-builds.mjs`
- `src/frontend/tests/builder.spec.ts`
- `src/frontend/tests/safe-reporter.ts`

## 검증·적용

[[28 DP11-01 Builder 저장 버전 조합과 자료 권한 검증]]: 최신 사례 기준 backend52/브라우저9 pass, 분리 user23/admin23 모듈 빌드·경계 pass. backend는 두 실행의 최신 사례 집계이며 전체 server suite 단일 성공이 아니다. 누락 error 메시지/화면 타입 오류와 시험API 포트 충돌은 수정·소유 서비스 중단 후 재시험했다. 신규Builder browser ID 등록 전 통과3건은 등록 후 재실행3건으로 대체 집계한다.

신규 migration0, SQL000~029 30개 checksum 유지. primary 자산/실행/문서/정책 변경·유료호출0. 기존 primary 행 fingerprint 전체 재측정은 하지 않았으며 보존 시험으로 과장하지 않는다. 격리 fixture·private credentials·sources 제거와 API pool0 확인. API8000/user5173/admin5174 복구·health/페이지 HTTP200. primary 인증 Builder 시험은 하지 않았고 인증 UI는 fixture에서만 검증했다.

## 미완료와 다음 작업

DP11-02 구조화 system/developer/user prompt·model_ref·RAG scope 저장/과거버전조회/복제 lineage/실제 검색시험, DP11-03 최소 모델 계약·trial admission/worker/gateway/비용·취소·SSE, DP11-04 개인 시험 이력/평가셋/비교/승인 증적 연결이 남아 있다. Tool/MCP/Workflow·일반 제작자 capability·기관연동·운영 게시/배포 완료가 아니다. F전체 완료 판정은 갱신하지 않는다. 다음은 상세 계획 Task2다.

관련: [[15 전체 기능명세서 잔여 기능 개발 실행 계획]], [[23 포털 UI UX 확정과 사이트 분리 검토]], [[02 포털 UI UX 작업 기록]].
