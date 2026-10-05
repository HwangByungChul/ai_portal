---
title: GraphRAG 순수 코어와 문서 처리 상세 작업 계획
created: 2026-10-05
updated: 2026-10-05
status: completed
stage: 250.구현
tags: [implementation-plan, C02, graphrag, provenance]
---

# I250-C02 GraphRAG 순수 코어와 문서 처리

**Goal:** 등록 원문만으로 위치를 보존한 청크·근거·규칙 Graph·임베딩 배치 계획을 생성한다. 기존 GraphRAG의 처리 구조를 선택 활용해 개인 MVP의 공통 코어로 정리한다.

**Architecture:** `src/common_core`는 원문과 등록 metadata, 고정 규칙, 토큰 계산기를 입력받는 순수 처리 모듈이다. backend는 C01의 현재 권한/비공개 저장 경계를 유지하며 처리 계획을 연결한다. DB 권한, API 키, provider 호출과 과금은 공통 코어에 넣지 않는다.

**Tech Stack:** 기존 Python 3.13/Pydantic/tiktoken, UTF-8 TXT·Markdown, 고정 `cl100k_base` 임베딩 토큰 계산. 설치된 패키지를 우선 사용한다.

**Spec:** [[06 문서와 GraphRAG 설계]], [[03 데이터 모델과 RLS 설계]], [[09 문서와 GraphRAG 연결 상세 작업 계획]], [[10 문서와 GraphRAG 저장 기반 구현 결과]].

## 전제·범위·일정

- C01 시험과 기본 DB 적용 결과를 확인한 후 시작한다. 사용자의 다음 작업 진행 승인에 따라 C02를 순차 실행한다.
- 기존 C 배정 20시간 중 C02의 **예상 3시간**을 세분화한 계획이다. 실제 개인 학습·개발 투입 시간은 미측정이다. 10월 31일 목표와 주 20시간 이상 조건은 유지한다.
- 실제 임베딩/DB 색인/등록 API/Job 실행/검색 답변/새 화면은 C03~C05에서 연결한다. C02의 파싱 시험 통과만으로 Q20 또는 전체 MVP 완료를 선언하지 않는다.
- 실제 AI 호출 0회·추가 비용 0원으로 진행한다. 기본 대화·예산·등록된 키·기존 SQL·합성 평가 원본을 보존한다.
- 평가 정답/질문별 required·forbidden/R·EV 목록을 runtime에 입력하지 않는다. 평가는 원문에서 만든 실제 산출물과 별도로 대조한다.
- 원본 `GraphRAG AI Agent`의 소스는 읽기만 한다. 기존 프로젝트 전체 복사나 별도 서버 기동 없이 필요한 책임을 선택 이관한다.

## 작업 1 — 재사용 범위와 입력 계약 (예상 25분)

Files:
`src/common_core/README.md`, `provenance.json`, `__init__.py`, `ai_pipeline/__init__.py`, `document/schemas.py`, `graphrag/schemas.py`.

- [x] 원본 HEAD `913f3881b4a4a73b9f764f60575775ecdbba6bdd` 및 B06의 9개 검토 소스 지문을 다시 대조한다. 작업 중 기존 변경은 보존한다.
- [x] DocumentPipeline/ParserRegistry/Chunker/Graph schema/RelationExtractor의 책임을 새 모듈별로 매핑한다. “동일 코드 복사”, “구조 참고 후 보완”, “새 구현”을 provenance에서 구분한다.
- [x] 라이선스/저작권 표기의 실제 존재 여부를 기록한다. 명시되지 않은 라이선스를 임의로 만들어 표시하지 않는다.
- [x] tenant/document/version/index UUID, source SHA, parser/pipeline revision과 실행 mode를 갖는 불변 입력/결과 모델을 정의한다. 이름·본문의 PERSON 값은 사용자 권한 UUID와 구분한다.
- [x] 청크/근거/개체/관계는 index 범위의 안정적인 local ordinal을 갖는다. 최종 DB UUID를 임의 재생성해 중복 저장하는 책임을 순수 코어에 넣지 않는다.

완료 기준: 코어 import에 네트워크/DB/키가 필요하지 않고, 원문·등록 metadata·고정 규칙 외 평가 파일 입력 경로가 없다.

## 작업 2 — 파싱과 원문 위치 mapping (예상 40분)

