---
title: DP-06 XLSX 원본과 셀 위치 변경 영향 분석
tags: [AI플랫폼, DP-06, 분석]
status: analyzed
---
# DP-06 XLSX 원본과 셀 위치 변경 영향 분석

[[13 DP-06 XLSX 시트와 셀 수용 기준]]을 기준으로 현재 PDF/DOCX 구조를 재사용한다.

| 영역 | 변경과 보존 |
|---|---|
| 파서 | XLSX worker/호출 경계/위치 검증 추가; DOCX 허용 부품과 PDF 계약은 그대로 유지 |
| 접수 | MIME·xlsx·ZIP magic 추가; 기존 권한/재접수/제한 이후 파싱 |
| 원본 | source_mapping.origin의 XLSX 명시적 분기; canonical DB는text/plain 유지 |
| 위치 | XLSX sheet/cell 단위 검증, 조회 응답만구조 출처 추가; FactPacket/location_snapshot 변경 없음 |
| 저장/복구 | 현재 original/source 두 SHA 및0600/삭제/고아 정리 재사용 |
| 화면 | 시트명·셀 주소 및지원 제한 안내; TXT/PDF/DOCX 내려받기 유지 |
| DB | 새 SQL 없음;000~024/25개 SQL/96개 보안함수 유지 |

ZIP은 디스크로 펼치지 않고 부품·관계·타입을 먼저 확인한다. 허용 경로는 workbook/worksheet1~10/styles/sharedStrings/theme1 및 core/app 속성·두 관계파일·Content_Types다. 모든 worksheet가 워크북의 고유 관계로 연결돼야 한다. 추가 부품·외부 관계·관계 누락·중복·잘못된 타입은 거부한다. XML 전체를 DTD/엔터티 금지 및 합산 한도로 읽고, semantic 부품은 명시적 구조로 검증한다.

숫자는 원래 값 문자열을 보존하므로 Excel 화면의 반올림/천단위/화폐 모양을 재현하지 않는다. 날짜 직렬수는 기본 서식의 일반 숫자로 저장된 경우 일반 숫자이며 날짜로 추정하지 않는다. 날짜 서식이 붙으면 거부한다. 빈 시트도 이름을 수집 검사에 포함한다. 서식/메타데이터 전체의 개인정보 탐지나 범용 공격 탐지 완성은 주장하지 않는다.

대안은 범용 openpyxl 추가, Excel 실행 변환, 현재 표준ZIP+defusedxml 격리 구현이다. 범용 라이브러리는 호환 범위가 넓지만 지원하지 않는 구조를 별도 검출해야 하고 의존성이 늘어난다. Excel 실행은 설치/자동 실행/재현성 부담이 있다. 승인된 제한 범위와 비용0 원칙에 맞춰 현재 의존성만 사용하는 격리 파서를 채택한다. 구조 허용 목록은 DOCX와 독립적이다.

공식 근거: [셀 유형/inlineStr](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.cell), [숫자 서식과 날짜](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.numberingformat). 셀 값과 화면 서식의 차이를 고려한 프로젝트의 보수적 설계다.
