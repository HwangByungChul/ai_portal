---
title: DP11 Agent Builder 프롬프트 RAG Playground 상세 개발 계획서
created: 2026-10-12
status: approved-for-development
priority: 사용자 요청으로 DP13보다 먼저 착수
tags: [ai-platform, builder, prompt, rag, development-plan]
---

# DP11 Agent Builder·프롬프트·RAG Playground 상세 개발 계획서

**Goal:** 제작자가 Agent 초안을 편집하고 정확한 불변 버전의 프롬프트·자료 범위를 확인한 뒤, 정책·비용 원장을 적용한 시험 실행 증적을 승인 요청에 연결한다.

**Architecture:** 기존 FastAPI·PostgreSQL 자산 원장과 독립 React 관리 앱을 확장한다. 편집/조합 검증, 자료 검색, 모델 시험 실행을 분리한다. 운영 이용자는 승인·게시 전 초안에 접근할 수 없으며 시험 실행은 제작 권한으로 별도 접수한다.

**Tech Stack:** 현재 Python/FastAPI/Pydantic·PostgreSQL RLS/RPC·React/TypeScript·pytest/Playwright를 유지한다.

**Spec:** [[비거버넌스 하위요구 수용기준]] F016·F024·F032, [[15 전체 기능명세서 잔여 기능 개발 실행 계획]], [[24 DP-09 동적 AI 자산 기반 상세 설계와 실행 계획]], [[26 DP10 Agent 카탈로그 My Agent 이용 권한 구현 결과]].

**실행 방식:** 사용자 2026-10-12 요청에 따라 이 세션에서 계획을 먼저 기록하고 직접 순차 개발한다. 스킬의 새 승인/커밋/하위 에이전트 권장 절차보다 이미 승인된 개발 범위와 기존 변경 보존 지시를 우선한다. 전체 DP11 완료와 첫 독립 묶음 완료를 구분한다.

## 1. 우선순위 변경과 설계 대안

이전 순서는 DP13 모델 관리→DP11이었다. 사용자가 Builder·프롬프트·RAG Playground를 먼저 요청했으므로 DP11-01 편집/조합 검증부터 시작한다. 실제 시험 실행 전에 DP13의 최소 모델 계약을 DP11-03에 포함하며 모델 Registry 전체는 후속으로 유지한다.

| 대안 | 장점 | 한계/결정 |
|---|---|---|
| 기존 자산 원장 확장, 실행은 별도 시험 경로 | 불변 버전·CAS·재시도·감사 재사용, 승인 경계 보존 | 채택. 단계마다 실제 API/화면과 검증 증거 제공 |
| Builder 전용 저장소·별도 모델 호출 | 독립 화면 구현이 빠름 | 버전·비용·권한 중복과 우회 위험으로 미채택 |
| 전체 모델 관리 완료 후 Builder | 모델 선택 기능을 한 번에 연결 | 사용자 우선순위와 달라 미채택; 최소 실행 계약만 선행 |

## 2. 기준선·공통 제약

- 생성형 AI 플랫폼 명칭, 사용자 A홈·관리 A홈/B승인 패널 유지. 관리 메뉴에 Agent Builder를 추가한다.
- 기존 assets/asset_versions와 고정 general/rules_rag 원장을 재사용한다. 신규 Agent는 draft이며 운영 실행과 사용자 카탈로그에 노출하지 않는다.
- SQL000~029는 수정하지 않는다. 저장 구조 확장은 additive030 이상, 백업·기존 행/체크섬 보존 확인 후 local 반영한다.
- local/dev/tb/prd 설정·사용자5173/관리5174/API8000 분리 및 CSRF/현재 조직 권한 검사를 유지한다.
- 최초 제작자는 현재 조직 관리 권한을 가진 사용자다. 일반 제작자 capability는 DP16에서 추가한다. 관리자라는 이유로 타인의 대화·개인 문서·시험 입력을 읽게 하지 않는다.
- 문서 범위는 최대5개 정확한 document_id/version_id. 현재 게시/색인/원문 권한을 서버에서 재확인한다. 빈 선택으로 전체 조직 자료를 암묵 확장하지 않는다.
- 유료 제공자 호출 없이 합성 제공자로 먼저 검증한다. 실제 품질·비용 검증과 기관 UAT·운영 배포는 별도다.
- 기존 거버넌스 제외와 PPTX/OCR 보류 유지. Tool/MCP·Workflow 실행은 이 계획에서 구현 완료로 표시하지 않는다.

