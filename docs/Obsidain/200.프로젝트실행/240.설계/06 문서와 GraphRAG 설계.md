---
title: 문서와 GraphRAG 설계
created: 2026-10-04
updated: 2026-10-04
status: approved
stage: 240.설계
task: D240-05
user_review: approved
tags: [ai-platform, design, graphrag, documents, evidence, multi-tenant]
---

# 문서와 GraphRAG 설계

> **현재 기준 — 2026-10-04 종합 승인:** 사용자가 종합 설계 보고 후 “네 진행 바랍니다”로 후속 진행을 지시하여 이 설계를 확정했다. [[200.프로젝트실행/250.구현/01 인증과 테넌트 기반 구현 계획]]으로 전달한다. 아래 각 D240 작업 당시의 검토 대기/미수행 서술은 작성 이력이다. 현재250의A01환경·health/DB도구는구현·시험완료다. 인증·테넌트업무DB/RLS·화면/AI·전체시험은미수행이며250 결과문서를따른다.

## 1. 결론·상태·입력

문서 버전별로 원문·청크·실제 임베딩·개체·관계·근거를 만들고 검증한 색인만 공개한다. 검색은 현재 권한과 허용 버전을 먼저 결정한 뒤 벡터/Graph/원문 전체에 같은 범위를 적용한다. 관계별 근거를 정확히 연결하며, 공유 회수 후 과거 답변과 다음 대화의 이력까지 현재 권한으로 검사한다.

D240-05 문서 작성/자체 점검 완료. 사용자 “네 진행 바랍니다”로 D240-04에 이은 순차 설계를 진행했다. 240 종합 승인 전 설계안이며 앱 코드·DB/계정/키 설정·색인/모의/실제 검색·유료 호출·Q20 실행은 없다. 원본 GraphRAG와 합성 자료는 수정하지 않는다.

입력: [[200.프로젝트실행/240.설계/02 인증과 테넌트 권한 설계]], [[200.프로젝트실행/240.설계/03 데이터 모델과 RLS 설계]], [[200.프로젝트실행/240.설계/04 API와 실행 상태 설계]], [[200.프로젝트실행/240.설계/05 AI 호출과 사용량 원장 설계]], [[200.프로젝트실행/230.분석/03 GraphRAG와 백엔드 재사용 분석]], [[200.프로젝트실행/230.분석/04 화면과 업무 연결 분석]], [[200.프로젝트실행/230.분석/05 합성 데이터와 평가 기준]]. 관련 요구21개는14절에 연결한다.

| 접근 | 판단 | 이번 선택 |
|---|---|---|
| 벡터 검색만 사용 | 단일 구절에는 단순하나 관계 방향/책임별 근거를 별도로 검증해야 함 | Graph 결합의 한 입력 |
| 원문 규칙 추출 + 권한 내 벡터/Graph 결합 | 추가 LLM 추출 비용 없이 명시적 관계와 근거 검증 가능. 문장 형식의 한계 있음 | **개인 MVP 설계안** |
| 범용 LLM 추출/커뮤니티 요약/글로벌 탐색 | 새 비용/스키마/검증 범위가 필요 | 이번 범위에 추가하지 않음 |

기존 common_core의 파서/추출/검색 경계를 새 repository·verified context에 연결한다. bare chunks/sources와 graphrag_*를 동시에 쓰지 않고03의 rag 모델로 통일한다. 기존 mock 관계/완료 표시와 미구현 pgvector 어댑터는 실제 산출물 검증 없이 재사용 완료로 보지 않는다. Microsoft GraphRAG 문서는 Graph+원문 문맥 결합 원리의 참고이며 그 패키지의 전체 인덱서/커뮤니티 모델을 도입했다는 뜻이 아니다.

## 2. 등록·원문·버전·중복

관리 API-22/23은 현재 관리 조직에서 TXT/Markdown1파일, UTF-8, 최대128KiB/40000자·title200자·전체160KiB를 검사한다. private 등록의 owner/reader는02의 같은 조직 허용자이며 관리자가 자신을 임의 reader로 추가하지 못한다. 기존 private 새 버전은 본문 ACL도 필요하다. 공유 수신 조직은 새 버전/재처리/삭제/재공유를 하지 못한다.

원문 frontmatter의 tenant/owner/scope/version은 **권한 입력이 아니다**. 서버의 검증된 등록 metadata와 계정/조직만 권한 정본이다. 합성 초기화 로더는 manifest의 액터/권한 선언을 운영 ID로 변환하는 별도08 계획을 거친다. runtime 인덱서는 manifest의 정답 entities/relations/evidence 및 questions.json을 읽지 않는다.

원본 바이트 SHA-256과 불변 source object를 저장한다. 파일명/경로는 서버 UUID로 생성하고 업로드 경로를 사용하지 않는다. 외부 링크 fetch·첨부 실행·HTML script 실행·YAML 객체 생성은 하지 않는다. 원문은 plain text 다운로드/안전한 텍스트 표시로만 제공한다. UTF-8 오류/NUL/빈 본문/크기 오류는 provider0이다.

임시 비공개 파일→검사→03의 원자 rename→문서/버전/index/Job/접수 receipt transaction commit 순서다. 파일/DB는 하나의 transaction이 아니므로 중간 장애는 비공개 orphan으로 남겨 정리하고 공개하지 않는다. commit 응답 불명은 같은 client_upload_id로 접수 정본을 조회한다. 등록202는 queued 접수이며 색인 완료가 아니다.

| 입력 상황 | ID/비용 처리 |
|---|---|
| 같은 operation ID·같은 request hash | 같은 receipt/document/version/index/Job 반환, 새 등록/발사 없음 |
| 같은 operation ID·다른 payload |409 충돌, 기존 자료 불변 |
| 새 문서 등록·새 upload ID | 별도 document_id. 다른 문서/owner/조직에 같은 바이트가 있어도 전역 hash 중복검색/병합 없음 |
| 같은 기존 문서의 새 버전 요청, 최신 등록 버전의 내용·title·불변 metadata가 같음 | 현재 권한/expected_revision 검사 후 그 버전/index/활동 또는 완료 Job 재사용, 새 자기 receipt 연결 |
| 최신 등록 버전과 다름 또는 title 변경 | 새 version_id/version_no. 과거 버전과 같은 바이트라도 과거 버전으로 조용히 되돌리지 않음 |
| 같은 version+pipeline fingerprint에 활동 Job 존재 | 기존 Job 반환. 같은 index 활동 Job 최대1개 |
| 같은 version+pipeline의 공개 완료 index | reused=true, provider0. 현재 공개/권한을 확인하며 completed 이력을 위조하지 않음 |

