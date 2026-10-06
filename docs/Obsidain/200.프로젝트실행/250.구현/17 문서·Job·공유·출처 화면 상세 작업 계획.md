---
title: 문서·Job·공유·출처 화면 상세 작업 계획
created: 2026-10-06
updated: 2026-10-06
status: completed
stage: 250.구현
tags: [implementation-plan, C05, frontend, rag]
---

# I250-C05 문서·Job·공유·출처 화면

C01~C04 서버 API를 실제 사용자·관리자 화면에 연결한다. 등록→색인→정확한 버전 공유→규정 질문→근거·원문 확인→공유 회수 흐름을 모의 환경에서 시연하는 것이 완료 기준이다. 실제 모델 품질·합성7버전/Q20 전체 평가는 다음 C06에서 별도 판정한다.

참조: [[16 ACL 검색과 RAG 답변 구현 결과]], [[09 문서와 GraphRAG 연결 상세 작업 계획]], [[../240.설계/07 사용자와 관리자 화면 설계]], [[../240.설계/06 문서와 GraphRAG 설계]].

## 일정과 순서

기존 C20시간 중 C05 예비3시간을 유지한다. 예상 공수이며 개인 실제 공수는 미측정이다. 주20시간 이상/총80시간(여유10시간 포함), 10월24일 파일럿·28일 기능동결·31일 종료 목표를 유지한다.

| 순서 | 예상 | 구체 작업 |
|---|---:|---|
| 1 |20분|실제 응답·타입·공통 API adapter 대조, 조직/CSRF/취소/접수 복구 재사용|
| 2 |40분|관리자 문서 등록·새 버전·Job 상태·명시 재시도·삭제|
| 3 |25분|정확한 게시 버전의 공유 발급·회수·revision 충돌 처리|
| 4 |35분|사용자 문서 선택·규정 Agent 실행·검증된 저장 답변|
| 5 |25분|현재 근거·원문 다운로드·회수와 조직 전환 경계|
| 6 |35분|새 화면/기존 화면 회귀·결과/WBS·C06 상세 계획|

초과 시 장식·통계·추가 파일 형식을 먼저 보류한다. 현재 권한·버전 구분·접수 복구·근거 차단은 완료 기준으로 유지한다.

## 1. 공통 화면 경계

예정 변경: `src/frontend/src/App.tsx`, `types.ts`, `api.ts`, `scoped.ts`, `ChatPage.tsx`, `styles.css`. 예정 신규: `DocumentsPage.tsx`, `DocumentJobsPage.tsx`, `DocumentSharingPanel.tsx`, `RagEvidencePanel.tsx`; 실제 기능이 작으면 불필요한 파일 분할은 줄인다.

모든 조직 API는 현재 조직 헤더를 사용하고 쓰기에는 기존 Origin/요청 헤더/CSRF를 유지한다. 서버의 현재 권한 응답으로 메뉴와 조작을 결정한다. 개인 문서의 관리 권한을 원문 읽기 권한으로 처리하지 않는다. 플랫폼 관리 역할만으로 다른 조직의 본문을 제공하지 않는다.

조직·사용자·선택 대화가 바뀌면 요청을 취소하고 문서 선택/Job/Grant/근거/본문을 즉시 지운다. 늦은 응답은 현재 scope를 통과해야 표시한다. 본문·파일·근거는 localStorage나 공용 캐시에 저장하지 않는다. 권한 회수·조회 실패 시 이전 민감한 결과를 남기지 않는다.

## 2. 관리자 문서·처리 상태

사용 API: GET/POST `/admin/documents`, POST `/admin/documents/{document_id}/versions`, DELETE `/admin/documents/{document_id}`, GET `/admin/jobs`, GET `/admin/jobs/{job_id}`, POST `/admin/jobs/{job_id}/retry`.

`app/documents/upload.py`의 실제 multipart metadata/파일 계약을 대조해 TXT/Markdown·허용 크기를 안내한다. 임의 조직·서버 경로를 입력하지 않는다. client_upload_id는 한 요청에 고정하고 통신 결과가 불명확하면 같은 payload/ID로 접수를 확인한다. 새 ID의 자동 중복 업로드는 하지 않는다.

등록202는 '접수됨'이며 게시 완료와 다르다. validate_source/parse_plan/embed_batches/validate_index/publish 단계와 queued/running/needs_review/failed/completed를 표시한다. 이전 게시 버전이 유지되는 실패도 구분한다. 화면이 열린 동안만 정해진 간격으로 조회하고 조직 전환 시 polling을 종료한다.

재시도는 서버가 허용한 상태에서 expected_revision/client_retry_id로 명시 수행한다. usage_unknown/needs_review를 자동 재실행하지 않는다. 삭제는 현재 revision을 사용하고 이후 목록·선택·근거를 다시 읽는다. 삭제와 함께 사용량 원장을 초기화하지 않는다.

## 3. 정확한 버전 공유

사용 API: GET `/admin/share-recipients`, GET/POST `/admin/documents/{document_id}/versions/{version_id}/grants`, DELETE `/admin/grants/{grant_id}`.

