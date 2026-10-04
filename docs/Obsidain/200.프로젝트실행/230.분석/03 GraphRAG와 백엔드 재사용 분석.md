---
title: GraphRAG와 백엔드 재사용 분석
created: 2026-10-04
updated: 2026-10-04
status: reviewed
stage: 230.분석
tags: [analysis, graphrag, backend, reuse, gap]
---

# GraphRAG와 백엔드 재사용 분석

## 결론

기존 프로젝트는 **문서 처리·도메인 스키마·규칙 기반 추출·검색/근거 계약·고정 워크플로 골격을 선택 재사용**하는 기반으로 적합하다. 현재 별도 백엔드를 그대로 포털·멀티테넌트·AI Gateway 완성품으로 사용하기에는 IAM/조직 권한·실제 저장소·색인 연결·관계 근거·공통 호출/usage·대화/Job 운영을 보완해야 한다.

원본을 통째로 복사해 두 개의 검색/백엔드 경로를 함께 유지하지 않는다. 승인된 단일 FastAPI 업무/API/AI 경로와 GraphRAG 공통 코어 계약으로 연결하는 방안을240에서 설계한다. 모델 교체·새 Gateway 제품·LangGraph 필수 도입을 추가하지 않는다. 경량 고정 실행 골격을 활용하되 상태/취소/한도는 플랫폼 책임으로 보완한다.

## 기준과 확인 한계

[[200.프로젝트실행/230.분석/02 분석 대상과 기준 버전]]의 HEAD913f388 및 현재 파일 지문과 일치함을 확인한 뒤 읽기 분석했다. 코드/테스트를 실행하지 않았고 DB 정책·실제 schema/view·모델 응답·프론트 연결은 미검증이다. 비밀설정/키/DB 비밀번호 값은 수집/출력하지 않았다. 역사 검토를 그대로 옮기지 않고 아래 현재 파일 근거를 확인했다.

## 재사용 단위

| 단위 | 재사용 판단 | 필요한 보완 |
|---|---|---|
| DocumentPipeline/Parser/Chunker/Metadata | 골격/순수 처리 선택 재사용 | 파일 한도 사전검사, 문서/색인 버전·동일 처리, 권한 metadata와 실제 강제 구분 |
| DomainSchema/Entity/Relation/Evidence 계약 | 재사용 후 tenant/version/Grant 경계 확장 | 규정/책무 스키마·별칭·방향 규칙, 유효 원문 근거 |
| InMemory Graph/Vector | 모의/단위 시험용 참고 | auth 강제 보완, 실제 임베딩/DB·지속 저장 용도로 사용하지 않음 |
| PostgreSQL/PGVector 어댑터 | 인터페이스만 참고 | 실제 읽기/쓰기·RLS·동시/삭제 트랜잭션 신규 구현 |
| HybridRetriever/ContextAssembler | 수정 재사용 | 관계별 근거·권한 필터 전파·근거/오류 상태·정확한 버전 |
| Agent 상태/WorkflowFactory/노드 | 고정 흐름 골격 참고 | 비동기 공통 호출·플랫폼 지속 실행/취소/중지/usage |
| Core AdminService 단계 timeline | 처리 단계 참조 | 메모리/무권한 운영 경로를 실제 DB/Job/정책으로 교체 |
| 별도 backend API/SQL/모델 코드 | 흐름·요청/응답/SQL 아이디어 선별 | 모의 인증/전역 prompt·category 권한·직접 AI·색인 단절·숨긴 실패 제거 |
| 원본 테스트 | 문서/추출/검색 기본 회귀 참고 | 실제 멀티테넌트/다중 관계 근거/DB/usage/취소·재시작 검증 추가 |

## 현재 코드 근거

### E01

[src/common_core/ai_pipeline/document/document_pipeline.py — 확인 위치 48](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/document/document_pipeline.py:48>): DocumentPipeline이 파싱/정규화/청킹/metadata를 조합한다. source.content가 필요하고 재처리 document ID는 UUID로 생성되므로 버전/해시/동일 처리 계약은 추가해야 한다.

### E02