내용 동일성은 server HMAC ingest fingerprint(tenant/doc/원문 SHA/title·불변 metadata)를 보호 버전에 저장하고 **동일 문서 안에서만** 최소 함수로 비교한다. 함수는 현재 등록/버전 관리 권한을 검사하고 opaque 결과 ID만 반환한다. private 본문/title/raw SHA를 읽어 관리자에게 보여주는 우회가 아니다. 접수 receipt에는04대로 request_hash/불투명 참조만 남긴다. document/version 식별이 없는 최초 등록에서 비밀 문서의 존재를 hash 조회로 드러내지 않는다.

pipeline_fingerprint는 parser/chunker/tokenizer/정규화·추출 규칙/별칭/schema revision·embedding model/dimension·mode를 포함한다. Agent 이름/안내 지침 변경만으로 재임베딩하지 않는다. real/mock index는 섞어 재사용하지 않는다. metadata와 상태 변경은 revision으로 경합을 검사한다.

## 3. 파싱·청킹·근거 위치

| 항목 | 규칙 |
|---|---|
| 파싱 | 원본 바이트/행 보존, 파생 텍스트는 BOM 처리·CRLF→LF와 제한 Markdown 문법 제거. 변환마다 원본 위치 mapping 유지 |
| 제외 | 시작 frontmatter·합성 고지·HTML anchor·EV marker ID는 업무 사실/embedding 입력에서 제외. heading의 실제 문구는 유지 |
| 단위 | heading 아래 문단/문장, 가능한 문장 경계에서512토큰 이하 청크로 묶음. 첫 MVP overlap0 |
| 긴 문장 | Unicode 문자 경계에서 토큰 상한 안으로 분할하고 원문 offset 재검사.512를 넘는 단일 문장 관계는 잘린 문장에서 확정하지 않음 |
| 총 상한 | 버전당128청크/512개 근거/512개 개체/1024개 관계/2048개 관계-근거 연결. 초과는 INDEX_LIMIT_EXCEEDED, 자동 잘라 완료 처리 없음 |
| 임베딩 |05의512토큰/청크,8청크·4096토큰/요청, 차원1536. 한 버전 최대16배치. 작업 전체300초 이내 완료 보장은 아님 |
| 근거 | 의미 있는 원문 문장/연속 구절의 exact_quote + byte SHA + line_start/end + Unicode codepoint start/end + chunk/index/version 복합 참조 |

원문 exact_quote는 원본의 실제 연속 구간이어야 한다. heading/여러 문장을 합쳐 만든 문장은 quote로 저장하지 않는다. 정규화 label과 원문 quote를 분리한다. Markdown heading/marker를 제거하더라도 원본 행/offset은 사라지지 않는다. 긴 문장 조각에는 위치 근거를 만들 수 있지만 관계 확정은 완전한 주장과 한 근거 구간을 확인한 경우만 한다.

EV18은 평가자가 선언한 원문 구간이며 runtime evidence_id/chunk_id가 아니다. runtime ID는 서버 UUID/결정적 local ordinal로 생성한다. 평가자는 source SHA+문서/버전+원문 구간/quote를 대조해 EV와 runtime 근거를 매핑한다. EV marker나 금지/정답 목록을 모델 문맥에 포함하지 않는다. 원문에서 추출한 데이터가 정답 R16과 일치하는지는 실제 색인 후 시험으로 판정한다.

토큰 검사/전체 산출물 크기 계획은 유료 임베딩 전에 완료한다. source→chunk/evidence/Graph 계획이 유효할 때 실제 임베딩을 시작한다. 관계0개인 문서도 실제 청크/벡터/근거가 유효하면 색인할 수 있으나 Graph coverage를 partial로 명시한다. 모든 문서를 Graph 완성으로 표시하지 않는다.

## 4. Job·색인·복구·공개

| stage | 산출물·지속 경계 | 실패/권한 변경 |
|---|---|---|
| validate_source | 현재 위임/원문 SHA/metadata/규모 확인 | queued→running claim/lease 필요, 실패는failed 또는blocked |
| parse_plan | 위치 mapping/청크/근거/규칙 Graph/배치 fingerprint 확정 | 계획 검증 후 staging 저장. provider0 |
| embed_batches | batch별 central embed_document + usage 기록 + 정상 벡터/checkpoint commit | 매 배치 전 현재 initiator/문서/Agent·lease/한도 검사. 불명은needs_review |
| validate_index | 청크 수/벡터1536·유한/동일 mode·source/hash/관계별근거/외래키/완료배치 검사 | 미완성/틀린근거는 공개 금지, validated는 사용자 공개 아님 |
| publish | 현재 관리 권한/Agent enable·문서 삭제/버전/epoch 재검사, pointer+Job completed commit |03 잠금/CAS. 삭제/회수/권한 상실/설정 변경이면blocked, 가짜completed 없음 |

batch checkpoint는 index의 예상 batch ordinal/input fingerprint, 해당 Job/call 참조, 벡터 저장 확인, usage 확인, source/pipeline/mode를 기록한다. 각 chunk에 batch ordinal/call 참조를 두고 index에 완료배치 요약을 둔다. 기존31개 모델의 필드 보완이며 별도 저장 서비스/새 테이블을 만들지 않는다. 벡터와 checkpoint는 같은 transaction으로 저장한다. meter 정산은 별도이며 둘을 하나의 외부/DB atomic 호출로 주장하지 않는다.

재처리는 이전 terminal Job을 고치지 않고04의 retry Job을 생성한다. 새로운 lease/현재 권한으로 source/계획을 확인한 뒤, **동일 index·source/pipeline/mode + 정상 벡터 전부 지속 저장 + 기존 call 확정 정산**인 배치만 재사용한다. usage가 settled여도 벡터가 유실됐으면 새 호출 비용이 필요하다. 값이 메모리에 있다는 이유로 재사용 완료를 만들지 않는다.

