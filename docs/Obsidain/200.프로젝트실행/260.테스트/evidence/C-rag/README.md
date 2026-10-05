# C 문서·GraphRAG 검증 증거

| 작업 | 상태 | 범위 |
|---|---|---|
| C01 | pass | 문서/버전/공유·현재 권한/비공개 원문/실제 pgvector 저장 기반 |
| C02 | planned | 순수 파싱·원문 위치·청킹·규칙 Graph |
| C03~C06 | planned | 등록·Job·실 임베딩·검색·RAG·화면·실제 Q20 |

- `C01-test-summary.json`: 집계와 실제 검증 소스 SHA256. full과 targeted는 중복 집계하지 않는다.
- `C01-test-results.json`: 전체/관련 시험 및 브라우저 결과. 파라미터 원문은 공개하지 않고 구분 SHA만 남긴다.
- `C01-db-boundaries.json`: 기본 환경 신규 적용·기존 행 보존·권한/파일 경계·정리 결과.
- `C01-installation.json`: 공식 확장 버전/소스 commit/추가한 3파일과 해시, native PostgreSQL 15/SDK 빌드 조건.

기존 A/B 증거 파일은 그대로 유지한다. 원본/키/비밀번호/DSN/본문/private 로그는 공개 산출물에 넣지 않는다. 이번 단계 유료 호출 0회이며 기존 내부 실제 호출 집계 0.19원은 공급자 청구 확인값이 아니다. 브라우저 회귀는 native HTTP/DB와 mock provider로 수행한다. Q20과 전체 MVP는 아직 미완료다.

결과 [[10 문서와 GraphRAG 저장 기반 구현 결과]], 다음 [[11 GraphRAG 순수 코어와 문서 처리 상세 작업 계획]].
