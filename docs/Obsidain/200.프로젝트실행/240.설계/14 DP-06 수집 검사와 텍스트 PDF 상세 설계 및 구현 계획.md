# DP-06 수집 검사와 텍스트 PDF 상세 설계 및 구현 계획

> **For agentic workers:** 승인된 이번 세션에서 아래 단위를 순서대로 직접 수행한다. 별도 에이전트 위임은 사용하지 않는다.

**Goal:** 최소 수집 검사와 텍스트 PDF의 원본/페이지 출처를 기존 개인·관리자 문서와 GraphRAG에 연결한다.

**Architecture:** 별도 파서 프로세스가 PDF를 제한된 텍스트/페이지 맵으로 변환한다. 기존 텍스트 저장·색인·증거 봉인을 재사용하고 원본은 불변 sidecar로 보관한다. 영수증·접수 창 확인은 파싱 전에, 정책·파일 저장·등록은 현재 권한 재확인 뒤 수행한다.

**Tech Stack:** Python3.13/FastAPI/기존 PostgreSQL RLS, pypdf6.19.0, macOS sandbox-exec, React/기존 Playwright.

**Spec:** [[11 DP-06 수집 검사와 텍스트 PDF 수용 기준]], [[04 DP-06 PDF 원본과 수집 검사 변경 영향 분석]], 승인된 [[13 DP-06 파일 파서 확장과 수집 검사 상세 작업 계획]].

## Global Constraints

- 원본128KB, 추출40,000자/128KB,20페이지, 펼친 페이지 스트림 합계4MB, 파서 CPU2초/벽시계5초, RSS512MB 초과 종료 감시.
- 파서 네트워크·임의 쓰기·비밀 파일 읽기 차단. 격리 불가 시 PDF 거절. 파서 환경에 AI/PG/인증 값을 전달하지 않는다.
- 정책 버전 document-ingest-v1. NFKC 정규화 후 형식 문자 제거; 주민번호(구분자형/연속13자리), 국내 모바일/국제82 표기 전화, 이메일, 계좌/계좌번호/account 라벨 뒤10~22자리 숫자, 명시적인 기존 지시 무시/시스템 비밀 노출 지시를 차단한다. 진위·유효성 검사가 아니라 후보 탐지다.
- policy 결과는 allow/block·규칙 ID만 반환하고 검출 문자열·위치를 오류/감사에 기록하지 않는다. 정책 함수 오류는503, 탐지 차단은422, PDF 실패는 안전한422 코드, 격리 불가503.
- source_mapping.origin은 원본 format/hash/bytes, parser_version, text_sha256, pages(page/start/end)만 저장한다. 경로는 서버의 tenant/document/version에서 결정한다.
- 봉인된 답변의 location_snapshot은 기존 텍스트 오프셋/행으로 유지한다. GET evidence에서 불변 페이지 맵을 대조해 page_start/page_end를 추가한다.
- 원본·추출물 모두 무결성 검사. 삭제/확인된 orphan은 둘 다 제거한다. 기존 원장·감사·실행 식별자 유지.
- PDF 폼/첨부/자동실행/JavaScript/URI·외부 링크/암호/손상/비텍스트 페이지는 미지원. DOCX/XLSX/PPTX/OCR/HWP/URL은 후속.
- 기존000~023을 수정하지 않고024에 영수증 조회·파싱 전 접수 창 고정 함수 하나만 추가한다. 기존32개 테이블/95개 함수에 테이블 추가 없이96개 함수가 된다.
- 실 모델/유료 호출과 운영 배포를 수행하지 않는다.

## Task 1: 선행 문서 검사

Files: Create app/policies/document_ingest.py; tests/test_ingest_policy.py.

Interfaces: evaluate_document_policy(text:str) -> PolicyDecision(action,rule_ids,revision). require_document_policy(text:str) -> None; 차단/오류는 AppError.

