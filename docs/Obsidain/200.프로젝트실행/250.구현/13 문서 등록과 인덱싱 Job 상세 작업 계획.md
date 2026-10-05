---
title: 문서 등록과 인덱싱 Job 상세 작업 계획
created: 2026-10-05
updated: 2026-10-05
status: completed
stage: 250.구현
tags: [implementation-plan, C03, indexing, tenant-isolation]
---

# I250-C03 문서 등록과 인덱싱 Job

C02의 순수 처리 계획을 실제 문서 접수·Job·벡터 저장·게시로 연결한다. 사용자·관리자 화면은 C05, 권한 검색과 RAG 응답은 C04에서 연결한다. 현재 문서는 다음 작업의 계획이며 C03 실행 결과가 아니다.

참조: [[09 문서와 GraphRAG 연결 상세 작업 계획]], [[12 GraphRAG 순수 코어와 문서 처리 구현 결과]], [[../240.설계/04 API와 실행 상태 설계]], [[../240.설계/05 AI 호출과 사용량 원장 설계]], [[../240.설계/06 문서와 GraphRAG 설계]].

## 범위와 시간

기존 C 전체 20시간 중 C03 예상 4시간을 아래처럼 배분한다. 개인 실제 투입 시간은 미측정이다. 10월 24일 파일럿·28일 기능 동결·31일 종료 목표를 유지하며, 구현 난도가 예상보다 크면 추가 포맷·화면 장식·검색 튜닝을 먼저 줄인다. 안전한 재시작·권한·정산 검증은 생략하지 않는다.

기본 mock 상태와 등록된 키·기존 원장·기발생 내부 추정 0.19원을 보존한다. mock 및 고정 가짜전송 시험을 먼저 완료한다. 실제 임베딩은 별도 사전 토큰·예약 계획과 기존 대표 500원 잔여 한도 안의 승인 범위가 확인된 뒤에만 수행하며, 이번 계획 작성은 유료 발사 승인이 아니다. 불명한 발사 결과는 자동 재시도하지 않는다.

| 순서 | 예상 | 작업 결과 |
|---|---:|---|
| 1 | 30분 | 실행 경로·최소 인덱서 권한·추가 migration 설계 |
| 2 | 40분 | 등록 receipt·버전·원문 보상·조회 API |
| 3 | 45분 | Job claim·lease·epoch·현재 권한 검사 |
| 4 | 50분 | 중앙 임베딩 예약·정산·벡터 checkpoint |
| 5 | 40분 | 원자 게시·삭제 차단·cleanup |
| 6 | 35분 | 실제 DB/동시성/재시작 검증·C04 인계 |

## 1. 입력과 실행 경로

예정 변경: `src/backend/app/documents/`의 등록·Job·저장 adapter, `app/ai/`의 중앙 임베딩 경계, `migrations/011_*.sql`, 해당 pytest. 기존 000~010 migration은 수정하지 않는다. native 서비스는 backend와 src 두 import 경로를 명시해 `common_core`를 읽도록 설정한다. 기존 비공개 환경 값을 출력하지 않고, 필요한 `AI_INDEX_DSN`만 별도 최소 권한 연결로 추가한다. web/index/meter 역할을 서로 대신 사용하지 않는다.

기존 `call_attempts`는 일반 대화 run 중심이며 Job 호출을 허용하지 않는다. 새 migration에서 run 또는 job 중 정확히 하나를 갖는 부모 계약, tenant/version/index/epoch/batch/mode/model/가격 snapshot, `embed_document` operation을 설계와 대조한다. Job 비용도 동일 중앙 예약·발사·정산 규칙을 통과해야 하며 원장 직접쓰기나 임시 별도 과금 경로를 만들지 않는다. 함수·모델·API 수는 실제 적용 카탈로그와 route로 기록한다.

완료 기준: 잘못된 역할·조직·Job 부모·operation 거부, PUBLIC 실행 금지·fixed search_path·최소 grants, 기존 일반 대화 원장 불변.

## 2. 등록과 원문 보상

서버 AuthContext의 현재 소속·관리 권한을 확인한 뒤 등록ID/문서ID/버전ID와 입력 fingerprint를 receipt에 고정한다. 같은 ID·같은 내용은 동일 결과를 반환하고, 다른 내용은 409로 거부한다. 제목/UTF-8 TXT·Markdown/128KiB/40,000자 제한은 C01을 재사용한다. 요청 경로·파일명·owner 주장은 저장 위치나 권한 근거로 쓰지 않는다.

UUID 비공개 원문 atomic add와 DB commit은 별개다. 실패 직후 무조건 파일을 삭제하지 않고 receipt/버전의 commit 결과부터 재조회한다. 결과가 불명한 객체는 비공개 격리한 뒤 확인된 orphan만 정리한다. 다른 성공 접수에서 참조하는 객체를 삭제하지 않는다. 등록 202는 접수 완료이며 게시 완료가 아니다.

등록/버전/Job 조회와 관리 제어 API를 승인된 API 설계에 대응한다. 무권한·존재불명은 외부 404로 통일하며 비공개 제목·본문·저장 key를 노출하지 않는다. 사용자가 원문을 읽는 경로에는 현재 readable exact-version 정책을 적용한다.

완료 기준: 동시 동일 ID 접수 1개, 다른 입력 409, 파일/DB 양쪽 실패와 commit 불명 복구, 원문 덮어쓰기 0, 타인 private 원문 관리 권한만으로 읽기 0.

## 3. Job 생명주기

현재 관리 위임을 검증한 Job만 claim한다. lease 60초·heartbeat 20초·epoch를 바인딩하고 작업 deadline 300초 안에서 각 stage를 제한한다. 상태는 접수→계획 생성→임베딩→검증→게시 또는 실패/검토 필요로 구분한다. 기존 설계의 정확 상태값과 route 계약을 사용한다.

