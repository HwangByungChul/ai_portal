---
title: ACL 검색과 RAG 답변 상세 작업 계획
created: 2026-10-05
updated: 2026-10-06
status: completed
stage: 250.구현
tags: [implementation-plan, C04, rag, acl, evidence]
---

# I250-C04 ACL 검색과 RAG 답변

C03에서 게시한 저장소를 사용해 현재 권한이 허용한 자료만 검색하고, 관계별 원문 근거가 검증된 RAG 답변을 저장·조회한다. 화면 연결은 C05, 합성7버전/Q20의 전체 평가와 통합 인계는 C06이다. 실제 실행 결과는 [[16 ACL 검색과 RAG 답변 구현 결과]]에 기록했다.

참조: [[09 문서와 GraphRAG 연결 상세 작업 계획]], [[14 문서 등록과 인덱싱 Job 구현 결과]], [[../240.설계/06 문서와 GraphRAG 설계]], [[../240.설계/05 AI 호출과 사용량 원장 설계]], [[../240.설계/04 API와 실행 상태 설계]], [[../240.설계/08 검증과 재현 설계]].

## 범위와 예상 시간

기존 C20시간 중 C04 예상4시간: 읽기/공유 계약35분 → 중앙 질의 임베딩·권한 검색45분 → 관계 근거·문맥 조립40분 → typed RAG/저장·본문 보호45분 → 출처·공유API/경계 시험40분 → 회귀·C05 인계35분. 개인 실제 학습·개발 시간은 미측정이며 10월24일 파일럿·28일 기능동결·31일 종료 목표와 주20시간 이상/80h(여유10h 포함) 기준을 유지한다.

먼저 mock/고정 가짜전송으로 전체 계약을 검증한다. 실제 호출은 별도 사전 토큰/예약 계획과 기존 대표500원 잔여 범위의 승인 조건을 확인한 뒤에만 수행한다. 기발생 사용량·예약·키·기본 mock/RAG 중지 상태를 임의 초기화하거나 한도를 증액하지 않는다.

## 1. 읽기와 버전 공유

예정 파일: `app/documents/`의 목록·Grant 서비스/라우트, 새 migration014 이후의 고정 공유·읽기 제어, 관련 pytest. 기존000~013 SQL은 수정하지 않는다.

서버 AuthContext와 현재 membership/ACL/publication/Grant로 `(owner tenant, document, version, published index)` 허용 집합을 만든다. 같은 문서의 버전을 섞지 않는다. 명시 document_refs는 최대5개이며 무권한·삭제·미공유 버전은 질의 임베딩 전에404로 거부한다. 생략하면 허용 집합 안에서만 검색한다. 공유 B v1만 허용될 때 미공유 v2의 존재·제목·담당·기한을 반환하지 않는다.

API-17 사용자 문서 목록, API-28 수신 후보, API-29/30 exact-version Grant 목록/발급, API-31 회수를 구현한다. org 소유조직 관리자만 발급·회수할 수 있고 private 재공유를 거부한다. CAS·같은 활성 Grant 중복·현재 권한 잠금 재검사·감사 rollback을 확인한다. 실제 route 수는 C03의34에서7개 추가한41 계약으로 대조한다.

완료 기준: owner/private reader와 관리 권한 구분·v1/v2 선택·수신B 헤더 유지·다른 조직/관리권한의 우회0, Grant 회수 즉시 차단.

## 2. 중앙 질의 임베딩과 검색

예정 파일: `app/ai/` 중앙 `embed_query`·`generate_rag` operation, `app/documents/search.py` 등 scoped 저장소 adapter, `app/execution/`의 rules_rag 실행 계약. run/conversation/메시지 부모·Agent binding·sealed provenance 모델의 기존 일반 전용 제약은 새 migration으로 확장한다. 일반 대화와 원장을 보존한다.

원문 색인·질의 임베딩은 같은 model/dimension/mode/pipeline을 사용한다. query 입력은 승인된 오프라인 tokenizer로4000토큰 이내를 검사하며 원문 정답/질문별 required·forbidden·R/EV 파일을 runtime에 읽지 않는다. 중앙 permit/reserve/dispatch/settle을 통과한 질의 벡터로만 pgvector cosine 검색을 수행한다. unknown 자동 재발사0·같은 전송ID 접수1·known checkpoint 재사용을 유지한다.

후보와 Graph 확장은 처음부터 허용 version/index 집합 안에서 수행한다. 권한 없는 후보를 먼저 가져와 응답 직전에 숨기는 방식에 의존하지 않는다. web FORCE RLS를 유지하고 최종 행을 현재 ACL로 재검사한다. 후보 수·검색 깊이·문맥은 승인 설계 상한 안에 둔다. source/index/mode mismatch·DB 오류는 실패, 허용 근거 부족은 insufficient_evidence로 구분한다.

