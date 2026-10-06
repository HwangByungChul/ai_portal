---
title: ACL 검색과 RAG 답변 구현 결과
created: 2026-10-06
updated: 2026-10-06
status: completed
stage: 250.구현
tags: [implementation-result, C04, rag, acl, evidence]
---

# I250-C04 ACL 검색과 RAG 답변 구현 결과

C04 서버 구현과 모의 검증을 완료했다. 현재 읽을 수 있는 정확한 문서 버전만 검색하고 원문·관계 근거를 검증한 후 답변을 원자 저장한다. 과거 답변에도 모든 출처의 현재 권한을 적용해 공유 회수 후 본문과 다운로드를 차단한다. 새 사용자/관리자 화면은 C05, 실제 모델 품질·합성7버전/Q20 평가는 C06 범위다.

참조: [[15 ACL 검색과 RAG 답변 상세 작업 계획]], [[09 문서와 GraphRAG 연결 상세 작업 계획]], [[17 문서·Job·공유·출처 화면 상세 작업 계획]], [[../260.테스트/evidence/C-rag/C04-README]].

## 구현 결과

- 현재 org/private/shared 문서 목록, 수신 조직·exact-version Grant 목록/발급/회수, 본인 run 근거·원문 다운로드를 추가했다. OpenAPI route는34→41개다. 조직 관리자도 private 원문을 자동 열람하거나 재공유할 수 없다. Grant는 게시 revision/CAS·현재 권한·중복/감사 rollback을 검사한다.
- 중앙 원장에 embed_query/generate_rag를 추가했다. 기존 예약/permit/dispatch/정산/슬롯/unknown 경계를 유지한다. query 확인 전 generation을 실행하지 않고 불명 응답을 자동 재발사하지 않는다. 모델·dependency·실사용 한도를 변경하지 않았다.
- 검색 scope는 조직/문서/버전/인덱스 복합키다. 허용 자료의 pgvector cosine 상위6청크 순위를 fact packet 우선순위에 반영하고 질문과 맞는 seed 최대4개에서2hop/최대32관계를 확장한다. 필요한 관계 부족·충돌은 근거 부족이며 DB/검색 오류는 failed로 구분한다.
- 원문 bytes SHA256·Unicode 구간/행·exact quote·관계/근거 링크·pipeline/mode를 재검사한다. 제한 실행 역할에 새로운 title/text/quote/vector SELECT 권한을 주지 않고 필요한 hash/연결 metadata만 허용했다.
- 모델은 strict JSON의 answer_kind/selected_fact_ids만 반환한다. 서버가 허용 fact로 사실·조건·인용을 렌더링한다. 자유 문장·새 필드·없는 fact·중복/잘못된 형식·끊어진 책임 관계를 공개하지 않는다. query4000/context2000/final6000토큰 상한을 유지한다.
- RAG 본문·근거·sealed·run 완료를 같은 transaction으로 저장한 후 정본을 공개한다. 저장 전 RAG draft는 SSE에 보내지 않으며 기존 일반 streaming은 유지한다.
- 현재 소속/Agent/문서/게시/Grant/hash 연결을 과거 답변에도 검사한다. 출처 하나가 회수되면 전체 본문은 unavailable이다. 근거 목록은 현재 허용 항목만 제공하고 회수 ordinal은 unavailable이다. 다운로드는 전체 답변 gate와 exact-source/file SHA를 재확인한다.

## 최종 검증

| 구분 | 실제 관측 |
|---|---|
| 전체 backend | 737개 통과 / 실패0 / skip0 / 785.91초 |
| 최종 관련 | 35개 통과 / 46.63초; 전체에 포함 |
| 기존 화면·build | 51개 통과 / runner 오류0 / 124.42초 |
| 기본 native 서버 | health 통과 / OpenAPI41 / mock·execution/index 유지 |
| 추가 실제 provider | 0회 / 추가비용0원 |

실제 PostgreSQL role/FORCE RLS에서 A/B·private·v1/v2·외부 참조·Grant CAS/감사 rollback·동시 발급 중복 방지·회수 후 본문 차단을 확인했다. 두 출처 중 하나를 회수해도 전체 답변 본문이 숨겨진다. 저장 직전 Agent/Grant 변경·위조 quote/relation·query unknown·검색 장애·관측된 generation의 usage 누락을 구분했다. usage_unknown은 실제 비용이 확인된 성공으로 표현하지 않는다.

