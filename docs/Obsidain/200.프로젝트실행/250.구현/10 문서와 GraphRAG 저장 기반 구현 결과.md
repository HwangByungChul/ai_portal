---
title: 문서와 GraphRAG 저장 기반 구현 결과
created: 2026-10-05
updated: 2026-10-05
status: completed
stage: 250.구현
tags: [C01, implementation, document-policy, pgvector]
---

# I250-C01 문서와 GraphRAG 저장 기반 구현 결과

C01의 문서·버전·공유 권한과 비공개 원문 저장 기반을 완료했다. 실제 DB로 격리/벡터/권한을 검증한 후 기본 환경에는 새 SQL 2개만 적용했다. **문서 업로드 API·화면, 실제 GraphRAG 파싱·색인·답변은 후속 단계이며 아직 사용할 수 없다.**

## 1. 완료 범위

| 항목 | 결과 |
|---|---|
| 저장 모델 | 기존 16개 + 문서 관련 15개 = 업무 31개, infra 1개 별도 |
| DB 변경 | 009/010 추가, 총 11 migration, 반복 적용 0건 |
| 정책 | 기존 46 + 신규 3 = 고정 security 함수 49개, 새 payload 9개를 포함한 FORCE RLS 17개 |
| 벡터 | native PostgreSQL 15.18에서 pgvector 0.8.6/1536차원/유한값/정확 코사인 거리·rollback 검증 |
| 접근 | 현재 세션/소속 + 소유자·개별 reader + 게시 포인터 + exact-version Grant |
| 원문 | UTF-8 TXT/Markdown, UUID 경로, 0700/0600, SHA 무결성, 덮어쓰기·symlink 우회 차단 |
| 활성화 | 기본 RAG Agent 비활성 유지, 새 15테이블은 모두 0행, API는 기존 27개 |

`security.document_access/private_readers/document_publications/share_grants/job_authorizations/operation_receipts`, `rag.document_versions/index_builds/jobs/chunks/entities/relations/evidence/relation_evidence`, `portal.answer_evidence`를 추가했다. source/pipeline/mode 및 조직·문서·버전·index 복합 FK, 같은 index의 관계 양 끝과 근거, 활동 Job 유일성을 강제한다.

## 2. 현재 권한과 버전 선택

`resolve_readable_version(pool, ctx, document_id, version_id=None)`은 서버 AuthContext와 현재 DB 세션/소속을 재검증한다. 최신 전체 버전을 고른 후 공유 여부를 확인하는 방식 대신 **허용된 게시 버전 중 최신**을 선택한다. 소유 A 조직은 게시 v2, 공유 v1만 허용된 B 조직은 v1을 반환하며 staging v3는 숨긴다.

private는 소유자/초기 명시 reader만 읽을 수 있다. A 관리자와 담당 플랫폼 관리자는 관리 역할만으로 title/본문에 접근하지 못한다. 공유 철회/원 조직 비활성/문서 삭제/게시 해제/세션·소속 회수는 다음 조회부터 차단된다. 같은 버전의 게시 index가 교체되면 이전 index 청크도 조회되지 않는다.

없는 문서와 무권한 문서는 같은 내부 `DOCUMENT_UNAVAILABLE` 결과를 사용한다. HTTP의 공통 404 매핑은 신규 문서 라우트를 만드는 C03에서 연결한다. C01에서 새 문서 HTTP API를 시험한 것으로 집계하지 않는다.

## 3. runtime 역할

ai_web은 허용된 게시 문서만 읽고 제어 테이블이나 원장을 직접 수정하지 못한다. ai_index는 특정 Job/조직/문서/버전/index의 lease hash·epoch·만료와 현재 initiator 관리 권한이 일치할 때 staging payload를 읽고 추가한다. 다른 버전·게시 index·private 대상과 임의 epoch/claim은 거부된다. cleanup 위임에는 원문·청크 읽기 권한을 부여하지 않았다.

