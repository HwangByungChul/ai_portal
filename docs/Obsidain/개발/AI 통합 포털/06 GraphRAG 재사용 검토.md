---
title: GraphRAG 재사용 검토
created: 2026-10-04
updated: 2026-10-04
status: review-draft
purpose: BNK 생성형 AI 플랫폼 개인 학습·MVP
tags: [ai-portal, bnk-platform, graphrag, mvp]
---

# GraphRAG 재사용 검토

## 결론

**기존 프로젝트는 Knowledge Pipeline·Retrieval·Agent 노드의 공통 코어로 활용할 수 있다. 플랫폼 전체, 중앙 AI G/W, 금융 운영환경이 완성된 상태는 아니다.** 코어 계약과 단위 흐름을 우선 재사용하고 웹 백엔드·관리자 화면은 기능별로 연결 상태를 확인해 선별한다.

검토 기준은 GraphRAG 저장소 HEAD `913f388`과 현재 작업 파일이다. 공통 코어는 Git 이력에 포함되어 있으나 `backend/`, `frontend/`, 실행 스크립트는 현재 untracked 상태다. 수정된 요구정의 문서도 있다. 따라서 공통화 완료 문서와 현재 웹 앱을 같은 검증 기준으로 보지 않는다. 원본 파일·Git 상태를 변경하지 않았다.

## 실행 확인

프로젝트의 `tools/run_tests.py`로 11개 시험 파일의 **32개 함수 시험이 모두 통과**했다. 실패 0, 생략 0. 사용 환경에 pytest가 없어 프로젝트 자체 실행기를 사용했다. 바이트코드·시험 캐시 생성은 비활성화했다.

시험 범위는 문서 처리, 메모리 저장소, 규칙 기반 추출, 근거 조립, 검색, 간단 Workflow, AdminService와 샘플 파일럿이다. **실제 DB, 모델 API, 브라우저/API 통합, 계열사 격리·권한 차단은 이번 실행으로 검증되지 않았다.** 외부 DB 접속·모델 호출·DB 초기화·서비스 실행은 수행하지 않았다.

## 재사용 단위

| 자산 | 현재 확인한 상태 | 활용 방안 |
|---|---|---|
| DocumentPipeline·ParserRegistry·Chunker | 텍스트/Markdown/JSON/CSV 중심의 경량 처리·메타데이터 | 합성 문서 MVP의 처리 골격. PDF/DOCX/OCR 별도 구현 |
| DomainSchema·SchemaRegistry | 도메인별 개체·관계 정의 | `bnk_regulation_demo` 스키마 추가. 기존 농업 샘플 스키마 분리 |
| Entity/RelationExtractor·Resolver·EvidenceLinker | 규칙 기반 추출·정규화·연결 | 작은 규정/책무 평가셋으로 재설계·평가 |
| VectorStoreAdapter·GraphStoreAdapter | 제공자 교체 인터페이스 | 실제 PostgreSQL/pgvector 구현과 ACL 계약 추가 |
| HybridRetriever·ContextAssembler | 검색 결합·근거 컨텍스트 조립 | 구조는 유지, 권한/필터·인용 정확성·전략 처리 보완 |
| Retrieve/Answer/StructuredOutput 노드 | 상태 전달·조회·응답 훅 | 고정 Agent 흐름. 실제 모델은 중앙 호출 계층으로 주입 |
| WorkflowFactory | 경량 실행기, LangGraph 추가 전 브리지 | 초기 고정 노드 실행. 체크포인트·장기 작업 런타임으로 간주하지 않음 |
| AdminService·admin 라우터 | 문서·색인·검색 시험의 메모리 흐름 | 관리 기능 계약을 참고하고 영속성/조직 권한 추가 |
| 별도 FastAPI backend | DB SQL·모델 직접 호출, 코어와 별도 경로 | 공통 코어로 수렴시키고 인증·DB·색인 경로 수정 |
| React 관리자 화면 | 일부 모의 데이터·동작 존재 | 문서·검색 관리 컴포넌트 선별, 실제 API·상태 연결 |

## 통합 전 핵심 보완