원문은 지정 version/index/lease/epoch 위임으로만 읽는다. private 문서의 기계 처리를 위한 제한 위임과 관리자 본문 읽기 권한을 구분한다. 현재 세션·소속·Agent·문서 미삭제·작업 관리 권한을 claim/배치 발사/게시 시 재확인한다. lease를 잃은 worker는 저장·발사·게시할 수 없다. 프로세스 재시작 때 상태를 읽어 이어가며 오래된 epoch로 결과를 반영하지 않는다.

완료 기준: 동시 claim 1개, lease 만료·회수·삭제 뒤 재검사 거부, 오래된 worker 반영 0, Job 화면 조회가 완료/실패를 임의 추정하지 않음.

## 4. 중앙 임베딩과 checkpoint

C02 계획을 검증하고 청크 최대 512토큰·overlap 0, 배치 최대 8청크/4096토큰/16배치로 고정한다. source/pipeline/parser/mode/index/model/dimension fingerprint를 호출과 저장에 바인딩한다. 고정 `text-embedding-3-small` 1536차원의 반환 개수·형식·유한값·벡터 유효성을 저장 전 검사한다.

배치마다 현재 예산 확인→원자 예약→단일 dispatch→usage 정산을 중앙 gateway에서 수행한다. 과금 실패/usage 불명/응답 유실은 unknown 또는 needs_review로 보존한다. provider 호출과 DB transaction을 하나의 원자 작업으로 표현하지 않는다. dispatch 이후 응답 저장·정산·checkpoint 각 실패창을 시험한다.

재사용은 같은 index·source·pipeline·mode의 검증된 저장 벡터와 확인된 비용 상태에 한정한다. 저장된 벡터 checkpoint는 DB transaction으로 기록한다. 정산과 checkpoint 중 하나만 남았으면 durable 기록을 대조해 복구하며, 유료 재발사로 해결하지 않는다. 실패한 다른 mode·버전·index 벡터를 가져오지 않는다.

완료 기준: mock provider와 고정 가짜전송에서 known batch 재사용·unknown 자동 재발사 0·예약 해제와 정산 상호배타·배치 호출 1회·잘못된 1536 벡터 게시 0. 실 호출 시 실제 usage/금액은 별도 증거로만 집계한다.

## 5. 검증·게시·삭제

청크/Graph/원문 근거/복합 scope/벡터/checkpoint를 전부 검증한 index만 게시한다. 현재 권한과 문서 미삭제를 잠금 안에서 재확인하고 publication pointer 변경·Job completed·감사 기록을 하나의 DB transaction으로 수행한다. 감사 실패는 전체 rollback한다. 새 index 실패 때 기존 게시 pointer를 유지한다.

삭제 요청은 먼저 현재 읽기·검색·게시 경계를 차단하고, cleanup Job이 해당 scope의 payload와 원문을 정리한다. cleanup에는 새 원문 SELECT·provider 호출·게시 권한을 주지 않는다. receipt/Job/call/usage/삭제 tombstone 등 복구·감사에 필요한 metadata는 보존한다. 현재 Grant와 출처 회수의 응답 처리는 C04에서 연결한다.

완료 기준: 게시 경쟁·삭제 경쟁·회수 직후 pointer 변경 차단, 기존 게시본 유지, cleanup 호출 0, 다른 scope 삭제 0, 원문 orphan 확인 후만 정리.

## 6. 시험과 결과 보고

폐기용 소유 DB에서 실제 role/FORCE RLS·복합 FK·동시 접수/claim/게시·재시작·잠금/감사/DB 실패를 검증한다. primary는 기존 행·사용·예약·키 해시를 비교하고 검증된 새 migration만 적용한다. 기존 보호 파일·이전 증거·원본 GraphRAG·관련 없는 미추적 파일을 보존한다. 공개 증거에는 원문·private 제목·label/quote·key/DSN을 넣지 않는다.

관련 시험 후 변경 영향에 맞는 전체 backend 회귀를 수행한다. C03에 새 화면이 없으면 frontend 시험은 영향이 있을 때 수행한다. native API 확인은 개수만으로 기능 완료를 주장하지 않고 권한·실패·재시작 계약을 검증한다. 모의 인덱스와 실제 임베딩 인덱스를 분리하며 Q20는 검색을 실행하기 전까지 not_run이다.

산출물: `250.구현/14 문서 등록과 인덱싱 Job 구현 결과.md`, `260.테스트/evidence/C-rag/C03-*.json`, 대장/WBS 및 다음 C04 상세 계획. 각 구현 단계는 현재 채팅에서 순차 진행한다.

- [x] 입력/권한·추가 migration
- [x] 등록 receipt/원문 보상/API
- [x] Job lease/epoch/현재 권한
- [x] 중앙 임베딩/비용/checkpoint
- [x] 검증·게시/삭제 cleanup
- [x] 회귀·보존 증거/다음 C04 계획

## 실행 계약 보완

현재 채팅에서 순차 실행한다. multipart는 파일1개+metadata JSON1개만 허용하고 실제 request stream을 제한한다. 공통 코어 입력에는 평가 manifest를 사용하지 않는다. 실제 유료 임베딩은 수행하지 않고 mock/고정 가짜전송으로 중앙 원장·Job 재시작을 우선 검증한다.

완료 결과: [[14 문서 등록과 인덱싱 Job 구현 결과]]. 실제 유료 발사0이며 C04 검색/RAG 상세 계획은 [[15 ACL 검색과 RAG 답변 상세 작업 계획]]이다.