## 3. 화면·사용 흐름

관리 사이트 → Agent Builder → 자산 선택 또는 신규 초안 → 이름/설명/실행 방식/템플릿 편집 → 새 불변 버전 저장 → 변수값 입력 → 조합 검증 → 자료 범위 확인 → 시험 실행 → 결과 비교 → 승인·검증 요청 순서다.

목록·편집 패널은 기존 자산 관리 UI를 재사용한다. 기존 운영 Agent는 읽기 전용이며 운영 설정 변경은 기존 승인 경로를 따른다. 초안을 저장한 후에만 저장 버전 조합 검증을 허용한다. 저장하지 않은 수정이 있으면 결과를 지우고 저장 안내를 표시한다. 조직/자산/버전 변경 시 입력·결과와 요청을 폐기하며 늦게 도착한 응답을 표시하지 않는다.

Playground는 세 가지 결과를 구분한다: **조합 검증**(모델 미호출), **검색 검증**(검색 결과·인용 후보), **모델 시험**(실제 생성 결과·비용·종료 상태). 조합 검증을 AI 답변이나 품질평가로 표시하지 않는다.

## 4. 데이터·API 계약

### DP11-01 기존 저장 버전 조합 검증

instructions에 `{{variable_name}}` 문법을 사용한다. 이름은 `[A-Za-z][A-Za-z0-9_]{0,39}`, 최대20개. 미입력/추가 변수·잘못된 괄호·빈 필수값은422, 변수값은 최대2000자, 전체 치환 결과는8000자/UTF-8 24000바이트 이하. 재귀 치환·코드 실행·표현식 평가를 수행하지 않는다. 변수값 안의 괄호는 단순 데이터다.

POST `/api/v1/admin/builder/assets/{asset_id}/preview`:

```json
{"expected_revision": 1, "values": {"audience": "담당자"}, "document_refs": []}
```

서버가 현재 admin 자산 상세와 revision을 조회한다. stale409, legacy409, 권한없음403, 타조직404. rules_rag에만 자료 선택을 허용하고, 정확한 게시/권한/색인 범위를 확인한다. 응답은 asset_id/version_id/config_hash/revision, 변수명 목록, 치환 instructions, 조합 SHA256, 현재 허용 source bindings, `kind=composition_preview`, `provider_called=false`다. 미리보기는 저장된 템플릿의 조합 결과이며 실제 실행 snapshot으로 오인하지 않게 표시한다. POST의 CSRF·본문32KiB·rate limit·no-store를 적용한다.

### DP11-02 구조화 프롬프트·복제·자료 검색

후속030+에 `portal.builder_profiles`를 추가한다. PK(tenant_id,version_id), asset_versions FK, system_prompt/developer_prompt/user_template, model_ref, RAG scope와 설정 schema 버전을 저장한다. 기존 버전은 수정하지 않고 새 버전으로 구조화한다. 저장 transaction은 asset_registry append와 profile 저장을 함께 처리하여 일부 저장을 막는다. 별도 security.builder_save RPC가 현재 제작 권한·expected_revision·client_request_id·payload 지문과 audit를 검증한다.

POST `/admin/builder/assets/{id}/versions`는 기존 AssetConfig와 profile, expected_revision/client_request_id를 수용한다. 복제 POST `/admin/builder/assets/{id}/clone`은 원본 version_id와 새 요청 ID를 받아 새 자산/버전과 parent lineage를 원자 저장한다. 원본 권한이 회수되면 복제 차단한다.

