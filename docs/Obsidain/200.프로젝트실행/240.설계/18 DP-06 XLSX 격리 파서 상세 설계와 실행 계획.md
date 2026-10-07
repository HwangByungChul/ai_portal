---
title: DP-06 XLSX 격리 파서 상세 설계와 실행 계획
tags: [AI플랫폼, DP-06, 설계]
status: approved_plan_concretized
---
# DP-06 XLSX 격리 파서 상세 설계와 실행 계획

> **For agentic workers:** 사용자가 승인한17 계획을 현재 세션에서 단계별로 직접 수행한다. 별도 에이전트 위임은 하지 않는다.

**Goal:** 제한된 XLSX 시트/셀을 개인·관리자 문서함과 GraphRAG에 연결한다.

**Architecture:** 별도 stdin/stdout worker가 OOXML ZIP/XML·의미·자원 한도를 확인하고 canonical 및시트/셀 위치를 반환한다. 기존 권한·정책·원본 보관·검색·다운로드를 재사용한다. 현재 조회 응답만 시트/셀 정보를 추가한다.

**Tech Stack:** Python3.13 표준zipfile/defusedxml0.7.1, 기존 macOS 격리 실행기, FastAPI/PostgreSQL/React/Playwright. 새 의존성 없음.

**Spec:** [[13 DP-06 XLSX 시트와 셀 수용 기준]], [[06 DP-06 XLSX 원본과 셀 위치 변경 영향 분석]], 승인된 [[17 DP-06 XLSX 파서 확장 상세 작업 계획]].

## Global Constraints

원본131072바이트·canonical40000자/131072바이트. 시트10·셀2000·sharedStrings10000·ZIP200부품/각1048576바이트/합계4194304바이트/압축비100. XML 깊이50·합산20000노드. CPU2초/실행5초·RSS512MB 종료 감시50ms(하드 상한 아님). SQL000~024·sealed location·현재 권한/회수/재접수 계약 유지. 유료 호출0·합성 데이터·비밀 환경 미전달·실패 시 차단.

## Task 1 파서와 위치 — 250/260

Create: app/documents/xlsx_worker.py,xlsx.py,xlsx_locations.py; tests/xlsx_support.py,test_xlsx_parser.py. Modify: formats.py.

Consumes: raw bytes. Produces: `extract_xlsx(raw) -> {text:str,locations:list,parser_version:str}`; `validate_xlsx_locations(locations,character_length)`가 부정확한 맵에ValueError. 버전xlsx-v1+defusedxml-0.7.1.

- [ ] 합성 자료와 실패 시험을 먼저 작성한다. 정상inlineStr/sharedStrings/숫자/불리언/ISO날짜·실제 셀 주소, 미지원 수식/숨김/병합/외부 링크·압축/XML 경계를 확인한다.
- [ ] `.venv/bin/python -m pytest -q tests/test_xlsx_parser.py`를 실행해 파서 미구현 실패를 확인한다.
- [ ] worker를 구현한다. zipfile에서 항목 안전성과 전개 한도를 검증하고, defusedxml.iterparse의forbid_dtd/entities/external=True 및 합산노드를 적용한다. 타입/관계/워크북/시트/문자열/숫자서식을 명시적 분기로 확인한다.
- [ ] 예시 기대값: 이름규정, A1값합성문서 → text=`시트: 규정\n\n셀 A1: 합성문서`; loc0kind=sheet, loc1kind=cell/cell=A1. JSON의원문/예외를 오류에 노출하지 않는다.
- [ ] 기존sandbox_command(xlsx_worker경로)/run_isolated를 사용한다. 검증된 DOCX 호출기 구조를 형식별로 확장하고 모든PDF실행기 오류를 XLSX안전코드로 변환한다.
- [ ] 동일시험을실행해통과확인한다. 실제worker경로의읽기/쓰기/통신/하위실행차단시험을포함한다.

## Task 2 접수·보관·근거·화면 — 250/260

Modify: upload.py,repository.py,storage.py,evidence_routes.py,errors.py; frontend/src/types.ts,api.ts,DocumentsPage.tsx,RagEvidencePanel.tsx. Create: tests/test_xlsx_acceptance.py; frontend/tests/xlsx-acceptance.spec.ts 및합성fixtures.

Consumes: Task1추출계약. Produces: 불변origin{media_type,source_sha256,byte_length,parser_version,text_sha256,locations};HTTPstructure_locations는start/end없이sheet/cell키만반환. download=document.xlsx/정확한MIME.

- [ ] TXT/PDF/DOCX와동일하게수집정책/현재권한/재접수/최종CAS/두지문검증을연결한다. XLSX에는validate_xlsx_locations만호출하고기존DOCX/PDF분기를유지한다.
- [ ] 제목/빈시트이름/셀개인정보후보는보관·작업·호출전차단한다. 확정재접수는파서0회, 동시최초요청은한파일쌍/한작업, 감사실패후동일ID복구를시험한다.
- [ ] 개인/관리자원본바이트, 지정버전공유/회수, 다른사용자/조직차단, 파싱중권한회수, 원본/맵변조와삭제정리를시험한다.
- [ ] 화면파일선택·한글지원제한·시트/셀근거·정확한원본파일명과MIME를연결한다. 신규화면3개를먼저통과시킨다.

## Task 3 최종회귀·산출물 — 280

- [ ] 변경영향서버범위와신규시험을순차검증하고수집목록으로고유사례수를확인한다. DBfixture와화면시험은동시에실행하지않는다.
- [ ] 화면타입/빌드 및전체브라우저회귀를통과시킨다. 기존로그인이미지두개만시험전저장본으로복원한다.
- [ ] 기존주DB32개테이블원본열/행해시와000~024SQL지문보존·새SQL0개를확인한다. 초기화/재시딩금지.
- [ ] 구현/모듈/통합결과와소스/의존성지문·정확한시험수·호출0공개JSON을작성한다. 전체프로젝트완료로확대하지않는다.
- [ ] 기존소유모의시연프로세스만교체해5173화면을복구하고0600비공개로그인파일을유지한다. 다음PPTX계획을작성한다.

자체검토: 요구범위/위치키/오프셋·한도·번호와본문설계일치. 수식/서식/빈시트이름을무시하는우회없음. 새라이브러리·SQL불필요. 승인된진행범위를구체화하며별도기능확장없음.
