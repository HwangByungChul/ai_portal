# C03 문서 등록·인덱싱 검증 증거

C03 등록/버전·Job/lease·중앙 임베딩 원장·벡터/checkpoint·게시/삭제 정리의 native DB 및 mock 검증이다. 실제 provider/검색/RAG/화면/Q20 완료 결과가 아니다.

- C03-test-summary.json: 전체·관련·기존 브라우저 회귀 집계. 관련 시험은 전체에 포함한다.
- C03-test-results.json: 실제 결과와 시험 식별자. 파라미터 값은 SHA로 대체한다.
- C03-db-boundaries.json: 추가 SQL·기존 행 보존·native 시작/재시작·정리 경계.
- C03-preservation.json: 기존 비밀 값·역사 증거·원본·데이터 보존. app.env는 기존 bytes를 유지하고 index 설정 2항목만 추가했다.
- C03-source-fingerprints.json: 실제 검증 소스 SHA 및 로컬 source commit.

개인 원문/인용/벡터/DSN/키/private 로그/XML은 공개 증거에 포함하지 않는다. Q20는 not_run이며 이전 증거 파일은 수정하지 않았다.

결과 [[14 문서 등록과 인덱싱 Job 구현 결과]], 다음 [[15 ACL 검색과 RAG 답변 상세 작업 계획]].