[src/common_core/ai_pipeline/document/parser_registry.py — 확인 위치 25](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/document/parser_registry.py:25>): TEXT/MARKDOWN 등록과 경량 파서가 있다. FILE/URL 등록은 실제 파일 fetch/URL loader 구현과 같지 않다.

### E03

[src/common_core/ai_pipeline/graphrag/schemas.py — 확인 위치 40](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/graphrag/schemas.py:40>): AuthContext에 tenant_id/user_id/roles가 있으나 선택값이다. 계약 필드 존재만으로 실제 권한 검사 완료를 뜻하지 않는다.

### E04

[src/common_core/ai_pipeline/graphrag/graph_store.py — 확인 위치 194](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/graphrag/graph_store.py:194>): 메모리 Graph 조회/탐색/삭제가 auth 인자를 받지만 해당 경로에서 auth를 강제하지 않는다. entity/relation 키도 domain 기반이며 tenant/version 분리는 없다.

### E05

[src/common_core/ai_pipeline/vectorstores/in_memory.py — 확인 위치 51](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/vectorstores/in_memory.py:51>): 메모리 벡터는 토큰 빈도 cosine 방식이고 auth 강제는 없다. 실제 OpenAI 임베딩/영속 pgvector와 다르다.

### E06

[src/common_core/ai_pipeline/graphrag/postgres_graph_store.py — 확인 위치 23](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/graphrag/postgres_graph_store.py:23>): PostgreSQLGraphStoreAdapter의 쓰기/조회/탐색/삭제가 NotImplementedError 골격이다.

### E07

[src/common_core/ai_pipeline/vectorstores/pgvector_adapter.py — 확인 위치 14](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/vectorstores/pgvector_adapter.py:14>): PGVectorStoreAdapter의 add/search/delete/get_chunks가 미구현이고 health는 false다.

### E08

[src/common_core/ai_pipeline/graphrag/hybrid_retriever.py — 확인 위치 196](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/graphrag/hybrid_retriever.py:196>): _relation_evidence는 relation_id가 비어 있지 않으면 전체 evidence를 반환한다. 여러 관계의 근거를 관계별로 좁히지 않는다. _find_seed_entities도 request.filters를 seed query로 전달하지 않는다.

### E09

[src/common_core/ai_pipeline/graphrag/context_assembler.py — 확인 위치 29](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/graphrag/context_assembler.py:29>): 근거/청크 참조와 인용 목록을 조립한다. 첫 evidence 선택 및 글자수/4 token 추정은 실제 usage나 관계별 올바른 근거 검증을 대체하지 않는다.

### E10

[src/common_core/agents/nodes/llm_answer_node.py — 확인 위치 17](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/agents/nodes/llm_answer_node.py:17>): 답변 제공자 callable을 주입할 수 있으나 기본은 Answer draft 문자열이다. 제공자 호출은 동기 계약이며 공통 비동기 AI 호출과 연결 보완이 필요하다.

### E11

[src/common_core/agents/workflow_factory.py — 확인 위치 36](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/agents/workflow_factory.py:36>): 노드 레지스트리와 경량 비동기 순차 실행이 있다. 실행/취소/한도/DB checkpoint가 있는 운영 엔진은 아니다. 고정 흐름의 골격으로 재사용 가능하다.

### E12

[src/common_core/ai_pipeline/graphrag/schema_registry.py — 확인 위치 30](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/graphrag/schema_registry.py:30>): 기본 도메인은 농업 sol_bat이며 관계 keyword 규칙도 농업 중심이다. 규정/책무 schema·별칭·방향성 규칙을 별도로 작성해야 한다.

### E13

[src/common_core/admin/service.py — 확인 위치 52](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/admin/service.py:52>): 관리 서비스는 메모리 sources/source_status/jobs와 기본 메모리 저장소다. 단계 timeline/재시도 참조는 가능하나 Job 영속성/현재 권한/중복 방지·실제 임베딩 완료 판정은 보완이 필요하다.

### E14

[backend/app/api/auth.py — 확인 위치 23](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/auth.py:23>): 모의 로그인은 입력 password를 검증하지 않고 미등록 email을 ROLE_ADMIN approved로 만든다. 실제 사용자 인증/승격 정책으로 재사용하지 않는다.

### E15

