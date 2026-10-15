---
title: DP12-03 사용자 전역 실행 이력과 철회 Agent 기록 탐색 계획
date: 2026-10-12
tags: [portal, history, execution]
status: 해당 구현 단위 완료 · 후속 남음
---
# 사용자 전역 실행 이력 구현 계획

사용자가 다음 작업 진행을 승인했다. [[34 DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교 구현 결과]] 이후의 사용자 전역 동적 실행 이력·철회 Agent 최소 기록 탐색 단위다. writing-plans와 obsidian-markdown을 적용하며 사용자의 Obsidian 경로·개발 진행 승인에 따라 같은 세션에서 구현한다. 별도 에이전트/커밋/운영 배포는 하지 않는다.

**Goal:** 카탈로그에서 사라진 Agent도 본인이 실행했던 최소 기록을 찾고 현재 권한이 허용하는 실행 상세를 확인한다.
**Architecture:** 기존 owner RLS 원장에 읽기 capability 하나와 인덱스를 추가한다. 원장/과거 비용/질문/답변은 수정하지 않는다. 페이지의 record 조회와 답변 조회는 분리하고 현재 publication·own 자료 권한을 검증하는 기존 published_run_guard/run API를 유지한다.
**Tech Stack:** PostgreSQL forced RLS, FastAPI, React/TypeScript, pytest, Playwright.
**Spec:** [[33 DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교 계획]]의 다음 사용자 탐색 단위 및 확정 [[23 포털 UI UX 확정과 사이트 분리 검토]].

## 계약과 경계

- 생성형 AI 플랫폼·사용자 A/관리 A/승인 B·local/dev/tb/prd 포트 및 세션 계약 유지. SQL000~038 동결·039만 추가한다.
- GET /api/v1/published-agent-runs: 현재 조직/본인 asset_chat만, created_at DESC/run_id DESC 20+1 cursor; optional asset_id와 state 필터. builder_trial/고정 대화 제외. cursor는 동일 owner/조직/필터 범위의 run이어야 한다.
- GET /api/v1/published-agent-runs/{run}/record: 본인 최소 metadata. fields run_id, asset_id, asset_revision/version_id, publication_revision, state/revision/is_terminal, execution_mode, created_at, available, display_name. available=false이면 이름도 숨기고 질문/답변/자료/현재 공개 대상/다른 사용자의 기록은 반환하지 않는다.
- available은 현재 exact publication binding과 own 자료/출처 권한의 기존 guard 결과다. 철회·다른 version 게시·대상회수·자료회수는 metadata만 보존한다. 최소 이력은 권한 부여가 아니다. 기존 상세 API/실행/정산/취소 경계를 유지한다.
- query UUID/state enum·중복/extra422·no-store·read-window. 인증/조직 접근 회수는 기존401/403 유지한다. capability owner/search_path/PUBLIC/raw 권한 불변.
- 사용자 메뉴 ‘Agent 실행 이력’과 AI 업무의 이력 이동 버튼을 연결한다. 기존 대화에 독립 Agent 질문을 삽입하지 않고 별도 조회 화면으로 탐색한다. 현재 카탈로그 재진입은 새 독립 실행이다.
- 상태 필터/20건 더보기/재조회/현재 허용 상세/취소를 제공한다. scope·selection generation·단일 refresh로 늦은 응답 무시. 선택 기록을 1초(active)/5초(terminal) 및 focus/visibility에서 현재 권한 재확인한다. 실패/회수 시 답변을 즉시 숨긴다. active metadata-only 취소는 가능하다.

## Task1 서버 이력 계약

Files: migrations/039_published_run_history.sql, app/assets/published.py, tests/test_published_history.py, tests/support.py.
- [x] owner/filter/cursor·철회 metadata·다른 owner/조직404·정책/자료/대상회수·과거 version·비밀 비노출·HTTP strict 계약을 테스트한다.
- [x] security.published_run_history(session,tenant,action,id,body,mode) list/record와 owner 인덱스를 구현한다. guard 실패의 알려진 권한/출처/게시 오류만 available=false로 처리한다. 예상하지 못한 DB 오류는 성공으로 삼키지 않는다.

```python
page = await history(user, 'list', None, {})
assert page['items'][0]['run_id'] == own_run
assert not retired_record['available']
assert retired_record['display_name'] is None
assert 'result' not in retired_record and 'messages' not in retired_record
```

- [x] 좁은 신규 계약과 기존 published/rollback/정산 수용을 순차 실행한다. 단일 실행과 별도 최신 집계를 구분한다.

## Task2 사용자 탐색 UI

Files: src/PublishedRunHistory.tsx, apps/user-web/src/App.tsx, src/ChatPage.tsx, tests/published-history.spec.ts.
- [x] 전역 이력 page 및 상태 필터/더보기/선택 record·현재 답변/정산·취소·카탈로그 이동을 연결한다. 모의 실행 라벨과 현재 상세 제한 문구를 유지한다.
- [x] AI 업무 이동·URL reload/back·조직 switch 시 초기화·늦은 상세 응답 무시·철회 후 답변 숨김을 실제 UI로 검증한다. 카탈로그가 빈 경우도 이력은 독립 진입한다.

```ts
await page.getByRole('button',{name:'Agent 실행 이력',exact:true}).click();
await expect(page.getByRole('region',{name:'Agent 실행 기록 상세'})).toContainText('현재 권한으로 상세를 조회할 수 없습니다');
```

## Task3 local 이행·기록

- [x] user/admin build·코드 경계·git diff --check. owned 서비스만 중지하고 fixture harness는 순차 실행한다.
- [x] private600 DB backup→039만 추가→기존51표 모든 행/39checksum 보존→51표/40migration/141security 함수 예상(실제 query 확인)·재적용 무변화→서비스8000/5173/5174 HTTP200. primary seed/reset/합성 업무/paid0.
- [x] 구현35/시험36·설계23/진행02/master15/DP11계획28/잔여11/AGENTS에 실제 파일·근거·실패/미검증·다음 작업을 남긴다.

## 미포함

다회차 memory·즐겨찾기·이력 제목/핀/삭제·모든 고정/문서/동적 작업 통합 원장·비용/토큰 상세·과거 version 답변 재허가·내보내기·복잡 승인/모델/secret/tool/workflow·실 provider/Entra/UAT/운영 배포는 후속이다. 전체F 완료 수를 재산정하지 않는다.

## 구현 중 보완

취소 추가 수용에서 기존 raw SELECT와 run_view의 철회 답변 guard가 취소를 막는 문제를 발견했다.039에서 기존 run_cancel의 상태/write/row lock/revision/audit 검사는 그대로 유지하고 asset_chat만 owner 최소 record 응답으로 분기한다. 상세 run API는 기존 guard로 계속 차단한다. 접수 필터는 원장 상태 accepted로 제공한다. 추가 일반 대화 취소 회귀도 수행한다.

## 실행 결과

[[35 DP12-03 사용자 전역 Agent 실행 이력과 철회 기록 구현 결과]]·[[36 DP12-03 실행 이력 소유권 철회와 현재 답변 권한 검증]]에 실제 파일·52서버 최신 별도집계·12브라우저 최신 별도집계·빌드·local 추가 이행/실패/미검증과 다음 작업을 기록했다.