partial/미확인 벡터를 성공 배치로 세지 않는다. needs_review는05의 실제 결과/정산 증거 대조 전 재처리 불가다. 알려진 기존 비용을0으로 되돌리지 않으며 timeout/재시작에 자동 provider 재발사하지 않는다. 개별 저장 작업의 안전 재시도는04/05대로 최대1회다. 전체300초 deadline에 도달하면 더 발사하지 않고, 미확인 call 여부에 따라 interrupted/needs_review로 남긴다.

동일 fingerprint index는 고유 키로 하나이며 활동 Job도 하나다. 실패 index의 정상 checkpoint를 살린 새 Job은 같은 index를 재개할 수 있으나 이미 공개된 index의 payload는 수정하지 않는다. pipeline이 달라지면 새 staging index를 만든다. 기존 publication pointer는 새 index가 검증/공개 commit될 때까지 유지한다. 완료 index가 현재 gate에 공개돼 있지 않으면 단순 reused completed로 응답하지 않고 현재 권한의 검증/공개 작업으로 판정한다.

Job은 HTTP logout과 독립적이며 현재 initiator의 계정/소속/작업 권한과 lease를 다시 확인한다. 사람에게 본문 읽기 권한이 없는 private 등록관리자의 Job도02의 **특정 버전 internal_index 위임**으로만 처리한다. 관리 API로 본문/청크를 반환하지 않는다. 오래된 worker의 epoch는 콘텐츠 저장/공개를 차단하되 기존 call의 정산/최소 실패 기록은05의 한정 예외로 남긴다.

## 5. 규정 스키마·별칭·방향·추출 규칙

개체 유형은 PROCESS/TEAM/ARTIFACT/DURATION/SCHEDULE/PERSON이다. 실제 개체 인스턴스는 tenant+index+entity_id로 분리한다. label은 원문에서 캡처하고 비교용 canonical label만 NFC/공백을 정규화한다. semantic_key는 원 소유tenant+유형+canonical label의 안정적인 키다. 필요하면 digest로 표현하되 조직 간 같은 이름을 같은 키로 합치지 않는다.

업무 별칭은 가상 여신심사↔여신심사, 가상 AI 지원 요청↔AI 지원 요청/지원 절차를 연결한다. 이 작은 도메인에서는 원문 “가상 AI 서비스”의 복구 목표를 같은 지원 업무에 연결하는 **명시적 도메인 규칙**을 둔다. 원문이 일반적으로 같은 업무를 의미한다고 추정하는 범용 규칙은 아니다. 팀/기간 값과 정답 relation/EV는 별칭 사전에 넣지 않는다. 예컨대 지원데스크와 플랫폼지원팀은 서로 다른 TEAM이며 같은 alias로 합치지 않는다.

PERSON label(A-U1 등)은 원문 사실이며 계정 권한 ID가 아니다. owner/reader의 보안 UUID는 등록 metadata에서만 얻는다. 시간은 숫자뿐 아니라 단위/상대 시작점/이내/매월 표현을 보존한다.2영업일을48시간으로 바꾸거나 현재 달력의 확정 일자로 계산하지 않는다.

| 규칙 ID | 원문 문형/관계 | 방향·추출 |
|---|---|---|
| GR-01 | “업무의 담당 부서는 팀이다” | PROCESS → TEAM, 담당부서 |
| GR-02 | “업무의 위험 검토 승인 부서는 팀이다” | PROCESS → TEAM, 위험검토승인부서 |
| GR-03 | “업무의 기록 보관 담당 부서는 팀이다” | PROCESS → TEAM, 기록보관담당부서 |
| GR-04 | “업무의 기록 보관 기간은 기간이다” | PROCESS → DURATION, 기록보관기간 |
| GR-05 | “업무는 … 점검표를 작성한다” | PROCESS → ARTIFACT, 필수점검표, 원문 조건/시점 보존 |
| GR-06 | “팀은 업무 기록의 누락 여부를 일정에 점검한다” | TEAM → SCHEDULE, 누락점검일; 업무 연결은 같은 문서의 명시적 보관 책임 근거로 확인 |
| GR-07 | “인물의 개인 시연 리허설은 일정에 진행한다” | PERSON → SCHEDULE, 개인리허설일정 |
| GR-08 | “지원 요청의 접수 담당은 팀이다” | PROCESS → TEAM, 접수담당 |
| GR-09 | “팀은 요청 접수 후 기간 이내에 접수 확인을 통보한다” | TEAM → DURATION, 접수확인기한; relative_trigger/qualifier 보존 |
| GR-10 | “서비스의 복구 목표는 기간이다” | 도메인 alias PROCESS → DURATION, 복구목표 |

긴/구체적 문형을 먼저 검사해 기록보관/위험검토 부서를 일반 담당부서로 잘못 분류하지 않는다. 문장별 한정된 긍정 선언을 whole-span으로 확인한다. 부정/예외/조건 불명/양립하지 않는 복수 값/대명사 주체 불명에는 관계를 추정하지 않는다. 미지원 문장은 원문 근거/벡터로 남기고 coverage partial이다. 개인 준비 항목처럼 관계 스키마 밖 문장은 원문 구절로만 제시할 수 있다.

모든 relation은 같은 index의 양 끝 개체와 정확한 evidence를 FK로 참조한다. dedup은 index+from+predicate+to+조건/원문 구간을 기준으로 하고 서로 다른 근거가 있으면 relation_evidence에 해당 근거만 추가한다. 같은 업무의 모든 evidence를 관계마다 붙이지 않는다. D-A-R1 승인과 D-A-R2 보관 관계는 다른 원문/색인 출처를 유지한다.

## 6. 버전 선택·공유·공개 범위

| 접근 | 사용할 버전/색인 |
|---|---|
| 소유 조직 organization | 현재 활성 membership + active publication에서 가장 높은 공개 version_no. 등록만 된 실패/진행 최신버전은 제외 |
| 같은 조직 private | owner/명시 reader의 현재 ACL 안에서 동일 공개버전 선택. 관리 역할만으로 허용하지 않음 |
| 수신 조직 공유 | 그 조직의 현재 활성 exact-version Grant와 active publication의 교집합에서 가장 높은 **허용 버전**. 전체 최신 버전을 먼저 고르지 않음 |
| 사용자가 명시한 document/version | 먼저 ACL을 검사. 허용된 해당 버전만 선택. 무권한은404 RESOURCE_UNAVAILABLE, embed/generation0 |
| 과거 인용 link | 저장된 exact source version/index/hash/현재 publication pointer·Grant 검사. 현재 검색 버전으로 자동 치환하지 않음 |