완료 기준: raw role/FORCE RLS에서 A/B·private·공유v1만 후보 허용, metadata/본문 우회0, mock와 실제 벡터 결과 구분, DB 실패를 근거 부족으로 처리하지 않음.

## 3. 관계 근거와 문맥

예정 파일: `src/common_core/ai_pipeline/graphrag/`의 현재 허용 결과 기반 문맥 조립/출처 검증, backend 검색 adapter와 pytest.

관계별 정확한 근거만 사용하고 방향·조건·상대 기한·버전을 유지한다. 원문 bytes SHA·Unicode offset/행·exact quote·FK/scope·pipeline을 다시 대조한다. 값 충돌·불명 예외·미지원·잘린 문장에 관계를 만들어 넣지 않는다. Graph에 없는 사실을 추가 추정하지 않는다.

문맥은2000토큰 이내, RAG base는4000, 최종 직렬화는6000 이내로 검사한다. 완전한 근거 단위만 선택하며 quote를 잘라 원래 주장의 증거라고 표현하지 않는다. 제목/인용/본문은 모두 현재 권한을 통과해야 한다. 출처 ordinal은0~19 범위에서 서버가 정하며 원문 평가 EV ID나 임의 provider URL을 사용하지 않는다.

완료 기준: 다른 관계의 유효한 quote 연결 거부·공유/개인 자료 혼합 거부·조건과 기한 보존·현재 허용 문맥만 모델 입력.

## 4. typed RAG·저장·과거 답변 보호

승인 설계06의 fixed rules_rag Agent는 중앙 `generate_rag` 경로로 answer_kind/selected_fact_ids의 제한 구조를 반환한다. 모델은 허용 fact ID를 선택하고 서버가 같은 관계와 근거 packet에서 사실 행·인용 ordinal을 렌더링한다. 자유 text/citation 계약은 사용하지 않는다. 모델 결과의 ordinal·quote·source binding을 서버에서 검증하고, 원문에 없는 근거나 허용되지 않은 인용은 게시하지 않는다. insufficient_evidence를 근거 부족으로 구분하고 provider/DB/usage 실패는 failed 상태로 남긴다.

검증되지 않은 RAG 자유 생성 draft는 SSE에 전송하지 않는다. 최종 본문·answer_evidence·sealed provenance·run completed를 원자 저장한 뒤 저장 정본을 공개한다. 일반 대화의 기존 streaming 계약은 유지한다. 재시작/응답 유실 후 GET으로 완료·권한을 확인하며 자동 재발사하지 않는다.

과거 답변의 본문·인용·다운로드에도 모든 출처의 현재 gate를 적용한다. Grant 회수·삭제·private ACL/조직·소속 회수 후 기존 본문에 기밀이 남지 않도록 현재 설계의 unavailable/본문 차단 규칙을 구현한다. 실패 시 민감한 제목·quote·owner metadata를 오류 메시지나 로그에 넣지 않는다.

완료 기준: 잘못된 typed 인용 공개0·저장 실패 완료표시0·sealed 전에 본문/SSE0·회수 후 과거 본문/인용/다운로드 우회0.

## 5. 출처 API와 검증

API-15 본인 run 근거 목록, API-16 exact-version 원문 다운로드를 구현한다. source tenant/version/index는 저장된 evidence FK에서 얻으며 요청자가 고를 수 없다. 수신B 헤더와 본인 run 권한을 유지한다. 파일/DB 처리 순서를 구분하고 현재 ACL/원문 SHA를 다운로드 직전 재확인한다. 정적 source URL·서버 경로·개인본문 로그는 제공하지 않는다.

폐기용 DB에서 실제 grants/FORCE RLS·복합 scope·동시 발급/회수/삭제·상태/예산·재시작/장애·typed quote 변조를 시험한다. SQL 적용 전 기존 행/모드/예산/키와 역사 증거를 보존하고, 모델이 모의이면 품질·실모델 완료로 표시하지 않는다. Q20는 실제 질문별 실행·별도 결과 기록 전까지 not_run이다.

## 6. 산출물과 인계

산출물은 `250.구현/16 ACL 검색과 RAG 답변 구현 결과.md`, `260.테스트/evidence/C-rag/C04-*.json`, 대장/WBS, 다음 C05 문서/Job/Grant/사용자 출처 화면 상세 계획이다. 변경 영향에 맞는 backend 회귀·기존 일반 화면 검증을 완료하고 정확 변경 파일만 로컬 Git에 기록한다.

- [x] 현재 허용 버전 집합/문서 목록/Grant
- [x] 중앙 embed_query/권한 검색
- [x] 관계별 근거·제한 문맥/typed 검증
- [x] RAG 저장·sealed provenance/현재 all-source gate
- [x] 출처 다운로드/동시성·회수·재시작/회귀
- [x] 결과/WBS·C05 상세 계획

최종 검증은 C04 결과/증거 기준이다. 모든 동시 삭제 경합을 망라한 시험을 주장하지 않는다. 다음 C05 화면은 미착수다.
