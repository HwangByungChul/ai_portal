---
title: 문서 등록과 인덱싱 Job 구현 결과
created: 2026-10-05
updated: 2026-10-05
status: completed
stage: 250.구현
tags: [implementation-result, C03, documents, indexing, multitenant]
---

# I250-C03 문서 등록과 인덱싱 Job 구현 결과

관리 API를 통해 문서를 등록하고 처리 Job을 저장·재시작·게시·삭제 정리하는 기능을 구현했다. 실제 PostgreSQL/pgvector에 모의 임베딩을 저장해 흐름과 권한·원장 경계를 검증했다. 현재 WBS는 **I250-3 진행 중 / C01~C03 완료 / 다음 C04**다. 검색/RAG 답변·새 문서 화면·전체 파일럿/Q20는 아직 완료하지 않았다.

계획 [[13 문서 등록과 인덱싱 Job 상세 작업 계획]], 상위 [[09 문서와 GraphRAG 연결 상세 작업 계획]], 다음 [[15 ACL 검색과 RAG 답변 상세 작업 계획]], 증거 `260.테스트/evidence/C-rag/C03-*.json`.

## 구현한 흐름

1. 파일1개와 metadata JSON1개만 접수하고 actual stream/UTF-8 TXT·Markdown/크기·중복 필드·Origin/CSRF/현재 조직/관리 권한을 검사한다. 사용자 파일명 대신 서버 UUID의 비공개 경로를 사용한다. 개인 문서 관리 권한과 본문 읽기 권한은 구분한다.
2. client_upload_id와 request HMAC으로 같은 요청은 같은 document/version/index/Job을 반환하며 다른 내용은409로 거부한다. 기존 버전은 CAS를 검사한다. 접수 전 현재 권한과 receipt를 확인하고 새 접수10회/분, 조회120회/분을 제한한다. 문서 목록은 private 제목/본문/경로를 반환하지 않는 관리 metadata다.
3. Job의 mode·원 세션·현재 소속/관리 권한·Agent/삭제 여부를 재검사하고60초 lease/20초 heartbeat/300초 전체 기한·epoch/claim을 강제한다. 모의 서버가 real Job을 접수하지 않는다. 재시작에서 queued/만료 running 상태를 복구하며 current origin 회수와 Agent 중지는 raw index role에서도 차단한다.
4. C02 순수 계획으로 원문 SHA/mapping·청킹/Graph를 재구성한다. 배치는 최대8청크/4096token, 벡터는1536차원·유한·float32 범위/정규화 검증 후 저장한다. 기존 중앙 permit/dispatch/settle로 embed_document를 연결하며 새 비용 원장을 만들지 않는다. confirmed dispatch만 provider에 전송한다.
5. 벡터와 checkpoint를 동일 DB transaction에 저장한다. 저장된 known batch는 재전송하지 않으며 결과가 불명인 호출이나 정산만 있고 벡터가 없는 상태는 needs_review로 남긴다. 현재 권한·lease·mode·호출/usage·payload 개수를 확인한 뒤 pointer/Job completed/감사를 함께 commit한다.
6. 삭제는 접근 차단과 cleanup Job 접수를 먼저 commit한다. 현재 관리자용 고정 purge-only 함수가 원문/파생 payload를 제거하고 metadata-only 파일 삭제를 이어서 수행한다. 이전 ID/receipt/호출·비용 이력은 남긴다. 파일과 DB는 별도 commit이므로 오류 때 비공개 orphan을 유지하며60초가 지난 미등록 파일만 현재 권한·DB 부재가 확인될 때 정리한다.

기존 SQL000~010을 수정하지 않고011~013만 추가했다. 현재 업무31+infra1 테이블 /14 migration /66 security 함수 /17 FORCE RLS /pgvector0.8.6 /34 API다. 기존27 API에 관리 문서·버전·삭제·Job 조회/재시도7개를 추가했고 새로운 화면은 C05 범위다.

## 검증 결과