[backend/app/api/deps.py — 확인 위치 55](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/deps.py:55>): verify_workspace_access는 ROLE_ADMIN의 모든 workspace 접근을 허용한다. 주 chat/source/prompt 라우트는 get_current_user_id를 사용하며 실제 소속/개인 ACL 계약이 없다.

### E16

[backend/app/api/workspaces.py — 확인 위치 28](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/workspaces.py:28>): workspace 목록은 source category 전체 집계이고 생성은 placeholder source다. category는 사용자 조직 소속/권한 증명이 아니다.

### E17

[backend/app/api/sources.py — 확인 위치 17](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/sources.py:17>): 업로드는 category에 저장하지만 실제 ingestion trigger는 주석이다. 지원 목록은 pdf/txt/docx이며 MVP Markdown 지원·한도·권한·버전/해시·Job 연결을 보완해야 한다.

### E18

[backend/app/ai/ingestion.py — 확인 위치 34](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/ai/ingestion.py:34>): 직접 OpenAI 임베딩 후 bare chunks/sources를 사용한다. Graph 추출은 주석/Mock인데 graph_status completed를 갱신한다. API의 graphrag.graphrag_* 테이블 흐름과 불일치하며 실제 DB alias/호환성은 미확인이다.

### E19

[backend/app/ai/retriever.py — 확인 위치 20](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/ai/retriever.py:20>): query embedding을 직접 호출한다. 벡터 검색 category와 별개로 Graph SQL에는 workspace/개인 ACL 조건이 없다. 예외 폴백/Graph 예외 무시는 검색 실패 구분을 흐린다.

### E20

[backend/app/api/chat.py — 확인 위치 17](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/chat.py:17>): JWT sub 확인으로 chat을 실행하고 전역 prompt·직접 LLM을 사용한다. conversation_id는 입력만 있고 사용하지 않는다. 매번 session을 만들며 저장 실패를 무시하고 text/plain 문자열을 스트리밍한다.

### E21

[backend/app/api/prompts.py — 확인 위치 48](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/prompts.py:48>): workspace_id 경로에도 프롬프트 version/active 상태는 전체 테이블을 갱신한다. 사용자 ID 확인만으로 저장하고 조직/Agent 설정 경계가 없다.

### E22

[backend/app/db/session.py — 확인 위치 7](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/db/session.py:7>): 비동기 session/search_path 골격은 있으나 이 파일에 transaction-local tenant/RLS runtime role 설정은 없다. 실제 DB 정책/역할은 접속하지 않아 미확인이다.

### E23

[backend/app/main.py — 확인 위치 24](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/main.py:24>): 백엔드 라우터는 app.api의 별도 auth/workspace/source/prompt/chat을 연결한다. common_core 관리/검색 경로와 중복이며 주 경로가 common_core 검색을 직접 조합하지 않는다.

### E24

[tests/test_graph_store.py — 확인 위치 147](</Users/jwpios/antigravity/GraphRAG AI Agent/tests/test_graph_store.py:147>): PostgreSQL 어댑터 테스트는 미구현 예외를 확인한다. 메타데이터 tenant 필드 테스트/단일 관계 검색 테스트는 A/B 격리 또는 다중 관계 근거 교차 차단 증거가 아니다.

### E25

[src/common_core/admin/routers.py — 확인 위치 20](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/admin/routers.py:20>): common_core 관리 router는 인증 dependency 없이 메모리 service를 호출한다. 백엔드 main에 연결된 제품 IAM/API로 그대로 노출하지 않는다.

### E26

[backend/app/api/sources_global.py — 확인 위치 12](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/sources_global.py:12>): source 전체 목록은 사용자 ID만 확인하고 category/tenant/개인 ACL로 제한하지 않는다. 전역 source 목록을 개인/조직 자료의 통합 조회로 그대로 쓰지 않는다.


## 핵심 보완 항목과240 전달