| 우선 | 확인 사실 | 통합 영향·조치 | 코드 근거 |
|---|---|---|---|
| P0 | 모의 로그인은 비밀번호 검증 없이 새 이메일에 관리자 역할을 생성 | 테스트 전용으로 격리하고 인증·사용자 승인·역할 부여를 분리 | backend/app/api/auth.py:23~49 |
| P0 | 코어 메모리 저장소는 AuthContext를 받지만 사용자/조직 권한을 검색·삭제에 강제하지 않음 | 인증 문맥 존재만으로 격리 보장 불가. 모든 저장소 검색·탐색·근거·삭제에 공통 ACL 적용 | vectorstores/in_memory.py, graphrag/graph_store.py |
| P0 | 백엔드 Graph SQL에 workspace/사용자 필터 없음. 문서/채팅 API는 사용자 ID 인증만 사용 | A/B 조직 격리·소속 검사·개인 문서 ACL 선행 | backend/app/ai/retriever.py:58~75, api/sources.py, api/chat.py |
| P0 | 업로드 색인 트리거가 주석 처리됨 | 업로드→작업→색인→질의 연결, Worker는 자체 DB 세션 사용 | backend/app/api/sources.py:62~63 |
| P0 | 업로드/검색은 graphrag_sources·graphrag_chunks, ingestion/init_db는 sources·chunks 사용 | schema search_path와 별개로 테이블명·ID·컬럼이 다름. 단일 마이그레이션 기준 확정 | backend/app/ai/ingestion.py:49~64, backend/init_db.py |
| P0 | PostgreSQL/pgvector 코어 어댑터가 NotImplementedError | DB 지속성 구현 전 운영 검색 엔진으로 사용할 수 없음 | vectorstores/pgvector_adapter.py, graphrag/postgres_graph_store.py |
| P1 | ingestion의 그래프 추출은 Mock인데 graph_status를 completed로 변경 | 실제 수행한 단계만 완료, NOT_RUN/FAILED 구분 | backend/app/ai/ingestion.py:55~64 |
| P1 | _relation_evidence는 관계 ID가 있으면 탐색 근거 전체 반환 | 관계별 EvidenceLink로 매칭하고 관계 A에 문서 B가 인용되지 않는 시험 추가 | graphrag/hybrid_retriever.py:197~203 |
| P1 | HYBRID_RERANK는 enum에 있으나 조회 분기는 VECTOR_ONLY/GRAPH_ONLY/HYBRID만 처리 | 미지원 전략 거절 또는 실제 검색+리랭킹 구현. 현 상태 지원 표시 금지 | graphrag/schemas.py:31, hybrid_retriever.py:47/76 |
| P1 | Prompt API의 workspace_id가 SQL 범위를 제한하지 않으며 전체 활성 Prompt 해제 | tenant/agent/version 범위·관리 권한·동시 버전 생성 통제 | backend/app/api/prompts.py |
| P1 | 채팅은 모델 직접 호출, conversation_id 미사용, 저장 오류 무시 | 중앙 G/W·대화 이어하기·실행 원장·저장 실패 상태·취소 처리 | backend/app/api/chat.py |
| P1 | DOCX 업로드 허용과 달리 ingestion은 PDF 외 파일을 UTF-8 텍스트로 읽음 | 파서 지원 형식 일치, 용량·파일명·저장 위치 검사 | api/sources.py:29~38, ai/ingestion.py:16~24 |
| P1 | 권한 매핑 저장은 alert, 통계 화면은 Mock | 서버 권한 데이터·실측 usage 연결 전 모의 상태 표시 | frontend/src/pages/PermissionMap.jsx, Stats.jsx |

DB 초기화 코드에는 접속 정보의 코드 내 기본값이 확인된다. 재사용 시 이를 복제하지 않고 비밀 관리 설정으로 옮긴다. 값은 문서에 기록하지 않는다. 실제 배포 설정이나 자격증명의 유효성은 확인하지 않았다.

## RFP와의 관계

| RFP | 공통화 프로젝트 기여 | 남은 차이 |
|---|---|---|
| RAG-001 필수 | Prompt/컨텍스트 조립 경계 | 중앙 버전·승인·조직별 적용 |
| RAG-002 필수 | Chunk 처리·저장소 인터페이스 | 전략/임베딩 카탈로그·모델 버전 |
| RAG-003 필수 | ParserRegistry | 다형식/OCR·성능 검증 |
| RAG-004·005 필수 | Source/Adapter 계약 | 실제 저장·계열사/개인 격리 |
| RAG-007 필수 | 개체·관계·근거·Graph 검색 골격 | 영속화·정확한 관계 근거·업무 평가 |
| RAG-006·009·010 권고 | Hybrid/SearchTest 골격 | 리랭킹·비교 화면·색인 버전/전환 |
| AGB-001·002 필수 | 노드/Workflow 상태 계약 | Builder·복구·장기 실행 |
| ONM-002·005 필수 | 직접 모델 호출 구현 참고 | 중앙 G/W·미터링·계열사 원장/정산 |

GraphRAG의 역할은 관련 지식을 검색해 근거를 공급하는 것이다. Agent 사용승인·조직 권한·비용 한도는 플랫폼 정책 계층이 결정한다. 그래프의 관계만으로 운영 권한을 부여하지 않는다.

관련: [[개발/AI 통합 포털/05 BNK 플랫폼 기준 정정과 개인 MVP]], [[개발/AI 통합 포털/07 플랫폼 통합 작업과 검증 기준]].

## 주요 코드 근거

[시험 실행기](</Users/jwpios/antigravity/GraphRAG AI Agent/tools/run_tests.py:1>)

[pgvector 어댑터](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/vectorstores/pgvector_adapter.py:37>)

[Graph 검색·근거 조립](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/ai_pipeline/graphrag/hybrid_retriever.py:197>)

[모의 인증](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/auth.py:23>)

[업로드와 색인 트리거](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/api/sources.py:62>)

[백엔드 Graph 검색](</Users/jwpios/antigravity/GraphRAG AI Agent/backend/app/ai/retriever.py:58>)

[간단 Workflow](</Users/jwpios/antigravity/GraphRAG AI Agent/src/common_core/agents/workflow_factory.py:34>)
