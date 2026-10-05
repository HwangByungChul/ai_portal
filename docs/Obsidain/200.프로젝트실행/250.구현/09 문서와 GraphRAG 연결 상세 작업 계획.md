---
title: 문서와 GraphRAG 연결 상세 작업 계획
created: 2026-10-05
updated: 2026-10-05
status: planned
stage: 250.구현
tags: [implementation-plan, graphrag, C, tenant-isolation]
---

# I250-C Implementation Plan — 문서와 GraphRAG 연결

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 사용자 결정에 따라 현재 대화에서 순차 수행하며 단계별 결과와 다음 작업 계획을 보고한다.

**Goal:** 합성 문서7개 버전을 실제 저장·색인하고 권한을 통과한 원문 근거로 규정/책무 Agent가 답하도록 연결한다.

**Architecture:** 기존 portal의 세션/현재 조직·역할·중앙 gateway·원장을 확장한다. 순수 처리 코어를 `src/common_core`에 선택 이관하고 권한/저장/Job/호출은 단일 backend가 강제한다. 기존 GraphRAG의 별도 서버나 mock 권한 경로를 함께 실행하지 않는다.

**Tech Stack:** 기존 Python/FastAPI/PostgreSQL15·React/TypeScript. pgvector(1536) 준비 상태는 C01에서 실제 확인한다. 생성 gpt-4o-mini/임베딩 text-embedding-3-small을 유지한다.

**Spec:** [[200.프로젝트실행/240.설계/03 데이터 모델과 RLS 설계]], [[200.프로젝트실행/240.설계/04 API와 실행 상태 설계]], [[200.프로젝트실행/240.설계/05 AI 호출과 사용량 원장 설계]], [[200.프로젝트실행/240.설계/06 문서와 GraphRAG 설계]], [[200.프로젝트실행/240.설계/08 검증과 재현 설계]], [[200.프로젝트실행/230.분석/03 GraphRAG와 백엔드 재사용 분석]]. 이 문서는 다음 단계 계획이며 C 구현/시험 결과가 아니다.

## Global Constraints

- 원본 GraphRAG는 읽기만 한다. 원본 HEAD913f3881b4a4a73b9f764f60575775ecdbba6bdd 및 9개 선택 소스 SHA를 B06 근거에 기록한다. 원본의 기존 요구문서 수정은 사용자 작업으로 보존한다.
- 기존000~008 SQL/primary 사용·예약·대화·키/합성9파일/Q20를 유지한다. 추가 SQL009 이후 순차 적용. 총31 논리모델/41 API 설계를 유지하며 현재16 모델/27 API에 필요한15 모델/14 API를 추가한다.
- 기존 InMemory Graph/Vector는 mock·시험 참고다. PGVector/PostgreSQL 어댑터의 NotImplementedError를 성공 결과로 바꾸지 않는다.
- A/B 논리 격리 + 문서 owner/private reader + publication + exact-version Grant를 서버 현재 권한과 FORCE RLS로 확인한다. TADMIN/PADMIN 역할만으로 개인 원문을 공개하지 않는다.
- runtime 인덱서는 정답 manifest의 관계/근거 및 Q20를 읽지 않는다. EV marker·정답·금지목록을 embedding/모델 문맥에서 제외한다.
- 실 임베딩/질문은 기존500원 대표 배정에서 B06 기발생 사용+예약을 제외한 범위에 상세 사전 token/reservation 계획을 만든 후 수행한다. 비용을0으로 reset하거나 새 한도를 자동 추가하지 않는다. 실제 호출이 막혀도 저장/권한·순수코어·mock 검증은 독립적으로 진행한다.
- RAG는 provenance 검증 후 본문을 공개한다. 검증 전 자유 생성 draft를 사용자에게 전송하지 않는다. 과거 답변도 모든 출처의 현재 ACL/공개/Grant를 검사해 회수 후 본문을 차단한다.
- Q20 각 execution.status는 실제 평가 전까지 not_run이다. 보고서는 별도 평가 실행 결과로 작성하고 원본을 덮어쓰지 않는다.

## 순차 작업과 일정 배정

기존10/18~10/24 문서·GraphRAG16h+격리/색인검증4h=20h 배정을 아래처럼 나눈다. 각 시간은 예비 배정이며 자동 실행 경과나 실제 개인 학습시간이 아니다. 10/24 파일럿·10/28 기능동결·10/31 종료 목표를 유지한다. C01에서 환경/보안 복잡도를 확인한 뒤 80h 안에서 재배분하고, 초과 시 장식/추가 포맷/검색 튜닝을 먼저 줄인다.