| Gap | 우선 | 관찰 및 영향 | 설계 입력·관련 검증 |
|---|---|---|---|
| G01 조직/IAM | P0 | 모의 로그인·전역 관리자 접근·category 전체 목록은 실제 소속/권한과 다름 | 계정/소속/역할·현재 문맥·개인 ACL, V-001/013~015/026~027/036 |
| G02 실제 저장소 | P0 | DB/벡터 어댑터가 골격이고관리Job은메모리 | 실제 schema·runtime역할/RLS·읽기/쓰기/복구, V-027/032/037 |
| G03 근거 연결 | P0 | 관계별 evidence 선택이 전체목록이고seed에filter누락 | relation→evidence join·버전/권한필터·일반/RAG 결과 구분, V-006/009/033 |
| G04 실제 색인 | P0 | 업로드 trigger주석·다른테이블명·Graph미수행 완료표시 | 문서/Job/색인계약통일·실제산출물검증·재처리중복방지, V-016~019/032 |
| G05 공통AI/usage | P0 | 생성/문서/질의임베딩직접호출·원장/한도흐름부재 | 공통비동기adapter·예약/확정/불명·중지/동시한도, V-023~025/029~031 |
| G06 대화/실행 | P0 | conversation미사용·저장실패무시·부분text스트림 | 조직/소유대화·실행종결/취소·저장실패·구조화근거응답, V-007~010/031/037 |
| G07 삭제/공유 | P0 | source단위메모리삭제와전역자료경로는Grant/파일/Job회수에불충분 | 즉시권한차단·버전Grant·파생삭제/남은근거·공개재검사, V-019/020/034 |
| G08 Agent설정 | P0 | activeprompt전역UPDATE는조직Agent범위와충돌 | 조직Agent2·설정version·현재허가/중지, V-003/021/022 |
| G09 규정도메인 | P0 | sol_bat 기본규칙은규정책무와다름 | 가상규정schema/별칭/명시방향규칙과정답근거, V-006/032/033/041 |
| G10 고급검색 | 후속 | HYBRID_RERANK enum은있으나search분기에는구현이없음 | MVP는HYBRID기본에집중,고급rerank를완성기능으로표시하지않음 |

P0는MVP필수정확성/권한/실제흐름이다. 각Gap을별도서버/제품으로만드는뜻이아니다. G01/G02→G05/G06/G08→G04/G03/G07/G09의기능연결순서를240에서구체화한다. 화면장식·정교한통계보다핵심흐름을우선하고초기80시간가정은실측후조정한다. 분석만으로10월말전체구현완료를보장하지않는다.

## 요구41개와재사용/보완 연결

분류는새MVP요구를충족시키는구현방안이며현재기능완료비율이아니다. 신규중심도기존계약/코드아이디어를참고할수있다. 동일모듈이복수요구를함께충족하므로행개수를독립개발Task/공수로합산하지않는다. 아래표는코어/백엔드판단이며화면재사용은다음A230-03에서추가한다.