A의 D-S v2가 공개되면 기본 검색은v2, B에v1만 Grant가 있으면 기본 검색은v1이다. B 목록에는 허용v1의 title/version만 보이며 미공유v2 존재/최신 여부/고유 담당/기한/복구 목표를 노출하지 않는다. 같은 제목이 있다는 이유로 허용v1 제목까지 숨기거나 누설로 판정하지 않는다.

새 버전/같은 버전 새 index가 실패하면 기존 유효 공개 pointer를 유지한다. version을 공개하는 것과 다른 조직에 공유하는 것은 별개다. 새 버전에 기존 Grant를 자동 승계하지 않는다. 이전 공개 버전은 active gate/권한이 유효하면 명시 조회·과거 인용에 사용할 수 있다. 같은 version의 index pointer가 교체되면 과거 index는03의 현재 공개 gate 밖이며 과거 답변은 재검증 필요로 처리한다. 다른 index로 근거 ID를 조용히 바꿔 역사 사실을 위조하지 않는다.

조회 함수는 row의 원 소유tenant와 현재 선택tenant를 구분한다. B 공유조회는 X-Tenant-ID=B를 유지하며 A 행은 명시적인 Grant 읽기 예외로만 통과한다. 받은 자료를 B 소유로 복제/전역 cache하지 않는다. source ID만 알거나 기존 FK가 있다는 사실은 현재 읽기 권한을 주지 않는다.

## 7. 검색·Graph 조립·답변 문맥

| 순서 | 현재 범위·출력 |
|---|---|
| R-01 요청 대상 검사 | 현재 run/session/tenant·Agent·명시 doc refs 최대5개를 검사. 무권한 대상은 모든 유료 호출 전404 |
| R-02 허용 버전 집합 |6절의 owner/private/Grant·published pointer·mode로 allowed `(source_tenant,doc,version,index)` 집합 확정. 집합이 비면 일반 근거 부족, 보호 자료 존재는 언급하지 않음 |
| R-03 질의 임베딩 |05 중앙 embed_query1회. 허용 범위/현재 중지를 다시 검사. 비용은 실행tenant |
| R-04 후보/seed | 허용집합만 대상으로 exact cosine 최근접 청크 상위6개, 질문 업무/인물/역할 표현과 일치하는 허용 개체seed 최대4개 |
| R-05 Graph 확장 | 현재 허용 인스턴스에서 방향별 최대2hop, 관계후보 최대32개. 같은 semantic_key의 허용 문서들을 연결하되 출처별 실제 관계/근거는 유지 |
| R-06 근거 조립 | 관계별 relation_evidence join·원문 hash/구간 검증, 중복quote 제거. 후보사실 최대20개·근거 최대20개·모델 문맥2000토큰 이내 |
| R-07 충분성/생성 | 질문의 필요한 역할/속성별 근거가 있는지 검사. 부족/모호하면 로컬 hold. 충분하면05 중앙 generate_rag1회에 허용 fact packet만 전달 |
| R-08 검증/저장/공개 |8절 출력검증, 모든 source ACL 재검사, 본인run/message/answer_evidence+completed 같은 commit, 그 후04 terminal |