- [ ] 주민번호/전화/이메일/라벨 계좌/명시 지시의 합성 양성·정상 음성·마스킹/분할 표현 미탐 시험을 작성한다.
```python
def test_email_candidate_blocks():
    assert evaluate_document_policy('가상 담당 synthetic@example.invalid').action == 'block'
```
- [ ] 새 모듈 부재의 실패를 확인한다.
- [ ] 정규화와 고정 규칙을 구현하고 matched 문자열 없이 규칙 ID만 반환한다.
- [ ] 모듈 시험을 통과하고 TP/FP/FN 한계를 기록한다.

## Task 2: 제한된 PDF 파서

Files: Create app/documents/pdf.py, app/documents/pdf_worker.py; Modify requirements.in/requirements.lock; Test tests/test_pdf_parser.py, tests/test_pdf_boundaries.py, tests/pdf_support.py.

Interfaces: extract_pdf(raw:bytes) -> dict(text,pages,parser_version). 등록 계층에서 canonical content/media_type/origin을 구성한다. PDF child는 stdin 원본, stdout 제한 JSON(text,pages,parser_version)을 사용한다.

- [ ] 정상2페이지/빈 페이지/암호/손상/첨부/JavaScript/잘못된 시그니처/페이지 초과 시험을 작성한다.
```python
def test_pdf_text_maps_pages():
    parsed = extract_pdf(pdf_fixture())
    assert parsed['pages'][0]['page'] == 1
    assert parsed['text']
```
- [ ] pypdf의 공식 wheel 지문과 BSD 라이선스를 기록하고 고정 의존성을 설치한다.
- [ ] stdin/출력 크기·CPU/메모리/시간·네트워크/파일 격리를 구현한다. PDF 객체의 위험 기능과 스트림 크기를 검사하고 텍스트가 없는 페이지를 거절한다.
- [ ] 격리 자체의 네트워크·비밀 읽기·쓰기 차단과 자원 초과를 별도 시험한다.

## Task 3: 파싱 전 권한/영수증과 저장

Files: Create migrations/024_document_intake_lookup.sql; Modify app/documents/repository.py, upload.py, storage.py; Test tests/test_dp06_acceptance.py, support.py, test_migrations.py.

Interfaces: document_upload_lookup(session,tenant,client,hash,document,expected,personal,window,request) -> {new_upload,allowed,retry_after} 또는 기존 receipt. 기존 고정 register/preflight를 최종 커밋에 재사용한다.

- [ ] 확정 동일 접수의 parser 재실행0, 다른 원본409, 권한 위조/상실, 정책 차단 시 파일·작업·호출0을 시험한다.
- [ ] lookup 함수는 개인/관리자 preflight·접수 창·감사 계약을 재사용하며 PUBLIC EXECUTE와 직접 쓰기를 금지한다.
- [ ] canonical source와 original 두 파일을 불변 저장한다. original 지문/길이/페이지 맵을 source_mapping.origin에 넣고 원본 지문으로 요청 해시를 계산한다.
- [ ] DB 실패의 원문 비공개 orphan, 재접수 복구, 두 파일 idempotent 정리를 확인한다.

## Task 4: 색인·페이지 근거·원본 다운로드

Files: Modify app/documents/worker.py, search.py, evidence_routes.py; Test tests/test_dp06_acceptance.py.

Interfaces: StoredSource에 optional source_mapping을 전달한다. storage.read는 canonical과 origin 무결성을 검사하고 read_original은 권한 확인 후 원본 바이트를 반환한다. evidence의 source_media_type/page_start/page_end는 서버 파생 값이다.

- [ ] 정상 PDF 업로드→색인→규정 질문→인용·페이지→원본 바이트/지문 일치를 시험한다.
- [ ] worker 색인 전 정책·원본 무결성 검사를 추가하고 retrieval용 원문에서도 현재 정책을 재확인한다.
- [ ] 타인/타 조직/회수/삭제에서 질문·근거·원문·평가가 차단되는지, 사용량/봉인 기록이 유지되는지 확인한다.
- [ ] TXT/Markdown 증거 봉인·다운로드 형식은 그대로 동작하는지 확인한다.