GET `/admin/builder/assets/{id}/versions/{version_id}`는 본인이 접근 가능한 정확한 버전 구성만 반환한다. 사용자 개인 대화나 서버 credential 값은 반환하지 않는다. 사용자 일반 공개용 프롬프트 조회는 승인 버전·별도 읽기 권한·민감값 마스킹 후 DP12와 연결한다.

POST `/admin/builder/assets/{id}/search-tests`는 version_id, client_request_id, query, 선택 문서 refs를 받는다. 기존 RAG QueryGateway·권원·embedding 원장을 사용하며 쿼리도 외부 호출 비용을 보존한다. 검색 노출은 근거 chunk·문서 버전·순위·부족 근거 여부, 최대6 chunk/현행 graph 한도를 유지한다. top_k/검색방식 확장은 공급자 schema 계약 이후 검증한다.

### DP11-03 실제 시험 실행

POST `/admin/builder/assets/{id}/test-runs`는 저장 version_id·client_send_id·변수값·문서refs를 받아202 run을 접수한다. ticket에는 execution_purpose=builder_test, creator_user_id, asset/version/config/profile/조합 지문, 모델·정책 revision, 자료 bindings를 봉인한다. 일반 `/runs`는 draft를 계속 거부한다. 시험 run 생성·조회·취소·SSE는 본인/현재 제작 권한 전용이며 idempotency 재요청도 현재 권한을 다시 검사한다.

DP13 최소 모델 계약: 서버 허용 모델 참조와 capability/context/output/가격을 검증하고 credential은 서버 설정 참조만 사용한다. 임의 model명/URL/key를 클라이언트에서 수용하지 않는다. 기존 AiGateway 예약→발사→관측/unknown 정산과 중지·취소·timeout를 동일하게 사용한다. RAG는 사용자 변수 입력을 검색 query와 구분하고 검색된 근거를 신뢰된 지시문과 분리한다.

### DP11-04 증적·비교·승인 연결

`portal.builder_test_results`는 tenant/run/user/version/model/policy/자료지문/종료상태/usage/평가를 저장한다. 개인 입력·출력은 owner 접근만 허용하고 관리자 목록은 본문 없는 최소 메타데이터만 제공한다. 동일 저장 버전/평가셋의 결과를 비교한다. 평가셋은 expected claims/source/실패 판정과 수동 평가를 구분하고 최소 합성 general/rag/부족근거 사례로 검증한다. DP12 요청에는 test_run_id와 저장 버전을 함께 연결하며 다른 버전·정책·회수 자료의 증적을 재사용하지 않는다.

## 5. 실제 파일과 순차 작업

| 작업 | 파일/책임 | 완료 기준 |
|---|---|---|
| DP11-01 | 신규 backend/app/builder/{templates.py,routes.py,__init__.py}, backend/tests/test_builder.py; 변경 app/main.py, frontend/src/{AssetsPage.tsx,BuilderPreview.tsx}, apps/admin-web/src/App.tsx | 기존 불변 저장·이력 UI 재사용, 템플릿 parser·저장 버전 조합 검증·RAG ACL 선택 범위·관리 메뉴·오류/조직 전환 |
| DP11-02 | 신규 migrations/030_builder_profiles.sql, app/builder/{repository.py,schemas.py}, tests/test_builder_profiles.py; 신규 frontend/src/BuilderProfileEditor.tsx | 구조화 프롬프트/자료scope/모델 참조 저장·과거 버전 조회·원본 lineage 복제·RAG 검색 시험 |
| DP11-03 | 후속 migrations/031_builder_test_runs.sql; 변경 app/ai/{repository.py,types.py}, app/execution/{manager.py,rag.py}; 신규 app/builder/execution.py, tests/test_builder_execution.py, frontend/src/BuilderTestRun.tsx | 개인 시험 admission/worker/SSE/cancel와 같은 gateway/예산/정산; 최소 모델 계약 |
| DP11-04 | 후속 migrations/032_builder_test_results.sql; 신규 app/builder/results.py, tests/test_builder_results.py, frontend/src/BuilderResults.tsx; DP12 승인 API 확장 계획 | 버전별 평가 증적·비교·본인 소유 경계·승인 증적 연결 계약 |