| 요구 | 기능 | 판단 | 현재근거 | 보완·240설계입력 | 검증 |
|---|---|---|---|---|---|
| UP-001 | 로그인·로그아웃 | 신규 중심 | E14/E15 | 실제 인증·로그아웃·현재 소속 조회 | V-001 |
| UP-002 | 조직 선택·전환 | 신규 중심 | E15/E16 | A/B 조직 소속/전환 및 기존 화면 응답 분리 | V-002 |
| UP-003 | 허용 Agent 목록·선택 | 신규 중심 | E11/E21 | 조직별 고정 Agent 목록·허가·상태 | V-003 |
| UP-004 | 질문 입력·전송 | 재사용+수정 | E20 | 질문 검증·전송 식별·동시 한도 | V-004 |
| UP-005 | 일반 질의 답변 | 재사용+수정 | E10/E20 | 저비용 공통 실제 생성·일반 흐름·usage 연결 | V-005 |
| UP-006 | 문서 기반 RAG 답변 | 재사용+수정 | E04/E08/E09/E19 | 권한 검색·관계별 근거·RAG 공통 호출 | V-006 |
| UP-007 | 실행 진행·실패 상태 | 신규 중심 | E20 | 지속 실행/부분 실패·저장 오류·재조회 계약 | V-007 |
| UP-008 | 본인 실행 취소 요청 | 신규 중심 | E11/E20 | 본인 취소·실제 종결·사용량 상태 | V-008 |
| UP-009 | 근거 목록·원문 조회 | 재사용+수정 | E09/E26 | 근거 버전·현재 ACL·원문 접근 | V-009 |
| UP-010 | 본인 대화 저장·재조회 | 재사용+수정 | E20/E22 | 조직/소유 대화 DB·conversation 실제 사용·이력 API | V-010 |
| UP-011 | 중지·한도·무권한 안내 | 신규 중심 | E15/E20 | 현재 권한·Agent/공통 중지·한도 거부 | V-011 |
| UP-012 | 근거 부족 안내 | 재사용+수정 | E08/E19/E20 | 근거 부족/검색 오류/무권한 결과 구분 | V-012 |
| AP-001 | 관리 조직 선택과 관리 진입 | 신규 중심 | E15/E16 | 허용 관리 조직·현재 역할 | V-013 |
| AP-002 | 조직 사용자·소속·활성 상태 관리 | 신규 중심 | E14/E15 | 조직 소속 활성 관리·전역 계정 분리 | V-014 |
| AP-003 | 조직 역할 배정·회수 | 신규 중심 | E14/E15 | 승격 제한·관리자 배정/회수 | V-015 |
| AP-004 | 문서 등록·범위 지정 | 재사용+수정 | E01/E02/E17 | TXT/Markdown·조직/개인 등록·버전/Job | V-016 |
| AP-005 | 문서·색인 상태 및 오류 조회 | 재사용+수정 | E13/E18 | 실제 DB Job·검증 완료/실패·최소 운영 조회 | V-017 |
| AP-006 | 실패 색인 작업 재처리 | 재사용+수정 | E13/E18 | 현재 권한·예약·중복 방지·영속 재처리 | V-018 |
| AP-007 | 문서 삭제·신규 접근 차단 | 재사용+수정 | E04/E13 | 권한 삭제·즉시 접근 차단·남은 근거 유지 | V-019 |
| AP-008 | 조직 문서 버전 공유 승인·회수 | 신규 중심 | E03/E04 | 문서 버전/조직 Grant·회수·재공유 거부 | V-020 |
| AP-009 | 고정 Agent 기본 설정 | 재사용+수정 | E21 | 조직 Agent 설정 버전·권한·유효성 | V-021 |
| AP-010 | Agent 중지·재개 | 신규 중심 | E11/E20/E21 | 조직별 중지/재개와 신규 호출 차단 | V-022 |
| AP-011 | 조직 사용량·호출 상태 조회 | 신규 중심 | E19/E20 | 단일 usage 조회·불명/임베딩 포함 | V-023 |
| AP-012 | 조직 한도 설정 | 신규 중심 | E15/E20 | 상위 배정·조직 한도·동시 예약 | V-024 |
| AP-013 | 프로젝트 합산 조회·공통 운영 중지 | 신규 중심 | E19/E20 | 프로젝트 합산/공통 중지·승인 예산 경계 | V-025 |
| CP-001 | 인증·활성 소속·요청 조직 문맥 | 신규 중심 | E03/E15/E22 | 필수 문맥·현재 소속·Job 주체 | V-026 |
| CP-002 | 자원·개인·공유 접근 강제 | 신규 중심 | E03/E04/E05/E15/E26 | 서비스/Graph/벡터/DB RLS/파일 ACL | V-027 |
| CP-003 | 요청 추적·입력 제한·동일 전송 식별 | 신규 중심 | E17/E20 | 요청/전송 식별·입력/HTTP/동시 제한 | V-028 |
| CP-004 | 생성·임베딩 공통 AI 호출 | 재사용+수정 | E10/E18/E19/E20 | 공통 비동기 생성/임베딩 adapter | V-029 |
| CP-005 | 단일 사용량 원장·한도 예약/정산 | 신규 중심 | E18/E19/E20 | 원장 소유·예약/확정/불명·조직/합산 한도 | V-030 |
| CP-006 | 실행·취소·재시도·중지 상태 | 신규 중심 | E11/E13/E20 | 실행/Job 종결·중지·취소·제한 재시도 | V-031 |
| CP-007 | 문서 색인·버전·재처리 | 재사용+수정 | E01/E02/E06/E07/E13/E18 | 실제 색인 저장·단계 검증·버전/중복 방지 | V-032 |
| CP-008 | GraphRAG 검색·관계별 근거·보류 | 재사용+수정 | E04/E08/E09/E12/E19 | 규정/책무 규칙·권한 검색·정확한 근거 | V-033 |
| CP-009 | 삭제·공유 회수·산출물 공개 재검사 | 재사용+수정 | E04/E13/E17 | 삭제/회수·파일/캐시/Job 공개 검사 | V-034 |
| CP-010 | 오류·관리 변경 최소 활동 기록 | 신규 중심 | E13/E20/E21 | 권한/오류/변경 추적과 내용 비노출 | V-035 |
| NFR-001 | 조직·개인 격리의 동시성 일관성 | 신규 검증+보완 | E03/E04/E15/E22 | 실제 RLS/Job/동시·개인/관리 우회 시험 | V-036 |
| NFR-002 | 대화·색인·원장 지속 저장과 재시작 복구 | 신규 검증+보완 | E06/E07/E13/E20 | 실제 저장·복구·실패/불명 상태 | V-037 |
| NFR-003 | 비밀·개인 내용 노출 최소화 | 신규 검증+보완 | E17/E20/E26 | 키/개인 내용 비노출·현재 ACL | V-038 |
| NFR-004 | 설치·합성 데이터 초기화·시연 재현 | 신규 검증+보완 | E06/E07/E13/E23 | MVP 설치/합성 초기화·실제/모의 시연 | V-039 |
| NFR-005 | MVP 성능 측정·제한 검증 | 신규 검증+보완 | E05/E08/E24 | 실제 모델/검색/Job 환경과 측정 계약 | V-040 |
| NFR-006 | 평가·검증 증거와 미완료 보고 | 신규 검증+보완 | E24 | 20질문 및 ACL/운영 검증 증거·결함 추적 | V-041 |