Files:
`document/parser.py`, `mapping.py`, `pipeline.py`;
`src/backend/tests/test_document_mapping.py`.

Interface: `parse_source(raw_bytes, media_type) -> ParsedSource`.
`ParsedSource`는 원본 Unicode 문자열/바이트 SHA, 파생 텍스트, 각 파생 구간의 원본 offset/행 mapping을 보존한다.

- [x] C01의 UTF-8/128KiB/40,000자/NUL 제한을 같은 입력 경계에서 확인한다.
- [x] BOM/CRLF 처리를 하면서 원본 문자열 기준 codepoint offset과 행 번호를 보존한다. 반복 문장은 `find()` 추측으로 위치를 정하지 않는다.
- [x] 시작 frontmatter·합성 고지·HTML anchor·EV marker ID를 처리 텍스트에서 제외한다. heading의 실제 업무 문구는 보존한다.
- [x] 제한 Markdown 문법 제거로 비연속 원문 조각을 합친 경우, 하나의 exact quote라고 주장하지 않는다. 원문에서 연속인 구간만 인용 근거로 만든다.
- [x] CRLF/BOM/반복 문장/한글·emoji/heading·marker·빈 문서/오프셋 경계 시험을 작성한다.

완료 기준: 모든 근거 `raw_text[start:end] == exact_quote`, 원본 SHA/행 번호 대조 통과. 불가능한 mapping은 오류로 처리한다.

## 작업 3 — 토큰 청킹·근거·배치 계획 (예상 35분)

Files:
`document/chunker.py`, `graphrag/evidence.py`;
`src/backend/app/documents/plan.py`, `tests/test_document_plan.py`.

Interface: `build_document_plan(source, metadata, tokenizer) -> DocumentPlan`.
계획은 청크/근거/Graph/coverage, 예상 배치와 fingerprint만 반환한다. 실제 DB 저장·provider 호출은 하지 않는다.

- [x] 문단/문장 경계를 우선해 청크를 **512토큰 이하, overlap 0**으로 구성한다. 기존 원본의 1000문자/100문자 overlap 가정을 이식하지 않는다.
- [x] 긴 문장은 Unicode 문자 경계에서 분할한다. 잘린 주장 조각으로 완전한 관계를 확정하지 않는다.
- [x] 128청크/512근거/512개체/1024관계/2048관계-근거 연결을 사전 검사한다. 초과는 `INDEX_LIMIT_EXCEEDED`이며 일부만 잘라 성공 처리하지 않는다.
- [x] 청크 8개·4096토큰 이하/최대 16배치의 deterministic 배치 계획을 만든다. source/pipeline/mode/배치 ordinal·실제 텍스트·모델/차원을 fingerprint에 바인딩한다.
- [x] 크기 경계/긴 문장/반복문/상한 초과/같은 입력의 동일 계획/다른 mode 재사용 금지를 시험한다.

완료 기준: 유효하지 않은 계획은 provider 호출 전 거부되며, 테스트용 호출 spy가 항상 0임을 확인한다.

## 작업 4 — GR01~10 제한 규칙 Graph (예상 45분)

Files:
`graphrag/extractor.py`, `context.py`, `schemas.py`;
`src/backend/tests/test_graph_extraction.py`, `test_graph_evidence.py`.

Interface: `extract_graph(parsed_source, chunks, evidence, fixed_schema) -> GraphPlan`.

| 규칙 | 관계 | 시험의 핵심 |
|---|---|---|
| GR01/02/03 | 담당부서/위험검토승인부서/기록보관담당부서 | 구체 문형 우선, 서로 다른 책임과 근거를 구분 |
| GR04/05 | 보관기간/필수점검표 | 숫자·단위·조건·시점을 원문대로 보존 |
| GR06/07 | 팀의 누락점검일/개인 리허설 일정 | 명시적 책임 근거 연결, PERSON을 권한 계정으로 해석하지 않음 |
| GR08/09 | 접수담당/접수확인기한 | PROCESS→TEAM→DURATION 방향, 상대 시작점·“이내” 보존 |
| GR10 | 복구목표 | 승인된 작은 도메인 alias만 사용, 원문에 없는 값 생성 금지 |