ai_meter는 새 본문·벡터·근거 SELECT 권한이 없다. 새 GraphRAG에 대해 NOLOGIN 정책 실행자는 제어에 필요한 식별자/상태만 읽으며 title/source key/text/quote/vector는 읽지 못한다. 모든 security 함수는 고정 search_path/전용 owner/PUBLIC EXECUTE 0을 유지한다. 일반 대화의 기존 owner 제한 함수에 필요한 B 단계의 본문/snapshot SELECT 예외는 보존했다. **RAG 대화 전체 근거 재검증은 C04에서 구현한 후 활성화한다.**

## 4. 원문 저장

`app/documents/storage.py`는 제목 200자/원문 128KiB·40,000자, UTF-8·NUL·허용 MIME을 검사한다. 서버 UUID의 `tenants/{tenant}/documents/{document}/{version}/source` 경로만 사용한다. 디렉터리와 파일의 owner/mode를 검사하고 dir-fd + NOFOLLOW로 링크/경로 우회를 막는다. 원문 SHA·길이·문자 수를 읽을 때 다시 확인한다.

임시 파일을 fsync한 뒤 atomic **add-if-absent hard link**로 게시하고 임시 파일을 제거한다. 덮어쓸 수 있는 rename 대신 추가 전용 원자 동작을 사용한 구현 결정이다. 동시 쓰기에서는 하나만 성공하며 기존 파일은 보존된다. 저장기는 HTML/Markdown 지침을 실행하거나 외부 URL을 가져오지 않는다.

파일 저장과 DB commit은 별개다. 등록 실패 시 파일은 비공개 orphan으로 남을 수 있다. 자동 orphan 정리·commit 불명 복구·삭제 cleanup과 사용자 다운로드 라우트는 C03에서 현재 권한/등록 상태를 확인한 뒤 연결한다. 저장기 자체가 사용자 권한을 판정하는 공개 API는 아니다.

## 5. 검증 결과

| 시험 | 관측 결과 |
|---|---|
| 최종 C01 관련 선행 시험 | 107 pass / 0 fail / 77.52초, 신규 101 + 기존 migration 6 |
| 전체 backend | 599 pass / 0 fail / 0 warning / 582.72초 |
| frontend 빌드·기존 브라우저 | build pass / A20+B31=51 pass / runner 0 / 118.16초 |
| 신규 schema/policy/storage | 22/52/27개 시험, 전체 backend에 포함 |
| 기본 적용 | 새 2 SQL / 반복 0 / 기존 16개 내용 SHA 동일 / 추가 15개 0행 |
| 비용·정리 | 새 유료 호출 0회·0원 / 기존 내부 집계 0.19원·예약 0·slot 0 / runtime 연결·임시 DB·listener 0 |

관련 107개와 전체 599개를 더해 집계하지 않는다. 브라우저는 native HTTP·PostgreSQL·mock provider이며 실제 OpenAI 브라우저 검증이 아니다. 이번 작업에서 실제 키를 provider에 주입하거나 유료 임베딩을 실행하지 않았다.

첫 관련 시험에서 102 pass/1 fail은 시험의 AuthContext 필드명 오류였고 수정했다. 공유/게시 불변성 검사를 추가하는 과정에서 공용 트리거가 다른 테이블의 OLD 필드를 평가하는 문제가 나타났다. 해당 테이블 분기 안으로 검사를 옮긴 후 최종 107개와 전체 회귀를 통과했다. 전체 backend 통과 후 첫 브라우저 실행은 신규 FK 때문에 전용 시험 DB 초기화가 거부돼 51개가 실패했다. 기본 DB를 거부하는 기존 보호 조건을 유지하고 초기화 대상에 참조하는 새 payload 테이블만 추가한 후 build/51개 브라우저를 재검증했다. 마지막 변경은 브라우저 시험 제어 스크립트에만 한정되며 제품 backend 소스는 전체 599개 통과 시점과 동일하다. 기본 DB 적용은 이 화면 회귀 이후에만 수행했다.

## 6. 확장 준비·재현