후속 migration 번호는 착수 때 최신 미사용 번호를 확인한다. 여기의030~032는 현재029 다음 연속 작업 계획이며 다른 새 migration과 충돌하면 더 뒤 번호를 쓴다.

### Task 1 — 저장 버전 조합 검증

- [x] 실제 코드/기준선 확인, 사용자 우선순위와 이 계획 기록.
- [x] template parser와 HTTP 권한/CSRF/revision 실패 테스트 작성·실행.
- [x] `compile_template(template: str, values: dict[str,str]) -> tuple[list[str],str]` 구현. 예시 테스트:

```python
def test_single_pass_binding():
    names, result = compile_template('대상 {{audience}}', {'audience': '{{secret}}'})
    assert names == ['audience']
    assert result == '대상 {{secret}}'
```

- [x] saved-version preview API 구현, RAG 선택 refs만 현재 ACL로 조회, 일반 대화 refs422. 화면에서는 기존 읽을 수 있는 자료 선택기를 재사용하며 UUID 입력을 요구하지 않는다.
- [x] 기존 AssetsPage에 builder mode와 조합 패널 추가, dirty/세션/조직 전환 결과 폐기.
- [x] `src/backend/.venv/bin/python -m pytest src/backend/tests/test_builder.py src/backend/tests/test_assets.py -q`로 fixture 시험. 환경에 맞는 backend cwd/PYTHONPATH 사용.
- [x] user/admin build와 신규 browser 사례를 격리 fixture에서 실행, 결과·실패도 기록.

### Task 2 — 구조화 저장·복제·검색

- [x] config/version/profile 단일 저장 transaction 설계와 RLS/함수권한 검증.
- [x] concurrent expected_revision 동일 수정 중 하나409; same ID same payload 동일 receipt, 다른 payload409 시험.
- [ ] system/developer/user 필드를 메시지 role로 구분하고 secret 참조 값은 서버에서만 해석한다. preview는 credential 대신 `[보호된 설정]`을 표시한다.
- [x] 원본version immutable 복제와 lineage, exact historical version 조회·현재권한 시험.
- [ ] QueryGateway 기반 검색시험 admission 및 비용/회수/검색 부족 처리, 문서 scope UI/비교 구현.
- [x] migration 격리시험→소유local 백업/행 fingerprint→반영→재시작/재적용 시험.

### Task 3 — 모델 시험·실패복구

- [x] fixed runtime contract를 분석하고 최소 허용 모델·가격·output 상한을 서버 registry로 정의한다.
- [ ] trial admission snapshot과 receipt/run/ledger를 원자 생성, worker부터 stream까지 권한 재검사한다.
- [ ] mock provider general/RAG 시험; timeout·cancel·budget·stop·mid-run revocation·unknown usage·restart 시험.
- [x] 같은 client_send_id 반복은 발사1회, 다른payload409; legacy 운영 run·개인 이력 보존 시험.
- [x] UI 진행·취소·terminal·실패·결과 불명/같은 요청 확인, 모의/실제 제공자 구분.

### Task 4 — 증적·완료 보고

- [ ] version/model/policy/자료 바뀐 시험결과는 기존 증적을 덮어쓰지 않는다.
- [ ] 정상·부족근거·권한거부 평가셋과 수동 평가/합성 자동평가를 구분한다.
- [ ] DP12 승인 연결은 구현되지 않은 상태에서 버튼만 성공 처리하지 않는다. 연결 전에는 “시험 증적 보관”까지만 표시한다.
- [ ] 파일 hash·원본 SQL checksum·기존 행 보존·검사별 최신 결과를 기록한다.
- [ ] 관련 설계23/진행02/총괄15를 갱신하고 좁은 완료와 전체 기능명세 미완료를 구분해 보고한다.

## 6. 수용 시험 매트릭스