| 작업 | 예비 시간 | 결과 | 선행/완료 기준 |
|---|---:|---|---|
| C01 저장·현재 ACL·pgvector 기반 |3h|추가15 모델/복합FK·RLS·역할·소유 파일 경계, extension 준비 진단|기존 원장 보존/잘못된role·조직·private 접근 거부. 미설치이면 실제 벡터 검증은 blocked |
| C02 선택 코어·문서 파싱·규칙 Graph |3h|원문 mapping/512token chunk/GR01~10/정확한 관계별 근거, 순수 계획 산출|원문 구간 재검사·상한 초과 provider0·Q20 정답 미참조 |
| C03 등록·Job·중앙 임베딩·공개 |4h|등록/동일ID/버전/lease·checkpoint·벡터 지속 저장·publish, 삭제 정리|재시작 유료 재발사0·known batch 재사용·불명needs_review/기존pointer 유지 |
| C04 ACL 검색·RAG·인용·Grant |4h|Vector+Graph 검색/문서별버전 선택/typed RAG/출처sealed·현재검사|공유v1/미공유v2·private·회수/삭제에embed/generation/body 우회0 |
| C05 문서·Job·공유·출처 화면 |3h|실 API 문서관리/처리단계·버전공유/규정Agent·인용보기|A/B 전환·권한/상태·같은ID 복구. 등록202를완료로표시하지않음 |
| C06 합성7버전·Q20·통합 인계 |3h|실제 등록/색인/검색평가·현재ACL/재시작 증거·260 인계|모의/실제·목표/관측/완료·차단을 구분. 전체V41 판정은260/280 |

다음 작업은 C01이다. C02 이후 구현은 C01 결과와 다음 상세 계획으로 순차 진행한다.

## C01 — 다음에 수행할 상세 작업

Files planned: `src/backend/migrations/009_document_graph_schema.sql`, `010_document_policy_control.sql`; `app/documents/policy.py`, `storage.py`; `tests/test_c_schema.py`, `test_document_policy.py`, `test_source_storage.py`; `250.구현/10 문서와 GraphRAG 저장 기반 구현 결과.md`; `260.테스트/evidence/C-rag/C01-*.json`.

- [ ] 1. baseline: 기존9 SQL checksum/16 업무·infra1/46 함수·primary 사용/예약/원장/키 해시·원본 소스 지문 확인. 차이가 있으면 기존 변경을 보존하고 영향 범위만 보고한다.
- [ ] 2. pgvector: 소유 cluster에서 `pg_available_extensions`/extension 설치·version·vector1536 유한 입력·정확 cosine 검색·rollback을 확인한다. 서버 설치와 DB 활성화를 구분한다. 사용할 수 없으면 준비 원인·구체 재현 절차를 기록하고 벡터 완료를 주장하지 않는다.
- [ ] 3. 추가15 모델: security의 operation_receipts/document_access/private_readers/publications/share_grants/job_authorizations, rag의 document_versions/index_builds/jobs/chunks/entities/relations/evidence/relation_evidence, portal.answer_evidence를 설계의 정확 필드와 대조한다. 기존16을수정/추가하는제약은새migration으로만적용한다.
- [ ] 4. 복합키: tenant+document/version/index, relation의 양 끝 동일index, 원문근거·publication pointer·Grant exact version, source/mode/pipeline fingerprint·활동 Job 유일성을 SQL로 강제한다.
- [ ] 5. 정책 adapter: `resolve_readable_version(ctx, document_id, version_id=None)`는 서버 AuthContext·현재 활성 ACL/publication·허용Grant를 검사한다. 요청의 owner/tenant/role 주장을 신뢰하지 않는다. 반환은 허용 exact version/index의 내부 계약이며 무권한과존재불명을외부404로통일한다.
- [ ] 6. 제한 함수/role: ai_web 원문·원장 직접쓰기0, ai_index는 특정version/lease/epoch 위임만, ai_meter 본문SELECT0, executorNOLOGIN/fixed search_path/PUBLICexecute0. 새로운 함수 수는 실제 catalog로 기록하며 기존46에하드코딩추정하지않는다.
- [ ] 7. 비공개 source storage: 서버 UUID object key/0700dir·0600file/허용UTF-8 TXT·Markdown/size·NUL검사. 원본path입력·외부URL fetch·HTML실행0. 임시 object→atomic rename→DB 접수commit 분리, orphan비공개정리·사용자다운로드는ACL라우트로만제공한다.
- [ ] 8. DB/파일 검증: A-U1/A-U2/B-U1/DUAL/ADM/P-A/회수 상태로 직접role/FK/RLS·private 관리와본문읽기분리·staging공개금지·v1/v2Grant를 검증한다. 테스트가정과 실제강제를구분한다.
- [ ] 9. primary 적용: disposable에서검증한009/010만checksum기반적용/재적용0 확인. 기존행/key/사용·예약불변을대조하고 불필요한seed/reset을하지않는다.
- [ ] 10. 관련 backend 회귀·build/기존화면회귀에서 B 동작이 유지되는지 확인하고 실제발사0·connection0·서버상태복원 증거 기록.
- [ ] 11. C01 결과 및 C02 세부 계획을 보고한다. extension이 막혀도 정책/문서 순수 처리 등 독립 작업의 완료 범위를 분명히 남긴다.

