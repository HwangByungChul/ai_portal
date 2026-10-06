# T280 잔여1~6 검토 증거

2026-10-06. 최종 실행 성공과 전체 요구 인수 판정을 구분합니다. 비공개 키/환경/로그는 포함하지 않습니다.

- `regression-cases.json`: 전체949 → 추가18 → 최종 retry추적 영향27의 시점/중복 구분.
- `browser-cases.json`: 전체64, 최종 문서9 재확인.
- `verification-matrix.json`, `verification-review.md`: 상세60/ACL16/V41 하위조건 개별 판정·미확인 이유.
- `actual-real-check.json`, `primary-postcheck.json`: 동일 primary 실제8회, receipt·원문·원장·재시작 대조. 실제Q20/전체성능과 구분.
- `static-audit.json`: SDK import/원문 저장소 범위.
- `failures-and-corrections.json`: 초기 실패·중단 및 수정.
- `source-fingerprints.json`: 최종 소스 SHA/소스 커밋; 전체949는 최종retry수정 이전 실행.
- `screens/`: 현재 로컬 Mock 화면6장. 직접 사용자 검토 아님.
- `preservation.json`, `public-secret-scan.json`, `result-manifest.json`: 보존·공개자료 검사와 결과 파일 SHA.

전체 인수는 조건부이며, 미확인 조합을 통과로 간주하지 않습니다. 원본 T280 이전 증거는 수정하지 않습니다.