## 원본테스트의위치와한계

원본tests의11개파일에test_함수32개가있음을정적으로확인했다. 이번실행결과/통과여부는없다. 기존메타데이터tenant필드검사는ACL강제와다르며단일관계근거시험은다중관계의잘못된근거연결을배제하지못한다. DB어댑터가NotImplementedError를던지는시험은영속저장구현완료를뜻하지않는다. 기존11파일을그대로새41개요구의검증증거로사용하지않는다.

현재backend의실제DB에별도RLS/view/alias가존재하는지는접속하지않아미확인이다. E18의테이블불일치는코드상연결Gap이며실제운영DB의호환여부를단정하지않는다. 원본init/checkDB를실행하거나민감설정의기본값을복사하지않았다.

## 다음 A230-03 화면·업무 연결 분석 — 예상30분

1. 5분: BNK시연PNG42개를기능군/초안/2차로구분하고UP/AP관련표본을선정한다. 버전은파일명과실제내용으로판단한다.
2. 10분: Chat·Agent목록·대화이력·Knowledge·사용자역할·운영/미터링관련이미지를확인하고MVP표시요소/부족상태를정리한다. 고급Marketplace/Canvas화면은후속으로분리한다.
3. 10분: GraphRAG frontend의실제page/위젯/API호출·모의배열·alert/저장·router를읽어화면의실제연결여부를대조한다. 이번단계에서도브라우저/백엔드/DB는실행하지않고코드관찰과시연이미지내용을구분한다.
4. 5분: UP12/AP13별화면기존자산·보존/변경/신규·필수권한/상태·240전달을04문서에작성/점검한다. 이미지없는화면을임의추정하지않는다.

산출물은04화면과업무연결분석.md다. 기능요구전체와화면자산의대응/보완을추적할수있으면문서작업완료로보고하며실제UI동작검증완료로표시하지않는다. 완료보고에는A230-04합성자료/평가질문작성의상세계획을포함한다.

## 자체점검

요구41개/V41의누락·중복없이파일근거E01~26와설계입력을연결했다. 코드지문과Git상태가선행기준과같음을확인했고원본변경/테스트/API호출은없다. 사실관찰과재사용의견·DB/동적실행미검증을구분했다. 화면분석과데이터/정답작성은아직후속작업이며앱구현은미착수다.

관련: [[200.프로젝트실행/220.요구정의/07 요구정의 검토 결과와 후속 전달]], [[200.프로젝트실행/230.분석/01 분석 상세 작업 계획]].