- [x] PROCESS/TEAM/ARTIFACT/DURATION/SCHEDULE/PERSON 6유형과 승인된 관계 방향을 구현한다.
- [x] alias에는 업무 명칭만 넣고 팀·기한·정답 relation/EV 값은 넣지 않는다. 원 소유 tenant별 semantic key를 만들되 실제 개체는 index별로 분리한다.
- [x] 문장 전체의 긍정 선언을 확인한다. 부정/예외/조건 불명/대명사 불명/양립 불가 복수 값은 관계를 만들지 않고 partial 이유를 남긴다.
- [x] 각 관계는 자신을 뒷받침하는 연속 exact quote만 연결한다. 같은 업무의 다른 승인/보관 근거 전체를 붙이지 않는다.
- [x] index/from/predicate/to/조건/원문 구간 기준 dedup과 evidence 연결을 확인한다. 다른 조직·index의 양 끝 개체/근거는 계획 검증에서 거부한다.
- [x] 미지원 문장은 원문 청크·근거로 남기고 Graph coverage를 partial로 표시한다. 원문에 없는 답을 보완하지 않는다.

완료 기준: GR01~10 긍정/부정/잘린 문장/근거 교차/alias/조건/조직·index 혼입 시험 통과. 실제 합성 원문 산출물과 평가 기대값은 시험 단계에서만 비교한다.

## 작업 5 — 검증과 C03 인계 (예상 35분)

Files:
`250.구현/12 GraphRAG 순수 코어와 문서 처리 구현 결과.md`, `260.테스트/evidence/C-rag/C02-*.json`, 진행 대장.

- [x] 관련 순수 코어 시험을 먼저 실행하고 C01/기존 backend 회귀 영향에 맞춰 확인한다. frontend 변경이 없으면 불필요한 반복 시험은 피한다.
- [x] 합성 7개 원문 버전의 byte SHA→실제 청크/근거/Graph/배치 fingerprint를 생성해 기록한다. 평가 정답 파일은 runtime과 분리한다.
- [x] 실제 DB 저장/임베딩이 없음을 결과에 명시한다. Q20 실행 상태는 실제 검색·RAG 검증 전까지 not_run으로 유지한다.
- [x] 기존 source/문서·예산·키/원본 프로젝트 보존, 유료 0회, 정확한 변경 파일과 소스 지문을 점검한다.
- [x] 다음 C03의 등록 receipt/원문 orphan 보상/Job claim·lease·epoch/중앙 임베딩/비용 예약·정산/벡터 checkpoint·게시/cleanup 상세 계획을 결과와 함께 보고한다.

실행 순서: 입력 모델 → mapping → 청킹/배치 → 규칙 Graph → 원문 구간 검증 → 회귀/산출물 → C03 상세 계획. 현재 채팅에서 순차 수행한다.


## C02 실행 보완

- 코어는 표준 라이브러리의 불변 dataclass/tuple을 사용하고 토큰 계산기는 backend의 기존 오프라인 `count_embedding_tokens`를 주입한다. 코어 자체에서 tokenizer 파일·DB·네트워크·키를 읽지 않는다.
- backend pytest의 module path에 src를 추가한다. native 서비스의 코어 경로 설정은 C03에서 등록/Job 연결 시 적용하며, 이 단계에서 서버 경로나 비공개 설정을 변경하지 않는다.
- 먼저 원문 위치/규칙/계획 시험을 작성해 import 실패를 확인한다. 입력모델→mapping/파싱→청킹/근거→Graph/검증→backend 계획 adapter 순서로 구현한 뒤 동일 시험을 실행한다.
- 원문 근거가 비연속이면 여러 연속 구간으로 분리하고 관계를 확정하지 않는다. 잘린 문장·heading·code fence는 관계 확정 근거로 쓰지 않는다. 조건/부정/충돌·미지원은 partial로 남긴다.
- 원문 7버전의 실제 산출물과 평가자의 R/EV는 오프라인 시험에서만 대조한다. 공개 증거에는 원문·비공개 제목·label/quote를 넣지 않고 ID/수량/해시/시험 결과만 기록한다.

## 최종 결과

관련72개와 전체 backend 회귀 통과. 실제 구현·원문7버전 평가 대조·제약과 다음 C03 계획은 [[12 GraphRAG 순수 코어와 문서 처리 구현 결과]]에 기록한다.