처음 native PostgreSQL 15에는 pgvector가 없었다. 공식 [pgvector v0.8.6 README](https://github.com/pgvector/pgvector/blob/v0.8.6/README.md)의 PG13+ 지원과 설치 절차를 확인하고 소스 commit `8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c`을 사용했다. 기존 PostgreSQL 버전이나 전역 기본 서버를 변경하지 않았다.

빌드 시 PostgreSQL이 기록한 MacOSX14.sdk 경로가 현재 없어서 실패했다. make의 `PG_SYSROOT`만 현재 `MacOSX.sdk`로 지정해 재빌드했고 PostgreSQL 설정 파일은 수정하지 않았다. `PG_CONFIG=/usr/local/opt/postgresql@15/bin/pg_config`, `with_llvm=no`, `OPTFLAGS=` 조건과 임시 staging install을 사용했다.

native PG15 경로에 **기존에 없던** `vector.so`, `vector.control`, `vector--0.8.6.sql` 3개만 추가했다. 기존 파일은 덮어쓰지 않았다. DB 활성화는 소유 fixture/기본 프로젝트 DB의 rag schema에 한정한다. 정확한 설치 파일/지문/소스·SDK 조건은 `C01-installation.json`에 기록했다. 다른 환경에서는 해당 PostgreSQL 버전에 맞는 확장 준비가 선행돼야 한다.

## 7. 보존·산출물

기존 SQL 000~008 9개, 합성 입력·평가 9개와 비공개 설정/실제 B06 결과 파일을 포함한 보호 파일 24개 및 기존 증거 42개는 동일하다. 기존 대화/사용량/실제 3회 호출 기록·내부 0.19원·예산/예약을 초기화하지 않았다. 기본 app.env/mock 모드·RAG 비활성·키·runtime credential bytes를 보존했다. 미추적 사용자 파일 72개와 원본 GraphRAG는 수정하지 않았다.

정제 증거는 `260.테스트/evidence/C-rag/C01-*.json`와 README에 관리한다. 실제 검증 소스 115개 SHA를 기록했고 testcase 파라미터 원문/벡터를 공개하지 않는다. raw 로그/JUnit은 Git 제외 비공개 runtime에 둔다. 원격 push·배포·별도 채팅/agent 생성은 하지 않았다.

## 8. 다음 C02 상세 방안

다음은 **GraphRAG 순수 코어·문서 처리**다. 예상 3시간은 기존 C 배정의 분해이며 개인 실제 공수 확정값이 아니다.

| 순서 | 작업 | 예상 |
|---|---|---|
| 1 | 기존 GraphRAG 재사용 책임/소스 지문과 입력·산출물 계약 정리 | 25분 |
| 2 | BOM/CRLF/Markdown 처리와 원본 offset·행 mapping | 40분 |
| 3 | 512토큰 청크·overlap 0·상한·8청크 배치 계획 | 35분 |
| 4 | GR01~10 규칙/6개체·조건·방향·관계별 exact quote | 45분 |
| 5 | 순수 처리·회귀 시험, 실제 원문 산출물 대조와 C03 계획 | 35분 |

C02는 원문에서 청크/근거/Graph/배치 계획을 만드는 단계이며 유료 AI 호출 없이 진행한다. DB/키/현재 권한 결정은 backend에 남긴다. 평가 정답을 runtime에 넣지 않으며 미지원·부정·조건 불명은 Graph를 추정하지 않고 partial로 표시한다. 모든 근거가 원본 연속 구간과 일치하고 다른 조직/index의 근거가 섞이지 않아야 완료다.

파일별 구현·Interface·시험·완료 기준: [[11 GraphRAG 순수 코어와 문서 처리 상세 작업 계획]]. C03 등록/Job/중앙 임베딩, C04 검색·RAG/현재 근거 보호, C05 화면, C06 실제 7버전·Q20은 아직 미착수다. 전체 V41/MVP 완료 판정은 후속 260/280 단계에서 수행한다.

10월 31일 목표·주 20시간 이상·기존 80시간(여유 10시간 포함) 계획을 유지한다. 실제 개인 학습/개발 시간과 확정 잔여 공수는 미측정이다.
