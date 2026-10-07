# DP-06 DOCX 원본과 구조 위치 변경 영향 분석

기준 구현:00e31a5. [[12 DP-06 DOCX 본문과 표 수용 기준]], [[15 DP-06 DOCX 파서 확장 상세 작업 계획]].

| 영역 | 변경과 유지 |
|---|---|
| 문서 파서 | 별도 docx_worker가 제한된 ZIP/XML을 검사하고 text/locations/parser_version 반환. 기존 PDF 격리 실행/메모리 감시를 재사용한다. |
| 등록 | application/vnd.openxmlformats-officedocument.wordprocessingml.document 분기 추가. 기존024 lookup과 원본 기반 request digest 재사용; DB media=text/plain 유지. |
| 저장 | source_mapping.origin의 media 별 검증을 확장. DOCX 위치 검증은 전용 모듈로 분리하고 PDF origin 계약 유지. 원본 저장/삭제는 기존 공통 기능 재사용. |
| 검색/색인 | 기존 canonical UTF-8·GraphRAG·정책 재검사 유지. 모델이나 DB 봉인 객체에 구조 필드 추가 없음. |
| 근거/다운로드 | 현재 읽기 권한의 HTTP 응답에 structure_locations 추가. MIME/파일명은 검증된 origin에서 파생. |
| 화면 | .docx 선택과 미지원 안내, 문단/표 위치, 정확한 DOCX 형식 다운로드. TXT/PDF 이전 표시 유지. |
| DB | 새 테이블/SQL 불필요. 기존 migration000~024와96개 고정 함수 유지. |

표의 셀 텍스트를 평문으로 바꾸므로 서식·열 배치·셀 간 관계를 자동 추론하는 기능은 아니다. 셀 안의 기존 GraphRAG가 지원하는 문장만 질의 근거로 사용한다. 무조건 파일을 열고 일부 텍스트만 취하는 방식은 미지원 요소가 누락되므로 엄격한 부품/구조 검사를 먼저 수행한다.

XML은 공식 defusedxml0.7.1의 DTD/엔터티/외부 참조 금지 설정을 명시적으로 적용하고 실제 격리/자원 시험을 수행한다. 새 의존성은 공식 배포 SHA-256과 라이선스를 확인한다. [공식 설명](https://pypi.org/project/defusedxml/0.7.1/), [공식 구현](https://github.com/tiran/defusedxml/blob/main/defusedxml/ElementTree.py).