## Task 5: 화면과 통합 검증

Files: Modify frontend/src/DocumentsPage.tsx, types.ts, RagEvidencePanel.tsx, api.ts; Create frontend/tests/dp06-acceptance.spec.ts.

- [ ] 업로드 선택에 .pdf를 추가하고 제한·미지원 OCR·안전한 실패를 한국어로 표시한다.
- [ ] 페이지 근거와 document.pdf 다운로드를 연결한다.
- [ ] 실제 브라우저의 개인·관리자 PDF·정책 거절·모바일·조직 전환·중복 접수를 시험한다.
- [ ] 새 서버 시험과 기존 문서/정책/복구/사용량/RAG/대화/평가 영향 회귀 및 전체 화면 시험·빌드를 순차 실행한다.

## Task 6: 보존·결과·후속 계획

- [ ] 소유 주 DB의 기존32개 테이블 원본 열/행 SHA-256을 비교하면서024만 적용한다.
- [ ] 지정250/260/280 폴더에 구현/모듈/통합 결과·소스 지문·정제 증거와 정책 TP/FP/FN을 기록한다.
- [ ] 별도 모의 시연 화면과 비공개 계정 파일을 복구한다.
- [ ] DP-06 P0/P1/P3의 텍스트 PDF 범위와 DP-18 문서 수집 최소 범위만 완료 표시한다. 다음 P2의 DOCX 상세 계획을 기록한다.

## 자체 검토

기존 PDF 원본을 source로 대체하면 텍스트 DB·봉인 계약이 깨지므로 두 파일로 분리했다. 페이지 정보를 모델의 봉인 객체에 추가하지 않고 검증된 불변 맵으로 HTTP 응답에서 파생한다. 같은 접수의 CPU 비용과 파서 접근 권한은 파싱 전 lookup으로 통제한다. 수집 차단은 보관/송신 전에 적용하고, 후속 Office와 일반 대화 정책은 이번 완료 범위와 분리했다. 승인된13 계획을 구체화한 동일 범위로 직접 수행한다.


## 구현 중 확인한 자원 제한 보정

macOS Python 런타임은 계획했던 `RLIMIT_AS(512MB)` 설정을 `ValueError`로 거부했다. CPU2초/시간5초를 유지하고 부모 프로세스가 50ms 간격으로 실제 RSS를 조회하여512MB 초과 시 종료하는 감시로 구현했다. 감시 실패도 종료·차단한다. 이 수치는 종료 기준이며 순간 초과까지 금지하는 하드 메모리 상한이 아니다. 실제 자식 종료와 감시 장애 시험 및 운영체제의 프로젝트 읽기·쓰기·통신·하위 실행 차단 시험으로 확인했다. 상세 인터페이스는 `extract_pdf(raw) -> {text,pages,parser_version}`이며 등록 계층이 canonical 원문/원본 지문을 구성한다.

## 실행 결과 연결

첫 묶음의 구현·모의 검증 결과를 [[11 DP-06 텍스트 PDF와 최소 수집 검사 구현 결과]], [[04 DP-06 텍스트 PDF와 수집 검사 모듈 시험 결과]], [[17 DP-06 텍스트 PDF와 수집 검사 검증 및 후속 작업]]에 기록했다. 계획 항목의 검증 범위와 실제 사례 수는 해당 결과와 공개 증거를 기준으로 한다. 기존 공통 등록/감사 실패 회귀와 PDF 원본/텍스트 및 고아 정리 시험을 포함했으며, 새 화면 시험은 PDF 질문/페이지/다운로드/권한/삭제·수집 거부·관리자 접수에 집중했다. 모바일·조직 전환·유실 재접수는 기존 전체 화면 회귀에서 확인했다.
