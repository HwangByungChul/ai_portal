# DP-06 DOCX 격리 파서 상세 설계와 실행 계획

> **For agentic workers:** 사용자가 승인한15 계획을 이번 세션에서 순차로 직접 수행한다. 별도 에이전트 위임은 사용하지 않는다.

**Goal:** 제한된 DOCX 본문/표를 기존 개인·관리자 문서함과 GraphRAG에 연결한다.

**Architecture:** 별도 stdin/stdout 파서가 ZIP/OOXML 계약 및 구조를 검증하고 UTF-8 평문/구조 위치 맵을 반환한다. 기존 접수 권한·정책·원본 sidecar와 증거 봉인을 재사용하며 현재 읽기 권한의 조회에만 구조 위치를 추가한다.

**Tech Stack:** Python3.13 표준zipfile, defusedxml0.7.1, 기존 PDF macOS 격리 실행기, FastAPI/PostgreSQL/React/Playwright.

**Spec:** [[12 DP-06 DOCX 본문과 표 수용 기준]], [[05 DP-06 DOCX 원본과 구조 위치 변경 영향 분석]], 승인된 [[15 DP-06 DOCX 파서 확장 상세 작업 계획]].

## Global Constraints

원본128KB, 추출40,000자/128KB, ZIP200항목/해제4MB/부품1MB/압축률100, XML 깊이50/노드20,000, 비어 있지 않은 단위2,000. CPU2초/실행5초/RSS512MB 초과 감시(50ms; 하드 메모리 상한 아님). 격리/감시 불가 시 차단. 기존000~024 SQL·권한·원장·봉인 유지. 신규 유료 호출/배포 없음. 사용자 파일명은 경로 권한이 아님.

## Task 1: ZIP/XML 추출

Files: Create app/documents/docx.py, docx_worker.py, docx_locations.py, formats.py; tests/docx_support.py, test_docx_parser.py. Modify requirements.in/lock and third_party license.

Interfaces: extract_docx(raw:bytes) -> {text:str,locations:list,parser_version:'docx-v1+defusedxml-0.7.1'}. validate_docx_locations(locations,character_length) raises ValueError on invalid map.

- [ ] 정상 문단/빈 문단/표/한글과 위험 ZIP/XML의 실패 시험을 먼저 작성·실행한다.
```python
def test_document_order_and_locations():
    result = extract_docx(docx_fixture())
    assert result['locations'][0]['kind'] == 'paragraph'
    assert result['locations'][1]['kind'] == 'table_cell'
```
- [ ] 공식defusedxml0.7.1 배포 지문/라이선스를 보존하고 버전을 고정한다.
- [ ] ZIP을 디스크에 풀지 않고 bounded read로 부품을 검사한다. XML은 forbid_dtd/entities/external=True, 시작/종료 이벤트마다 깊이/노드 상한 적용.
- [ ] 허용 부품: [Content_Types].xml,_rels/.rels,word/document.xml,word/_rels/document.xml.rels,word/styles.xml,stylesWithEffects.xml,settings.xml,fontTable.xml,webSettings.xml,numbering.xml,word/theme/theme1.xml,docProps/core.xml,app.xml,custom.xml. 폴더 항목은 이 부품의 부모 폴더만 허용.
- [ ] 패키지 root 관계는 document/core/extended/custom-properties, 본문 관계는styles/stylesWithEffects/settings/fontTable/webSettings/numbering/theme만 허용. 정확한 namespace/type/상대 경로 대상·기존 부품과 대조; External·중복ID·누락/중복 main 관계 거부. Content Types도 알려진 Word 본문/서식/속성 타입만 허용.
- [ ] 본문은 paragraph/table/마지막 sectPr 순서. 문단은r/t/tab/br/cr 및서식, 표는중첩·병합 없는tr/tc/p만 추출. 미지원 의미 구조/다른 namespace는 거부한다. 서식의 hidden·자동 번호도 거부.
- [ ] 비어 있지 않은 문단/셀을두 줄바꿈으로 연결한다. 빈 문단도 paragraph 번호에 포함. 셀 안 문단은한 줄바꿈. locations는 paragraph(kind,paragraph,start,end) 또는table_cell(kind,table,row,column,start,end). 모든오프셋은Unicode 코드포인트,첫start0·다음start이전end+2·마지막end=text길이.
- [ ] 실제 DOCX 격리의 읽기/쓰기/네트워크/하위 실행·환경값 미전달과 자원 초과/장애를 시험한다.

## Task 2: 등록·원본·근거

Files: Modify upload.py, repository.py, storage.py, evidence_routes.py; Test test_docx_acceptance.py.

- [ ] 개인/관리자 원본·텍스트 지문, 확정 재접수 파서0, 차단 주체 파서0, 정책 차단 파일/작업/호출0 시험을 작성한다.
- [ ] metadata DOCX MIME/파일명/magic 검사 추가. repository는 기존lookup 뒤extract_docx를 격리 실행하고 원본SHA 기반digest/canonical text 정책을 유지.
- [ ] origin은 공통media_type/source_sha256/byte_length/parser_version/text_sha256와DOCX locations. PDF는기존pages만 허용. 구조 맵을 명시적으로 검증.
- [ ] evidence 조회에서 검증된locations와 기존start_offset/end_offset의교집합만 반환. 원문/경로/tenant 식별자를 새구조필드에 추가하지 않는다. download는현재ACL·canonical/원본SHA 확인후정확한DOCX MIME/document.docx 반환.
- [ ] DB·감사 실패의 원본/텍스트 비공개 잔여 파일과 동일ID 복구, 원본 변조/누락, 두파일 삭제/고아 정리를 검증한다.

## Task 3: 화면·회귀

Files: Modify frontend/src/DocumentsPage.tsx,types.ts,RagEvidencePanel.tsx,api.ts; Create tests/docx-acceptance.spec.ts and synthetic fixture; Modify safe-reporter.ts.

- [ ] 파일 선택/한글 미지원 안내·문단/표 위치·DOCX다운로드를 추가한다.
- [ ] 개인/관리자 DOCX→질문→문단/표 근거→원본 바이트, 타 사용자/타 조직·삭제/공유 회수 및정책 거부를 실제화면/API로 확인한다.
- [ ] 기존영향 서버와TXT/PDF 전체 화면 회귀·빌드를순차로실행한다. 주DB 변경없음·32개원본열/행보존 및000~024지문동일을 확인한다.

## Task 4: 결과·다음 XLSX 계획

- [ ] 250/260/280에 구현/시험결과·소스/배포 지문·정제JSON을실제사례수로기록한다. DP-06 DOCX묶음과남은Office/OCR을구분한다.
- [ ] 모의시연과비공개테스트계정을복구한다.
- [ ] 다음XLSX의시트/셀원본근거·수식/외부링크/매크로/숨김데이터처리계획을작성한다.

## 자체 검토

Office 전체를 한 번에 구현하지 않고DOCX의ZIP/XML 위험과문단/표 위치로한정했다. 미지원 요소를조용히누락하지않는다. 기존raw/source SHA와 봉인된 위치 의미를바꾸지 않는다. 15의승인범위 내에서구체값과함수/파일명을 확정했으며추가승인을요구하지않고직접수행한다.