소규모 corpus는 pgvector의 exact 검색을 사용하고 HNSW/IVFFlat을 도입하지 않는다. cosine distance와 exact 기본 동작은 [pgvector 공식 문서](https://github.com/pgvector/pgvector)를 확인했다. 유사도 임계값을 품질 합격 기준으로 임의 확정하지 않는다. 벡터 순위는 후보 확보이고 답변 충분성은 명시 근거/관계로 판단한다.

RLS/서비스 ACL을 적용한 허용집합 안에서 정렬/seed를 구한다. 전체 조직 결과를 먼저 top-k로 얻어 사용자별 후처리만 하는 설계가 아니다. 제목/label/property/degree/count/관계 endpoint/quote/path/다운로드까지 동일 출처 guard를 적용한다. 근거가 RLS에 가려졌다고 관계/endpoint만 반환하지 않는다. 관계32개 상한에 도달해 필요한 경로를 끝까지 확인하지 못하면 **검색 범위 제한으로 답 확정 불가**로 표시하며 불완전 경로를 확정하지 않는다.

seed alias/질문 속성 분석은 로컬 도메인 규칙이다. 예컨대 위험 검토 승인과 기록 보관 담당을 각각 다른 predicate로 요청하고, 지원 접수 담당→확인 기한은2hop으로 확인한다. 긴 역할 표현부터 매칭하며 “담당”이라는 공통어 하나로 모든 책임을 바꾸지 않는다. 문서 간 연결은 원 소유namespace/semantic_key와 현재 허용 index 집합이 같아야 한다. B의 동일 업무 이름과 A의 private label을 그래프 하나로 합치지 않는다.

여러 요구 속성 중 하나라도 자료가 없거나 현재 허용 출처에 같은 속성의 모순 값이 있으면 전체 답변을 hold하고 필요한 범위를 설명한다. 임의 최신 문서/유사도1위를 정답으로 고르지 않는다. 명시 doc/version 선택으로 범위를 좁혀 다시 질문할 수 있다. 금리/결재 금액 상한/파기 승인자는 이번 규칙/허용 원문으로 답을 증명할 수 없으며 근거 부족이다. B의 복구 목표 질문도v1에 근거가 없으므로 hold다. 미공유v2를 찾아 채우지 않는다.

정상 부족은04의 completed+insufficient_evidence이며 신규 generate_rag0, 이미 수행한 embed_query 비용은 남긴다. DB/검색 오류는 failed+SEARCH_FAILED, 실행 거부는 blocked/안전 오류, 명시 무권한은404로 구분한다. 미지원 질문은 “이 MVP의 허용 자료에서 답을 확인할 수 없습니다”로 제한하며 일반 Agent로 자동 전환하지 않는다.

fact packet은 서버 local fact ID·관계 종류/양끝값·조건·정확한 구절·허용 출처 표시만 포함한다. 내부 파일path·권한 사유·다른 조직 자료/정답/Q-ID/forbidden 목록·전역Graph 통계는 전달하지 않는다. 원문 지시문은 데이터이며 시스템 지침/tenant/도구 허가를 바꾸지 못한다.05 dispatch 직전에 문맥의 모든 source를 다시 검사한다. source 변경/회수/중지는 새 문맥으로 몰래 재호출하지 않고 현재 실행을 차단한다.

## 8. 답변·인용 검증과 스트림 보완

관계별 잘못된 인용을 줄이기 위해 이번 rules_rag의 최종 사실은 **서버가 만든 사실 packet**에 한정한다. 모델은 질문에 필요한 fact ID를 선택하고 순서를 제안하며, 값·부서·기간·근거번호를 자유롭게 새로 만들지 않는다. 일반 Agent의 자유 텍스트 생성은05대로 유지한다. 범용 규정 요약/임의 문장의 자동 이해까지 구현했다고 주장하지 않는다.

| provider 출력 계약 | 검증/렌더링 |
|---|---|
| answer_kind=answer 또는 insufficient_evidence |04의 업무 answer_kind로 변환. provider refusal/실패와 구분 |
| selected_fact_ids 배열, 최대20개·중복 없음 | 모두 이번 run의 허용 packet ID여야 함. 모델이 만든 doc/version/관계/근거/URL/자유 본문은 수락하지 않음 |
| answer이면1개 이상·요구 역할/경로 충족 | 서버가 원문 추출 predicate/값/조건/관계별 근거를 사용해 한국어 사실 행과 인용번호를 생성 |
| insufficient_evidence이면 빈 배열 | 정제된 로컬 안내. 질문에 없거나 숨긴 자료 사실을 부연하지 않음 |

예: “위험 검토 승인 부서: 위험관리팀 [1]”의 값/역할/인용번호는 같은 relation+evidence packet에서 서버가 함께 만든다. 모델이 위험관리팀에 보관기간 근거를 붙이는 입력은 존재하지 않는다. 개인 준비 항목처럼 스키마 밖 구절은 질문 속성과 연결된 허용 exact_quote만 서버가 인용한다. 임의 요약 사실은 추가하지 않는다. packet 선별/관련성 자체는 실제 Q20/추출 검증 대상이며 schema 적합성만으로 사실/검색 품질 통과로 보지 않는다.

provider response_format=json_schema/strict의 논리 계약은 answer_kind enum·selected_fact_ids:string[]의 required2필드/additionalProperties=false다. 배열상한/중복/known-ID/질문 역할 충족은 서버가 추가 검증한다. 지원 모델/설치SDK의 실제 schema 호환은250 대표 시험에서 확인하며 실패하면 실제 RAG를 거부하고 자유 텍스트/가짜 응답으로 대체하지 않는다. [공식 Structured Outputs 안내](https://developers.openai.com/api/docs/guides/structured-outputs)를 참고했다.

**04/05 보완:** rules_rag의 provider JSON delta는 내부 버퍼에만 모으고 raw JSON/미검증 사실을 사용자에게 스트림하지 않는다. 최대64KiB/출력1024토큰/전체60초를 유지하며 초과/불완전 JSON/알 수 없는 fact ID/누락 역할은 `ANSWER_EVIDENCE_INVALID`로 최종 성공을 만들지 않는다. 정상 결과/usage/finish를 구분하고 이미 발생한 usage는05대로 기록한다.

사용자 SSE에는 검색/생성 상태와 검증된 사실 텍스트만 draft로 보낼 수 있다. fact 검증 후에도 매본문batch 현재 ACL을 검사하고 최종 DB commit 전에는 완료로 표시하지 않는다. 일반 Agent의 토큰 진행과 달리 RAG 본문은 검증 후 보이는 방식임을07 화면에 안내한다. EOF/JSON 완료/화면 글자 표시는 저장 완료가 아니다. 미완성 provider 응답을 “근거 부족 정상 완료”로 숨기지 않는다. 정상 finish 뒤 usage만 유실된 경우는05의 조건에 따라 completed+usage_unknown 가능하다.

사용자 근거번호는 answer_evidence ordinal0~19에 대응하며 화면은1부터 표시한다. 모델 fact ID/runtime relation ID와 다른 값이다. 각 인용은 exact doc/version/index/evidence/hash/location으로 저장한다. quoted text/title의 snapshot을 저장하더라도 현재 권한을 통과하지 않은 snapshot을 재표시하지 않는다. 원문 링크는 API-16의 본인run/ordinal 경유이며 정적 경로/파일 URL을 만들지 않는다.

## 9. 과거 답변·이력·DB 조회의 현재 권한

`render_current_answer(actor,selected_tenant,run)`을 API-09/12/15/16의 이력·결과·근거·원문 및 재연결/다음 이력 입력의 공통 서비스 경계로 둔다. 본인 대화/run·현재 세션/소속/Agent와 **저장된 RAG 답변의 모든 source provenance**를 검사한다.

| 현재 상황 | 표시·다음 모델 이력 |
|---|---|
| 모든 출처의 exact version/index/publication/ACL/hash 유효 | 저장 답변과 허용 근거 반환. 검색 기본버전이 이후v2가 돼도 허용 과거v1 인용을 자동 치환하지 않음 |
| 하나라도 Grant회수/삭제/reader회수/비공개index/해시 불일치/검사 실패 | **RAG assistant 본문 전체 숨김**,content_status=unavailable/result text=null 및 일반 안내. 안전한 state/time/own run ID 유지 |
| 근거 목록 일부 유효 | API-15는 유효 항목만 current title/quote 반환, 무효항목은 ordinal+unavailable만. 전체 답변을 일부삭제로 재조합하지 않음 |
| 해당 과거 turn이 차단됨 | 다음 생성 이력에서 assistant 본문/인용/snapshot과 짝을 이루는 turn을 제외. 모델에 raw 메시지 직접 전달 없음 |
| general 답변·사용자가 직접 입력한 질문 | 본인/현재 조직/세션 기준. 출처정보 없는 사용자의 복사본을 소급 회수할 수 있다고 주장하지 않음 |

완료된 run의 state=completed 이력 자체는 바꾸지 않는다. **실행 완료와 현재 본문 조회 가능**은 별개다. source 검사를 DB 장애로 못 하면 본문은 차단하고 정제된 서비스 오류를 반환한다. 원문/download는 해당 exact source 권한/파일hash 확인 후128KiB 이내 bytes를 읽어 반환한다. 파일이 사라지거나 hash가 다르면 보호 내용을 대체 반환하지 않는다. 읽기 승인과 권한 회수 순서는03의 짧은 authority 잠금/최신 statement로 결정한다.

RLS도 이에 맞게 보완한다.03 P-02의 “본인 메시지이면 본문 읽기”만으로 RAG 파생 본문을 읽을 수 있게 두지 않는다. RAG assistant payload SELECT는 **본인run + 모든 source의 현재 공개/ACL** 조건을 추가한다. 안전 상태 조회와 본문 조회를 분리하며, raw 메시지/snapshot/quote 열의 무조건 직접SELECT 경로를 허용하지 않는다.03의 DB-03 tenant WHERE 누락 SQL 시험과 함께 회수 후 자신의 저장답변 직접SQL도 시험한다.

필요한 제한 함수 `can_read_rag_answer_payload`는 portal.run의 소유/Agent 종류와 answer_evidence의 비콘텐츠 provenance ID만 읽을 권한을 최소 부여받고, security의 publication/access/Grant gate로 판정한다. policy executor에 메시지/문서/quote 본문 SELECT나 RLS 우회를 부여하지 않는다. run과 assistant 메시지의 Agent/source 분류는 서버 불변값과 FK로 연결해 message_kind를 general로 바꿔 우회하지 못한다. 원본 rawRLS policy가 이미 이런 조건을 구현했다고 표시하지 않는다. 세부 DDL/함수는250 계획,03과 최종 계약 통합은D240-08의 책임이다.

브라우저는 조직 전환/로그아웃/ACCESS_REVOKED를 받으면 draft·근거 패널·메모리 cache를 정리하고 서버 정본을 다시 조회한다. 완료 payload를 localStorage/service worker/offline cache에 저장하지 않는다. 이미 사용자에게 전달/복사된 정보 또는 OS/네트워크 버퍼를 소급 제거할 수 있다는 보장은 하지 않는다.

## 10. 삭제·공유 회수·파생 정리

| 작업 | 즉시 commit 경계 | 이후 정리 |
|---|---|---|
| 문서 삭제 API-24 | 현재 원 소유관리/expected_revision 확인. document_access tombstone·모든 해당 publication 차단·Grant 비활성·작업위임 회수/epoch fencing·최소감사 | 원본/청크/벡터/개체label·properties/관계properties/evidence quote와 파생 메시지 사본 정리. 비용/종결 이력 유지 |
| exact Grant 회수 API-31 | publication/Grant 잠금+revision으로 그 수신 조직의 버전 접근 차단 | 원 소유/다른 수신 조직이 쓰는 원문/색인은 유지. B 답변·이력은9절현재검사로차단 |
| private reader/소속 회수 | 현재 policy 정본/revision 변경 | 새 검색/근거/과거본문/다음이력 차단. 적법한 다른 reader/소유 자료 삭제하지 않음 |

삭제 응답은 access_state=deleted/cleanup_state=pending이다. 웹 관리 역할은03의 narrow 삭제 함수만 사용하고 타인 private 본문을 정리 목적으로 반환받지 않는다. source payload 정리는 index runtime의 **삭제된 특정 버전 cleanup 위임**과 최소 제어 함수로 수행한다. index runtime에도 전역 content SELECT/다른문서 DELETE/RLS bypass를 부여하지 않는다. job_authorizations의 action에 internal_cleanup을 구분하는 보완을 두고, 삭제 당시 허가된 target/삭제 revision/시스템 lease에 묶는다. 이 cleanup은 현재 사람의 본문권한을 새로 부여하지 않으며 이후 관리자가 로그아웃/권한 회수되어도 저장된 삭제 위임으로 정리만 계속할 수 있다. 위임은 삭제 대상으로만 purge write를 허용하고 처리/임베딩/재공개/본문 읽기는 허용하지 않는다. 실패 정리 단계는 safe error로 남겨 재시작에 재개하며 정리 완료를 위조하지 않는다.

published FK를 일괄 CASCADE로 파괴하지 않는다. document/version/index/chunk/entity/relation/evidence/answer_evidence의 **opaque 식별 tombstone/최소 provenance**는 남겨 감사/과거 참조를 유지한다. staging의 아직 생성되지 않은 vector와 삭제 후 payload는 NULL을 허용하되 공개 검증에서 완성 벡터를 강제한다. 내용 필드는 payload_purged/NULL과 소거 상태로 바꾸고 벡터/원본파일을 제거한다. source hash/원문 길이 등 보존이 필요한 내부 값은 계속 비공개다. 다른 문서에 같은 semantic_key가 있어도 그 문서의 관계/근거는 삭제하지 않는다.

portal의 삭제 문서 관련 저장 assistant 본문/인용 snapshot 사본도 즉시 숨긴 뒤 제한된 **파생 payload purge 함수**로 정리한다. meter/index 역할이 타인 대화 본문을 읽는 권한을 얻지 않으며 source provenance로 대상 run ID를 확인해 payload만 지운다. 여러 출처가 섞인 답변은 전체 assistant payload를 소거하고 다른 문서의 원본/색인은 유지한다. 사용자 자신의 질문은 별도 대화 자료이며 문서 삭제를 전체 질문 삭제로 확대하지 않는다. Grant 회수는 원 소유 파일 삭제를 유발하지 않고 접근만 차단한다.

삭제/회수와 진행 Job 공개는03의 authority/publication 잠금 순서를 공유한다. 삭제/회수가 먼저 commit되면 Job 공개 검사 거부. 공개가 먼저 commit돼도 뒤의 삭제/회수 이후 신규 읽기는 거부된다. 오래된 worker가 tombstone을 되돌리거나 Grant를 자동 만들지 못한다. 공유 신규 추가도 publication 잠금으로 부재행 경합을 직렬화한다.

## 11. 기존 GraphRAG 활용과 보완 전달

| 기존 책임 | 이번 재사용/보완 계약 |
|---|---|
| 파싱/청킹 경계 | UTF-8/명시적 범위·원문 mapping·512token/상한·검증 가능한 exact quote로 보완 |
| 도메인 추출/별칭 | 기존 sol_bat 규칙을 금융 규정 완성으로 보지 않고5절10문형/6개체 유형의 새 제한 schema로 구현 |
| Graph 검색 | 현재 허용seed·source별 개체 인스턴스·최대2hop·정확한relation_evidence join. 전체evidence 반환 제거 |
| PGVector adapter/repository | add/search/delete/get_chunks 미구현을03 복합키/RLS/현재publication에 맞게 실제 연결. health=false를 성공으로 바꾸지 않음 |
| ingestion/API | bare/graphrag_* 이중 저장/직접OpenAI/Graph mock completed를 제거하고2~4절 실제 Job·검증·중앙call로 연결 |
| 대화/근거 |9절의 현재 권한 renderer·RLS 파생본문 보호·원문API. 대화저장 실패 무시 제거 |

원본 파일을 복사/수정하거나 원본 SDK 키를 읽지 않았다. 실제 재사용 파일/설치 의존성·마이그레이션·실행/시험은 설계 승인 후 기능별250 계획에서 정한다. runtime SQL에서 분석 fixture의 R/EV ID를 그대로 Graph 테이블로 INSERT해 성공했다고 하지 않는다.

| 선행 명세의 보완 | D240-08 통합/250 입력 |
|---|---|
|03 버전/index/chunk/entity/evidence | ingest HMAC·parser 위치 mapping·batch/call/checkpoint·mode·coverage/산출물 수·payload_purged/tombstone 필드.31개 논리모델 안의 보완 |
|03 P-02/최소함수 | RAG assistant/snapshot 본문은 모든 source 현재허가 필요. 최소provenance SELECT·삭제대상cleanup/파생purge 함수 권한 명시 |
|04 상태/API | 재사용·publication/processing/cleanup 분리, typedRAG buffer→검증본문→저장완료, completed+content unavailable 가능 |
|05 centralAI | query/document embed와 generate_rag 그대로. 추가LLM 추출/자동재호출 없음. rules_rag response schema/fact packet 추가 |
|07 UI |RAG검증대기·hold/failed/deny·과거본문unavailable·권한내버전·private관리메타/실제Job진행·삭제cleanup표시 |
|08 검증 |실제원문→Graph/evidence/벡터·Q20별facts/provenance·회수이력/직접SQL·Job재공개·real/mock재사용거부 시험 |

## 12. Q20 대조와 핵심 경로

| 질문/시나리오 | 설계 기대값·증거 대조 |
|---|---|
| Q-001~006 | 현재 조직/본인/private/공유v1의 단일 사실. 원문 위치와EV의offline mapping으로 판정 |
| Q-007 | 담당/위험승인을 GR01/02로 구별. EV-A-R1-01/02 교차인용 실패 |
| Q-008 | 보관담당/기간을 GR03/04로 구별. EV-A-R2-01/02 역할과 각각 연결 |
| Q-009 | A의 허용된 두 문서 process semantic_key로 연결. 위험관리는R1-02, 기록보관은R2-01 근거 유지 |
| Q-010 | B namespace/허용index만. A의동명업무/팀을출력하지않음 |
| Q-011 | B에허용v1 PROCESS→접수팀→확인기간2hop, EV-S-v1-01/02 |
| Q-012 | A의현재공개v2 같은경로, EV-S-v2-01/02. 읽을수있는v1도현재질문답에혼입금지 |
| Q-013~015 | 금리/결재상한/파기승인자 원문근거부족, 로컬hold/허구값없음 |
| Q-016 | B허용v1 복구목표없음. 미공유v2의4시간/존재를노출하지않음 |
| Q-017/018/020 | 타조직/타인private/관리자private 직접refs는embed/generation전404,본문/title/근거없음 |
| Q-019 | BASE의v1 링크→Grant회수→동일link404/preview unavailable. 저장assistant전체/다음AI이력/직접SQL도차단 |

이 표는 **평가자용 설계 대조**다. 질문별 required/forbidden/정답EV/R을 실행 request/fact packet/추출 rule 입력으로 넣지 않는다. 실제추출 R/EV가 기대와 맞는지 아직 시험하지 않았다. schema 규칙이 있으므로Q20이 통과한다고 미리 판정하지 않는다. 원문 SHA/행/quote와BASE Grant 선언을 정적으로 확인했으며 execution.status=not_run을 유지한다.

## 13. 검증 입력 — 실제 시험 미수행

| ID | 입력·기대값 | 관련 요구/검증 |
|---|---|---|
| RG-01 |7원문 업로드/청킹/실제embed/추출/근거검증/공개 | 원문→실제산출물증거,등록≠완료·EV정답주입0; AP-004/005,CP-004,V-016/017/032/041 |
| RG-02 |같은upload ID충돌/새doc같은바이트/같은version재처리/동시Job |receipt/index/활동Job 중복없음·전역privatehash조회없음·재사용조건명확; AP-006,CP-006,NFR-004,V-018/032 |
| RG-03 |CRLF/BOM/heading·EV strip/Unicode긴문장/128청크초과 |exact quote/원문mapping·토큰상한·초과자동절단0·유료전검사; NFR-005/006,V-040/041 |
| RG-04 |승인/보관근거교차·타relation전체evidence·danglingFK |관계별구간/동일index검증거부·가짜완료0; CP-007,NFR-002,V-009/033,Q007~009 |
| RG-05 |같은업무 A/B/private seed·벡터·endpoint·Graph count·source ID |전경로currentACL/RLS·보호메타없음; CP-002/008,NFR-001/003,ACL01~08,V-027/033/036 |
| RG-06 |D-Sv1/v2·새 version실패·같은 versionindex교체·명시 old version |허용최신과전체최신분리·기존 pointer유지·과거출처자동치환0; UP-009,AP-007,CP-008,V-020/034,Q011/012 |
| RG-07 |규칙밖문장/부정/alias불명·복수값·질문속성부족·검색DB오류 |partial/hold/failed구분·미공유값으로보완0; UP-006,CP-009,V-006/012/033,Q013~016 |
| RG-08 |provider알 수 없는fact ID/역할 누락/rawJSON/refusal/usage유실 |schema/관계근거검증·미검증본문stream0·usage보존; UP-006/009,CP-006/007,V-006/007/009/037 |
| RG-09 |Grant/reader회수 뒤과거 답변/quote/cache/다음history/직접SQL |RAG assistant전체차단·허용항목만근거조회·rawRLS우회0; AP-008,CP-008,NFR-003,ACL09~12,V-020/034/038,Q019 |
| RG-10 |삭제/진행Job공개경합·cleanup장애/재시작·다른doc동명entity |즉시접근차단·오래된 worker재공개0·비용/최소FK보존·다른문서근거유지; AP-007,CP-009/010,V-019/034/037 |
| RG-11 |batch완료/usage만확정/벡터유실/unknown/retry·real/mock전환 |안전checkpoint만재사용·발생비용유지·불명재호출0·mode혼입0; AP-006,CP-004/006,NFR-002/004,V-018/029/030/032 |
| RG-12 |private관리자등록/Job조회·다른 tenant Grant재공유·키/경로오류 |limitedJob/관리메타만·권한확대0·정보비노출; AP-004/005/008,CP-002,NFR-003,ACL03~06/10,V-016/017/020/038 |

위12개는260/280 단계의 실제 API/DB/화면 시험 입력이며 시험 통과 수가 아니다. 단일 질의Q20은 Job경합/RLS/원장/삭제복구 시험을 대신하지 않는다. 실행 증거에는 source/색인 hash·relation→evidence 실제join·mode/모델/usage·권한거부·상태/저장확인·행/quote mapping을 기록하고 민감키/raw본문은 운영 로그에 남기지 않는다.

## 14. 요구 추적·자체 점검

| 요구 | 계약 |
|---|---|
| UP-006·UP-009·UP-012 |7~9절 규정/RAG·인용/원문·고정Agent 설명/지원범위와보류 |
| AP-004·AP-005·AP-006·AP-007·AP-008 |2~6/9/10절등록·Job·중복/재처리·삭제·exact-version공유/회수 |
| CP-002·CP-004·CP-006·CP-007·CP-008·CP-009·CP-010 |현재자원ACL·실제임베딩·저장복구·관계근거·버전Grant·삭제/남은근거·최소이력 |
| NFR-001·NFR-002·NFR-003·NFR-004·NFR-005·NFR-006 |tenant분리/실패·현재권한/비밀·중복/상한·bounded검색/시간·원문평가/재현 |

계획 관련요구21개·문형10개·Job단계5개·검색단계8개·검증입력12개를정적대조했다.7원문/6논리문서·EV18/R16·Q20은기존작성값을보존했고확정답입력유출을금지했다.512/8/4096·128청크/최대16배치와05의동시/한도·03복합키/공개gate·04state/오류/stream을대조했다. 과거파생본문RLS·삭제purge권한·typedRAG출력은선행설계의보완이므로11절에명시하고D240-08에통합한다. 미확인환경/실제품질/성능을합격으로보고하지않는다.

## 15. 다음 D240-06 화면 상세 작업 계획 — 문서 예상20분

다음산출물: **07 사용자와 관리자 화면 설계.md**. 기존UI7묶음/UP12/AP13과02~06계약을연결한다. 새정적시연/앱UI코드가아니라 화면정보·권한·행동·상태/API설계다. 기존215분/80시간안의배분이다.

| 순서 | 예상 | 구체작업·출력 |
|---|---:|---|
| 1 | 3분 |UI01~07 메뉴/로그인·사용/관리 진입·현재조직/역할표시·권한별접근/API 연결 |
| 2 | 5분 |UI02 고정Agent/질문·일반진행/RAG검증대기·이력/근거/원문·hold/failed/취소/저장불명/과거unavailable |
| 3 | 3분 |조직전환·두탭·늦은응답·캐시/근거정리·현재권한재조회·무권한메뉴/직접API거부 |
| 4 | 4분 |UI03~05 사용자역할·문서/private관리메타/Job/버전/Grant·삭제cleanup·Agent변경/중지의저장성공/실패/경합 |
| 5 | 3분 |UI06/07 비용추정/확정토큰/불명예약·real/mock·한도/배정·공통중지/재개·PADMIN범위와개인본문분리 |
| 6 | 2분 |UP12/AP13/7화면대조·시연수치와실제상태구분·자체점검·다음D240-07검증/재현상세계획 |

화면 설계 완료 뒤D240-07 시험/재현, D240-08 종합검토로이어간다. 사용자설계승인 후250 기능별구현계획/260시험을진행하며이번문서완료를서비스완성으로표시하지않는다.

## 16. 공식 근거·설계 선택·미확인

2026-10-04 확인. [pgvector 공식 저장소](https://github.com/pgvector/pgvector)는exact/approximate검색과cosine distance를설명한다. 작은corpus의exact 선택/상한수치는이번설계값이며DB설치/성능시험결과가아니다.

[Microsoft GraphRAG Local Search](https://microsoft.github.io/graphrag/query/local_search/)는Graph 구조와원문을함께문맥으로사용하는원리를설명한다.이번MVP의SQL/규칙추출/2hop/tenant권한구현을공식라이브러리가제공한다고가정하지않는다.

[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)는schema기반출력과refusal처리의참고다. schema에맞는값이사실/권한/관련성을증명하지않으므로서버fact검증/현재ACL과실제시험을별도로둔다. 모델/단가/timeout/예산은05를유지한다. runtime라이브러리버전/SDK호환/추출품질/검색측정/DB-RLS/키설정은미확인이다.

## 17. D240-08 통합 결과 — 종합 사용자 검토 대기

03 P-02/18절에all-source RAG payload gate·provenance control열권한·source_count/seal·write-only cleanup을반영했다.04 API표/15절에typedRAG buffer와본문unavailable·processing/publication/cleanup·job_kind를반영했다. 관리자는상태정보로개인title/본문을복원하지못한다. render_current_answer의Agent검사는불변유형/소유binding을확인하는뜻이며,과거저장답변은Agent enabled/config변경만으로차단하지않는다. 현재source/세션/소속gate는계속필수다. internal_cleanup은삭제위임/lease에한정된내용소거이고index처리/공개/유료호출권한이아니다. 개인reader의UI편집은범위밖이며회수시험은신뢰된운영/시험초기화가현재policy를변경해검증한다.

현재 통합 검토/구현 전달: [[200.프로젝트실행/240.설계/09 설계 검토 결과와 구현 전달]]. 선행 작성 당시 후속 계획은 이력이며 실제 구현/시험·유료 호출은 미수행이다.