| 경계 | 기대 결과 |
|---|---|
| 잘못된 placeholder/누락·초과 변수/길이/NULL/extra key | 422, raw 입력·secret을 오류/감사에 노출하지 않음 |
| 변수 안 표현식/괄호/HTML | 단순 문자열, 재귀/실행0, React text escape |
| 사용자/다른조직/CSRF없음/role 회수 | 403/404, 내용·시험 결과 없음 |
| 오래된 revision/저장 안 한 수정 | 서버409, UI 새 저장/최신 확인 필요 |
| draft를 기존 user catalog/run로 이용 | 기존404 유지 |
| 문서 미게시/삭제/다른개인/회수 | 조합·검색·실행/근거 재노출 차단 |
| 같은 요청·동시수정·네트워크 불명 | 저장/실행 중복0, 동일ID 결과 확인; 명시적 새 요청만 변경 |
| stop/quota/timeout/cancel/unknown | 기존 원장 보존·미발사해제·발사unknown 기록 |
| 조직/버전 전환 중 늦은 응답 | 이전 입력·결과 노출0 |
| 사용자/관리 빌드 경계 | 사용자 번들에 관리 Builder 구현 없음 |

## 7. 완료 산출물·예상 순서

각 Task는 코드·실제 화면·pytest/브라우저 결과·보존 증거와 Obsidian 구현/시험 노트를 제공한다. 일정은 임의 날짜 확정 대신 Task1 통과 후 실제 소요와 Task2~4 재산정으로 보고한다. 현재 기능 개발 시작 승인 상태이며 이 문서 작성만으로 DP11 구현 완료를 인정하지 않는다.

최종 DP11 완료는 Task1~4의 기능별 수용 통과다. 실제 Entra/제공자/기관 업무 평가와 DP12 운영 게시 승인은 별도 상태로 기록한다. 후속 순서는 DP11-01→DP11-02→최소 모델 계약+DP11-03→DP11-04→DP12 승인/게시와 DP13 전체 관리다.

관련: [[23 포털 UI UX 확정과 사이트 분리 검토]], [[02 포털 UI UX 작업 기록]].

## 2026-10-12 · Task1 실행 결과

[[27 DP11-01 Builder 템플릿 조합 검증 구현 결과]]·[[28 DP11-01 Builder 저장 버전 조합과 자료 권한 검증]]에 첫 묶음 실제 구현/검증을 기록했다. backend52/browser9 최신 고유 사례와 분리 빌드 통과, local 세 서비스 복구. Task2~4 미완료, 다음 Task2 구조화 프롬프트·복제·검색시험을 진행한다. 전체 DP11이나 운영 배포 완료로 표시하지 않는다.

## 2026-10-12 · Task2 착수 설계 보완

사용자 “네 진행 바랍니다”에 따라 Task2를 개발한다. Task2a 구조화 profile·불변 저장/버전 조회/복제를 먼저 독립 수용하고, Task2b QueryGateway 기반 실제 RAG 검색은 시험 admission·worker 계약을 필요로 하므로 Task3의 최소 실행 계약과 함께 연결한다. QueryGateway는 현재 정산 가능한 VerifiedRun/worker 권원을 요구한다. 임의 mock embedding/직접 모델 호출로 검색을 구현한 것처럼 표시하지 않는다. 이전 Task2에 있던 검색 요구는 삭제하지 않고 후속 Task2b로 보존한다.

030_builder_profiles는 version_id FK의 불변 JSON profile/hash와 actor별 동일ID receipt를 추가한다. save는 기존 검증된 registry 함수를 비공개 capability로 재사용하여 profile과 새 자산 버전을 같은 transaction에 저장한다. 과거 버전은 소급 수정하지 않는다. 공개 legacy append는 구조화 자산 변경을409로 거부한다. clone은 정확한 원본 version과 parent_version_id를 저장하고 재시도 시 현재 제작·자료 권한을 재확인한다. 모델 참조는 실행 방식의 기존 기본 모델 참조만 저장하며 임의URL/credential/key/모델 실행을 수용하지 않는다. preview는 schema role별 치환 메시지와 profile/config 지문을 반환하며 모델 호출은 없다. role별 값은 자산 템플릿이지 개인 시험 입력/credential 저장소가 아니다.