조직 소유의 게시 버전과 publication_revision으로 발급한다. v1 공유가 v2까지 포함되는 것처럼 표시하지 않는다. 신규201/활성 Grant 재접수200은 현재 상태로 다시 조회해 중복 표시를 막는다. 회수에는 Grant expected_revision을 사용하고409이면 최신 상태를 읽는다.

private 재공유·수신 조직 재발급을 제공하지 않고 서버 거부도 처리한다. 수신 후보는 서버가 허용한 목록만 사용한다. 개인 문서의 관리자가 원문 제목을 읽을 수 있다고 가정하지 않는다.

## 4. 사용자 자료와 규정 질문

사용 API: GET `/documents?scope=org|private|shared`, GET `/agents`, 기존 POST `/runs`와 run/본인 이력/취소/SSE 조회.

Agent가 현재 사용 가능할 때만 규정 질문을 접수한다. primary의 기본 mock/RAG 비활성을 자동으로 변경하지 않는다. 모의 시연은 별도 시험 데이터/조직에서 구성한다.

서버가 반환한 exact document_id/version_id를 최대5개 선택한다. 선택하지 않으면 현재 허용 자료에서 검색한다. org/private/shared·안전한 버전 이름을 구분하고 필터 변경 시 cursor를 초기화한다. 목록이 오래됐으면 재조회하며 회수된 버전을 자동 재전송하지 않는다.

일반 질문에는 document_refs를 보내지 않는다. 규정 질문에만 선택 버전을 넣는다. 같은 접수 복구는 질문/문서 선택/client_send_id를 유지한다. 현재 RAG는 질문별 처리이며 이전 대화 내용을 모델 입력으로 사용하지 않는 점을 도움말에 안내한다.

RAG는 저장·검증 후 정본만 표시한다. retrieval/generation/finalizing 단계와 insufficient_evidence/failed/unavailable을 구분한다. RAG SSE draft를 본문으로 표시하지 않는다. 기존 일반 대화의 작성 중/저장 확인은 유지한다.

## 5. 근거와 원문

사용 API: GET `/runs/{run_id}/evidence`, GET `/runs/{run_id}/evidence/{ordinal}/source`.

서버 인용 번호와 ordinal을 연결한다. 현재 허용된 제목·버전·정확한 인용·행 위치만 일반 텍스트로 표시하고 HTML을 실행하지 않는다. source_url은 예상 본인 run의 상대 경로인지 확인해 임의 외부 주소를 링크하지 않는다.

원문 다운로드는 현재 조직 헤더를 포함한 인증 요청으로 받는다. 실패 응답/Content-Type을 확인하며 Blob URL은 사용 후·조직 전환 시 폐기한다. 안전한 파일명/no-store/nosniff를 유지하고 서버 파일 경로를 표시하지 않는다.

답변은 모든 출처의 현재 권한이 유효할 때 공개된다. unavailable 항목의 제목·인용을 추측하지 않는다. 철회 후 최신 run 조회에서 본문 unavailable이면 이미 표시한 본문/근거를 지운다. 재진입·화면 가시화·새로고침 시 현재 권한을 다시 확인한다.

## 6. 시험과 산출물

예정 시험: `src/frontend/tests/documents-rag.spec.ts`와 기존 auth-tenants/chat-operations 회귀. 폐기용 A/B DB에서 실제 API와 mock provider를 사용한다.

- 등록202→Job 완료/게시·새 버전·삭제/재시도 상태를 정확히 표시한다.
- A org v1→B 공유→B 목록/질문/근거/다운로드 성공·미공유v2 접근 거부를 확인한다.
- private 읽기/관리 구분·재공유 거부·revision 충돌·최신 권한을 확인한다.
- 저장 전 RAG 본문0·근거 부족/실패/usage_unknown 안내를 확인한다.
- 회수 후 과거 본문/근거/다운로드 차단·조직 전환/늦은 응답/Blob 폐기를 확인한다.
- 같은ID 접수 복구·재시작 완료 조회에서 추가 provider 호출0을 확인한다.
- 모바일 폭의 문서 선택·공유·상태·근거 확인과 기존51개 회귀/build를 확인한다.

결과는 `250.구현/18 문서·Job·공유·출처 화면 구현 결과.md`, 신규 `260.테스트/evidence/C-rag/C05-*`, WBS/대장에 기록한다. 기존 증거를 덮어쓰지 않는다. C06 계획에는 합성7버전 실제 등록·색인, Q20 질문별 실행 결과, mock/real 구분, 실제 호출 예산 사전 계획과 통합/재현 인계를 포함한다. Q20 not_run 원본을 실행 전 완료로 바꾸지 않는다.

- [x] 공통 타입·조직 경계
- [x] 관리자 문서·Job
- [x] 버전 공유·회수
- [x] 규정 질문·문서 선택·저장 정본
- [x] 현재 근거·안전한 다운로드
- [x] 시험·결과·C06 인계

## 완료 기록 — 2026-10-06

실행 결과와 제약은 [[18 문서·Job·공유·출처 화면 구현 결과]]에 기록했다. 관련9개/전체60개 화면·빌드와 서버14개 통과. 개인 소유자/읽기 대상 편집 UI와 실제 RAG 품질은 후속 범위로 구분한다. 다음 [[19 합성 자료와 Q20 통합 검증 상세 작업 계획]].