실제 HTTP 접수→완료→같은ID 재조회→근거/다운로드→철회 차단, 고정 가짜 HTTP의 strict schema SDK 계약을 검증했다. native 재시작 후 같은 완료 본문/접수ID를 조회하며 추가 provider 호출이 없었다. 모든 임의 SIGKILL 시점이나 모든 동시 삭제 경합을 망라한 시험은 아니다. 기존 전체 suite에 일반 실행·Job·장애·lease·동시성 경계가 포함한다.

기본 DB 적용 후 첫 native 확인은 종료된 화면 시험의 포트 재사용 검사에서 bind 오류가 났다. 실행 중인 listener가 없는 것을 확인하고 재사용 가능한 검사로 바꾼 뒤 native health/41개 route·종료 connections0을 재확인했다. DB 변경은 재실행하지 않았으며 재적용0이었다.

초기 시험에서 nested pool 점유·메타데이터 조회 권한·UUID 응답 직렬화를 수정했다. 첫 전체 회귀734pass/1fail은 활성 RAG를 미구현으로 기대한 이전 HTTP 시험이었다. 현재 기대값으로 갱신하고 전체를 재실행했다. 새 동시 시험의 연결 도우미도 정정한 후 최종 관련35개가 통과했다.

## 적용과 보존

최종 시험 후 기본 DB에는014_document_sharing/015_rag_execution/016_rag_provenance만 적용했다. 재적용0·업무31테이블/infra1·migration17·security함수76·FORCE RLS17·pgvector0.8.6이다. C03 기록과 기존31테이블의 기존 열/모든 행 SHA를 대조해 동일함을 확인했다.

기존 일반 실호출3회·내부 비용 추정0.19원·예약0/slot0을 보존했다. 공급자 청구 확인값은 아니다. app.env/키/역할 설정을 변경하지 않고 기본 mock/RAG 비활성을 유지했다. 기본 DB에 새로운 corpus/RAG 실행을 적재하지 않았다.

보호29파일·역사59파일·원본 GraphRAG9소스/HEAD·관련 없는 미추적74파일을 보존했다. 날짜 변경으로 임시 실행 도우미가 정리돼 기존 private JUnit/C03 증거·Git에서 실행 맥락을 복원했으며, 적용 전 보호 snapshot과 이전 C03 DB projection을 다시 대조했다. private 로그/키는 공개 증거에 넣지 않았다. 종료 시 connection/임시DB/listener0·DB 정지다. 원격 push/배포 없음.

검증 소스 local commit: aa52b595b00bf35b975d339282aa9e5bde4aef83. 최종 160개 소스 SHA와 정확 변경 파일을 연결하며 문서/증거는 별도 로컬 commit으로 기록한다.

## 한계와 다음 작업

현재 RAG는 질문별 고정 규정 관계를 처리하며 이전 대화 내용은 모델 입력에 포함하지 않는다. 지원 문형 밖에서는 근거 부족으로 보류한다. 벡터 순위는 packet 우선순위에 반영하지만 실제 embedding의 의미 검색 품질은 미측정이다. 파일 bytes 무결성은 검색/다운로드에서 확인하고 과거 본문 DB gate는 저장 hash/FK·현재 권한을 검사한다.

실제 모델·전체7버전 적재/Q20·새 문서/RAG 화면·전체V41·파일럿/이행/전체MVP는 미완료다. Q20 원본은 not_run이다. 다음 C05 예비3시간은 관리자 문서/Job→버전 공유→사용자 문서 선택/규정 질문→현재 근거/다운로드→화면 회귀 순서다. 상세계획은 [[17 문서·Job·공유·출처 화면 상세 작업 계획]]에 기록했다.

WBS는 I250-3 서버 구현 완료/I250-4 RAG 서버 완료·화면 연결 진행으로 갱신한다. 전체 MVP는 약60~65%의 작업 범위 추정이며 가중치·실측 공수 기반 진척률이 아니다. 개인 실제 공수 미측정·10월31일/주20시간 이상/총80시간(여유10시간 포함) 기준을 유지한다.