## 2026-10-12 · Task2a 완료와 후속 번호

[[28 DP11-02a 구조화 프롬프트 버전 저장과 복제 구현 결과]]·[[29 DP11-02a 구조화 프롬프트 복제와 데이터 보존 검증]]에 구조화 저장/버전 조회/복제/역할별 조합의 실제 구현과 local 보존·검증을 기록했다. credential 참조·민감값 치환과 실제 RAG 검색/모델 시험은 아직미완료다. SQL031 UUID 정규화 보완으로 후속 시험run migration은032 이상, 시험결과는033 이상을 사용한다. 표의031/032 제안 번호는 과거 계획이며 실제 착수 시 미사용번호를 확인한다. 다음은 Task2b+Task3 최소 시험 실행 계약이다.

## 2026-10-12 · Task2b/3 착수 계약

사용자 계속 진행 승인에 따라 migration032로 본인 소유 builder_trial과 정확한 자산 버전·profile·메시지·자료 scope를 봉인한다. 기존 운영 Agent gate/예산/정산/취소/재시작 회수를 그대로 적용하고 사용자 대화와 구분한다. 일반 모델 시험과 RAG 검색/근거 생성 시험을 지원하며 빈 문서 scope는 검색 확장 없이 부족근거로 종료한다. system/developer/user 조합은 단일 치환으로 저장하며 시험 결과는 별도 테이블에 보관한다. 화면은 저장 버전 시험·진행 조회·취소·동일 ID 복구를 제공한다. provider/가격은 현재 고정 최소 계약을 재사용하며 임의 모델/URL/비밀 입력은 받지 않는다. 모의 제공자 검증과 실제 유료 제공자 품질 검증을 분리한다. 자동 평가·증적 비교·DP12 승인 연결은 다음 단계다.

## 2026-10-12 · Task2b/3 실행 기반 결과

[[29 DP11-03a 저장 버전 모델 시험과 RAG 검색 실행 구현 결과]]·[[30 DP11-03a 시험 정산 취소 권한 회수와 데이터 보존 검증]]에 실제 시험과 local 검증을 기록했다. 최소 서버 모델 계약/본인 초안 admission/worker/정산/취소/현재 권한·자료 회수/동일 요청 복구/화면은 구현했다. final-only polling 선택으로 SSE 중간 출력 요구는 이력으로 남긴다. run+trial 원자 admission과 호출 직전 ledger reservation transaction을 구분한다. 독립 장시간 timeout 수용·증적 목록/평가 비교/DP12 연결·secret 참조는 후속이다. 다음 Task4 상세 구현, migration033 이상.


## 2026-10-12 · DP11-04 본인 시험 이력·수동 평가·버전 비교

사용자 계속 진행 승인에 따라 [[29 DP11-04 시험 이력 수동 평가와 버전 비교 상세 계획]]을 먼저 기록하고 [[30 DP11-04 시험 이력 수동 평가와 버전 비교 구현 결과]]·[[31 DP11-04 시험 증적 권한 평가 불변성과 비교 검증]]에 실제 파일/검증/미완료를 남겼다. 이력20건pagination·불변평가/동일ID복구·동일자산2시험비교·현재본인/관리/자료ACL을 실제 DB/API/React에 연결했다. 기존 사용자A/관리A/B승인방향은 유지한다. 서버최신122(74/63실행 중복제거)/브라우저단일13/user23admin26buildpass. local기존43표전행·33checksum보존→44표/34migration/127함수, 재적용무변경·새평가0행·primary유료호출/합성쓰기0. 세서비스복구HTTP200.

전체DP11/원본F완료·실제품질·기관수용·운영배포완료는아니다. 자동업무평가셋/과거원문재변조탐지 전체수용·상세금액/토큰비교·평가전체내보내기·DP12동적승인게시·secret/다중모델·Entra/실제제공자 검증은후속이다. 다음DP11평가셋/승인증적계약 후DP12. 개인시험공개로권한을넓히지않고 승인용정확한version/run/result/profile/자료권원계약을구현한다. SQL000~033동결·034이상. 의미있는후속작업도동일Vault에계속기록한다.