| 확인 | 실측 |
|---|---|
| 최종 신규 관련 시험 | 35개 통과 /39.53초 |
| 전체 backend 회귀 | 706개 통과 /649.66초 /실패0·경고0 |
| frontend build·기존 사용자/관리자 browser | build 통과 /51개 통과 /121.93초 /runner 오류0 |
| native 인덱싱 재시작 | queued→실 서버 재시작→completed→재시작 후 동일 Job /모의 호출1회 |
| checkpoint 복구 | 저장한 batch·lease 만료→새 epoch /provider 추가 전송0 |
| 삭제 | 게시 차단·cleanup 완료·파일/벡터 payload 제거 /비용·ID 보존 |
| primary 시작 | mock·index/execution 활성 /health 통과 /API34 /정상 종료 |

관련 시험은 전체에 포함하므로 합산하지 않는다. 권한/CSRF·멀티테넌트/개인문서/CAS·모드 혼합·Agent/세션 회수·입력/벡터/provider usage 변조·감사 rollback·unknown/재시작/서명 cursor를 검사했다. SDK 시험은 고정 가짜 HTTP transport로만 실행했고 실제 OpenAI 요청은0회다. checkpoint 복구는 저장된 batch와 만료 lease 경계를 검증한 것이며 실행 도중 강제 종료의 모든 시점을 검증한 결과는 아니다.

초기 시험에서 UTF-8 시험 literal, 신규 제한 함수 grant/RLS·게시 감사 정책, native 시험 종료 메서드 오류를 발견해 수정했다. primary 적용 전에 관련 및 전체 회귀를 통과했다. native 시험의 잔여 DB는 marker가 확인된 시험 DB만 제거했고 primary는 제외했다.

## 기본 환경 적용과 보존

기본 DB에는011~013만 적용하고 재적용은0이다. 적용 helper의 기존 설정 exclusive-create가 거부되어 설정 불변을 확인한 뒤 private 사본을 fsync/원자 교체했다. native 종료 검사의 SIGTERM 반환(-15)은 연결/listener0와 기존 행 불변을 함께 확인해 기록했다. 기존31테이블의 기존 column 투영 SHA가 모두 동일하다. 이전 일반 호출에 추가 index/batch column은NULL이며 새15 문서 관련 테이블에 primary corpus는 적재하지 않았다. 기본 모드는 mock, rules_rag는 비활성이다. 비공개 app.env 기존6줄 bytes/키를 그대로 유지하고 index role DSN와 index_enabled만 추가했다. 파일0600/디렉터리0700/Git 제외를 확인했다.

보호26파일 중 app.env를 제외한25파일 SHA 동일, app.env는 원래 prefix 동일 및 승인된2항목 추가다. 이전53증거·관련 없는 미추적73파일·원본 GraphRAG9선택소스/HEAD·합성/evaluation 파일을 보존했다. 이번 유료 전송0/추가비용0원, 이전 일반3회 내부 추정0.19원·예약0·slot0을 유지했다. 0.19원은 공급자 청구 확인값이 아니다. 최종 연결/임시DB/listener0·소유 DB 정지, 새 dependency/원격 push/배포/추가 agent0이다.

## 한계와 다음 작업

현재 저장된 벡터의 흐름·격리는 mock 검증이며 실제 임베딩 품질 결과는 아니다. unknown은 자동 재시도가 없고 수동 검토가 필요하다. source purge와 DB 상태는 한 transaction이 아니므로 durable cleanup 및 비공개 보상 규칙으로 복구한다. 전체 기관 운영·SSO/물리격리/HA·성능 SLA 완료를 주장하지 않는다.

다음 C04는 현재 허용 버전/Grant API → 중앙 embed_query·권한 검색 → 관계별 원문 근거/제한 문맥 → typed RAG 저장·sealed provenance·현재 all-source gate → 출처 다운로드·회귀·C05 인계다. 상세 파일/순서/완료 기준은 [[15 ACL 검색과 RAG 답변 상세 작업 계획]]에 작성했다. C04 예상4h는 기존 C20h 배정의 일부며 개인 실제 투입은 미측정이다. 10월31일·주20시간 이상/80h(여유10h 포함) 기준을 유지한다. Q20는 not_run이다.

실제 검증 소스 로컬 commit: 0c08d9ae700b90a0d016b4253b8f47ebb95623db.
