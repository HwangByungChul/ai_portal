# 일반 대화·중앙 AI의 B01 저장 기반 증거

2026-10-05 I250-B01 완료. B 전체는 진행중이고 다음은 B02다. 유료AI0회/0원. 백엔드238pass(기존176+신규62)/실패0/경고0/208.77초, 기존A 포털build/Chromium20pass/runner error0/28.21초다. 신규 대화/관리 화면이나 실제 AI를 검증한 결과가 아니다.

- B01-test-summary.json: 범위·현재버전·전체통과·정확소스SHA256·보존·미완료.
- B01-test-results.json: 실제238개 backend와20개 기존A browser의 정제ID/상태/시간. 예전 A01~06 횟수를 현재 합계에 다시 더하지 않는다.
- B01-db-boundaries.json: 기존 primary11개 업무행 보존/005추가·16업무/infra1/6migration/새5개 FORCE RLS·원시변경거부·web/meter 실제역할/옵션·현재ctx/owner/FK/이벤트·종료연결0.
- B01-runtime-check.json: 정확 pin/hash·공개registry/Python/wheel/import·SDK transport·오프라인 인코딩준비·실제정리. 비밀·DSN·세션·CSRF·개인본문·SQL bound values는 없다.

A-auth 증거는 A06 당시 결과로 보존한다. B01의 가격/토큰수는 보수 내부추정이다. 단가 snapshot은 price-20261004-v1, 10/05 공식 가격재확인 후 동일값을 유지했다. 모델이용권·실응답·청구금액을 확인한 것은 아니다. 원자 reserve/dispatch/settle·고정 meter 함수·cancel/lease/AI/SSE 검증은 B04 이후다. Job/Graph·문서Grant/전체V41/Q20은 후속이다.

재현: backend 전용환경에서 `.venv/bin/python -m scripts.prepare_tokenizers`, `.venv/bin/python -m pytest tests -q`; Node22.23.1의 frontend에서 `npm run build`, `npm run test:e2e -- tests/auth-tenants.spec.ts`. 준비 명령만 공개 BPE를 다운로드하며 runtime은 누락/변조 때 차단한다. 각 시험은 자기 marked DB를 정리하고 원래 정지 상태를 복원한다. 기존 active fixture는 seed/reset하지 않는다.

기존 httpx0.28.1 pin은 유지했다. SDK3.24.0이 요구하는 httpx2 2.13.1을 hash lock에 추가했고 Starlette TestClient가 이를 사용하면서 과거 A06 경고1은 현재 suite에서 발생하지 않았다. 경고를 숨기지 않았다. SDK transport 가짜시험은 B04에서 httpx2.MockTransport를 사용한다.

baseline_commit은 검증전 이력, tested_source_commit은 정확소스의 로컬commit이다. 소스지문을 대조하고 커밋 생성 후 후속 문서commit에서 SHA를 채운다. private 원본로그/JUnit/자격·토큰캐시는 Git에 넣지 않는다. 달력경과는 개인학습 실투입/잔여80h와 구분한다.

검증소스 로컬commit: `189f95a76ca09862903320ab86b03f87caf069cd`. 소스지문 대조 후 후속 문서commit에서 기록했다.