## 2026-10-12 · DP11-05 업무 평가셋·자동 조건 검증

사용자다음작업진행승인에따라 [[30 DP11-05 업무 평가셋과 자동 조건 검증 상세 계획]]→[[31 DP11-05 업무 평가 사례와 자동 조건 검증 구현 결과]]·[[32 DP11-05 평가셋 권한 입력 근거와 불변 검증]] 순으로기록했다. 본인저장버전/입력사례·필수/금지문구/답변유형/실제자료기대조건을불변저장하고기존시험원장으로실행·literal-v1자동검증·중복복구·현재ACL·증적표시를실제API/DB/React에연결했다. 자동검증은의미적품질·배포승인아니다. 변경파일/증거는구현31·시험32참조. 서버최신118(92/45/1별도실행중복제거)/브라우저단일16/user23admin27buildpass. 기존44표전행/34checksum보존→46표/35migration/131함수, 새평가표0행·재적용무변경·primary유료호출/합성쓰기0·세서비스복구HTTP200. 최초UI타입오류/브라우저시험기대오류/증거메타데이터상수오류는시험32에기록했다.

다음은승인용정확한증적공유계약→DP12동적승인게시다. batch평가/semanticjudge·실제업무평가셋/전문가품질·역할negativecase제품실행·원문재변조전체수용/상세금액토큰/내보내기/secret·다중모델·Entra/실제제공자/UAT/운영배포는후속이다. 원본F전체완료수재산정없음. SQL000~034동결·035이상. 사용자A/관리A/B승인방향은유지하며개인시험입력을타인에게광범위공개하지않는다.


## 2026-10-12 · DP11-06 승인용 시험 증적 공유

사용자 진행 승인에 따라 [[31 DP11-06 승인용 시험 증적 공유 상세 계획]]을 먼저 기록하고 [[32 DP11-06 승인용 시험 증적 공유 구현 결과]]·[[33 DP11-06 증적 공유 독립 자료 권한과 철회 검증]]에 실제 파일/검증/실패/미완료를 남겼다. 개인 owner RLS는 유지하며 명시 동의한 exact run/evaluation/version/result 최소 snapshot만 현재 조직 PADMIN에게 공유한다. 검토자의 own 자료 ACL을 재검사하고 본인 철회 후 상세를 숨긴다. 질문/답변/기대문구/개인평가 의견은 공유하지 않는다. 기존 고정 설정 승인과 구분한 Builder 증적 B안 목록/상세를 승인 메뉴에 연결했으며 상태는 제출·미승인이다. 서버73 최신(신규12/기존61 별도)·브라우저19 단일·user23/admin29 build pass. local 기존46표/35checksum보존→47표/36migration/132함수·공유0행·세 서비스복구·primary합성/유료호출0. SQL000~035 동결. 다음 DP12 타인 승인/반려/재요청/공개·동적 실행·폐기/rollback이다. 이번 제출을 승인·게시·운영 배포로 확대하지 않는다. 실제제공자·Entra·업무품질/UAT와 이전 잔여·원본F완료수는 변경하지 않는다.

## 2026-10-12 · DP12 동적 Agent 승인 게시와 사용자 실행

사용자 진행 승인에 따라 [[32 DP12 동적 Agent 승인 게시와 사용자 실행 상세 계획]]을 먼저 기록하고 [[33 DP12 동적 Agent 승인 게시와 사용자 실행 구현 결과]]·[[34 DP12 동적 승인 공개 대상 실행과 정산 검증]]에 실제 파일/결과/실패/미검증을 남겼다. 본인 exact 공유 증적에서 공개 대상을 제출하고 다른 PADMIN이 검토하여 승인/반려한다. 승인+게시 snapshot 원자 저장·publication CAS/동시 receipt·자기 승인 거부·현재 own 자료 ACL·mode/정책/버전 검사를 구현했다. 일반 USER는 동적 catalog/변수/실행/취소/본인 이력에서 승인 snapshot만 기존 Gateway/예산/dispatch/meter로 실행하며 RAG private자료 권한은 전이되지 않는다. 빈 자료provider0·철회/삭제/취소의 답변 비저장과 비용 보존을 검증했다. 기존 A/A/B UI와 고정 승인·개인 owner RLS는 유지한다.