## C02 — 순수 코어 이관 계약

Files planned: `src/common_core/ai_pipeline/document/{schemas,parser,chunker,mapping,pipeline}.py`, `graphrag/{schemas,extractor,evidence,context}.py`; backend `app/documents/plan.py` and exact-position tests.

- [ ] 기존 DocumentPipeline/Parser/Chunker/DomainSchema·RelationExtractor 구조를 선택 이관하고 원본 라이선스/commit/파일 지문을 provenance에 남긴다. 원본 truncation·UUID재생성·무권한preview를 그대로 이식하지 않는다.
- [ ] CRLF/BOM/Markdown 제거 전후 원문Unicode offset·행 mapping 보존, 문장 경계512token/chunk·overlap0·버전128chunk/512evidence/512entity/1024relation/2048edge 상한 사전검사.
- [ ] GR01~10 긍정 문형/방향·alias를 원문에서 추출하고 관계별exact_quote를 연결한다. 미지원/부정/조건 불명은 coverage partial이며 추정Graph0.
- [ ] 코어에는 DB/키/HTTP/현재권한 결정이 없다. runtime 계획은원문+등록metadata+고정schema만 입력하고 평가정답은 테스트대조 전용이다.

## C03 — Job와 비용 경계

Files planned: documents/jobs routes·repository·runner, ai gateway/provider 확장, index/Job 제한 함수와 tests.

- [ ] upload receipt/client_upload_id·same payload reuse/다른payload409, publication≠processing 상태, 내부원문 위임·CAS/lease60s·epoch fence.
- [ ] validate_source→parse_plan→embed_batches→validate_index→publish 순서. 청크8개/4096token 이하 배치·1536유한벡터·usage·checkpoint/hash/mode 일치 후 batch commit.
- [ ] central embed_document permit/dispatch/settle 단일 경로. 벡터+checkpoint는같은DB transaction, 외부호출·정산은별개다. unknown은needs_review, 자동재호출0; 확정정산+지속벡터배치만 새Job에서재사용.
- [ ] publish 직전 현재권한·lease·삭제/Agent/규모/근거를 재검사해 pointer+Jobcompleted+감사를 commit. 실패하면기존publicpointer보존.
- [ ] 삭제 접근차단commit 후 purge-only cleanup 위임으로원문/파생payload를정리하고 기존비용·ID/원장보존.

## C04~C06 — 검색부터 평가까지

- [ ] Vector 후보/Graph 확장은 허용version/index집합 안에서만 실행. 공유B v1만허용일때 v2 존재/담당/기한을노출하지않는다. 관계별출처·조건을보존하고 근거부족은hold/insufficient_evidence, DB오류는failed로분리한다.
- [ ] embed_query와generate_rag는 기존centralgateway, typed출처ordinal/quote검증·sealed provenance·저장정본후SSE공개. 모든본문조회에현재all-source gate 적용.
- [ ] 문서관리/Job 최소정보, 등록·처리·공개·cleanup 상태를분리. private title/원문은현재read권한없으면숨기고 관리자역할만으로본문을보이지않는다.
- [ ] 합성7버전(D-A-R1/R2/P, D-B-R1/P, D-S v1/v2) 실제등록·색인, 원문SHA/구간으로EV 대조. Q20 각상태/근거/허구·누설·공유회수/재시작을별도평가결과로기록한다.
- [ ] 후속260/270/280/290/300 단계로 전체요구V41·처음부터끝까지파일럿·시연·이행·종료 자료를 인계한다. B06 또는 C 코어단위시험만으로전체MVP완료를선언하지않는다.

## 실행·검증 명령

각 C 작업의 구현 시 `.venv/bin/python -m pytest tests/test_c_schema.py tests/test_document_policy.py tests/test_source_storage.py -q` 등 실제 생성한 관련시험을 먼저 실행한다. 이후 기존 B 영향을 확인하는 회귀와 브라우저 build/e2e를 수행한다. 현재이명령은계획이며해당C파일/시험은없다. 실제유료임베딩은 C03 상세계획의사전token/예산표와원장조건을충족한뒤에만실행한다.