서버166 최신(기존144+최종신규22 별도 실행)·브라우저27 단일·user24/admin31 build·local47표/36checksum보존→50표/38migration/138함수·신규3표0행·primary 합성/유료 호출0·세 서비스복구HTTP200이다. SQL000~037 동결·후속038 이상. 이번 단위는 local mock 실제 앱 기능이며 운영 배포·전체 DP12/F완료가 아니다. 이전 미구현 기록은 당시 이력이고 다음은 이전 게시 버전 복원 승인/rollback·배포 이력 비교 및 사용자 이력 탐색 통합이다. 승인자 배정·동적 즐겨찾기/다회차 대화·secret/다중모델/tool/workflow·실 provider/Entra/UAT/운영 배포 및 이전 DP11 잔여는 유지한다.

## 2026-10-12 · DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교

사용자 진행/계속 진행 지시에 따라 [[33 DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교 계획]]을 먼저 기록하고 [[34 DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교 구현 결과]]·[[35 DP12-02 복원 승인 이력 보존과 사용자 실행 검증]]에 실제 파일/실패/미검증/안전 근거를 보존했다. 과거 승인 snapshot을 별도 타인 승인으로 복원하며 current 공개 대상을 유지하고 공유철회·정책/모드·현재자료권한·회원활성·게시CAS를 검사한다. 새 publication revision으로 기존 실행/정산에 연결하고 immutable 게시/복원/철회 metadata와 two-version 비교를 관리 B에 제공한다. 기존 누락 과거 철회/actor는 추정하지 않는다.

서버 이번35 최신(34단일+과거backfill1 별도)·브라우저28 최신 별도집계·user24/admin32 build·local50표 기존 행/열·38checksum보존→51표/39migration/140함수·재적용 무변화·primary합성/paid0·세서비스HTTP200이다. SQL000~038동결·후속039이상. 이는 local mock 실제앱 단위이며 전체 DP12/F·실 provider/Entra/UAT/운영배포 완료가 아니다. 다음 사용자 전역 동적 실행 이력·철회 Agent 최소기록 탐색·기존 대화 탐색 통합이며 기타 DP11·모델/secret/tool/workflow 잔여는 유지한다.

## 2026-10-12 · DP12-03 사용자 전역 실행 이력과 철회 기록

사용자 진행 승인에 따라 [[34 DP12-03 사용자 전역 실행 이력과 철회 Agent 기록 탐색 계획]]→[[35 DP12-03 사용자 전역 Agent 실행 이력과 철회 기록 구현 결과]]·[[36 DP12-03 실행 이력 소유권 철회와 현재 답변 권한 검증]]에 실제 변경 파일·검증 근거·실패/미검증을 기록했다. 사용자 메뉴/AI 업무에서 본인 전역 동적 실행을 조회하며 철회/버전변경/대상·자료회수 시 최소 record만 보존하고 이름/답변을 숨긴다. 기존 current exact guard·owner/조직·CSRF/취소/정산은 유지한다. 질문/원문/개인시험을 일반 대화에 혼합하지 않는다.

서버 이번52 최신(별도 실행 집계)·브라우저 최신12 별도 집계·user25/admin32 build·primary51표 전행/39checksum보존→51표/40migration/141함수·재적용 무변화·합성/paid0·세서비스HTTP200. SQL000~039동결·후속040이상. 실제 local mock 단위이며 전체DP12/F/실 모델·Entra·UAT/운영 배포 완료가 아니다. 다음 동적 즐겨찾기/My Agent 연동 상세 계획이며 다회차memory/제목핀삭제/비용토큰/과거답변재허가·이전DP11·secret/다중모델/tool/workflow·복잡승인은 남아 있다.
