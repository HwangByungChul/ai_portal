# 일반 대화·중앙 AI의 단계별 구현 증거

현재 I250-B01~05 완료/B 전체 진행 중·다음 B06이다. backend477 pass/실패0/경고0/466.24초, build 성공·기존A20+새B31=browser51 pass/runner0/117.06초·유료AI0회/0원이다. 사용자/관리자 화면과 기본 A/B 모의 시연 준비까지 확인했다. 기존 키/인증·대화·real 예산을 보존했고 준비 재실행 변경0이다. 실제 모델/Graph/Q20은 후속이다. B05-test-summary/results/db-boundaries/runtime-check.json이 현재 증거이며 아래 B01~04 서술은 각 단계 당시 이력이다.

## B01 당시 증거


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

## B02 운영 API 검증 — 2026-10-05

B01 JSON은당시기록으로보존한다. B02-test-summary/results/db-boundaries/runtime-check 4개에11개운영API/5추가SECDEF함수/현재권한·고정scope·한도·usage·CAS/audit·실동시경합을기록했다. 전체322pass(기존238+신규84)/실패0/경고0/300.79초,build/기존A브라우저20pass/runner error0/28.78초다. NativeHTTP11경로·재시작은84안의1개시험이며추가11시험으로합산하지않는다.

기존primary16업무행·app.env/이전000~005/합성9파일을보존하고006만추가/반복checksum적용[]·21fixedsecurity함수·8FORCE RLS/연결·임시DB0/서버정지다. 조직예산의초기12,500원/Agent활성화는새합성시험DB에서만수행했다. 미배정primaryusage/budget503은준비불가를숨기지않는계약이다. 예산초기화/실원장삭제나실AI호출은없다.

현재web의Agent settings 직접SELECT는없으며관리API만지침을반환한다. policy executor는허용scope의비용metadata/설정만읽고message.body/run.config_snapshot/call.claim은읽지못한다. 원장raw쓰기없음,사용량불명은예약·unknown분리다. 실제reserve/dispatch/settle·provider·SSE와새대화/운영화면은후속이다.

재현: `.venv/bin/python -m pytest tests/test_operations.py -q` 및전체tests, Node22.23.1 frontendbuild/기존auth-tenants.spec.ts. 모든시험은자기marked DB와private자격을정리하며primary를reset하지않는다. 다음B03 API07~13 계획은250.구현/04문서11절이다.

B02 검증 소스 로컬 commit: `aae2ace8cab56b3393bb9fafd89adde4caf1faf6`. 검증 소스의 SHA256을 대조한 후 후속 문서 commit에서 연결했다.

## B03 — 대화·질문 접수/조회/취소 증거

B03-test-summary는 최종 소스 지문/집계, test-results는 개별 399 backend(신규77 포함)와 기존 A browser20, db-boundaries는 현재 owner/RLS·동시성과 primary 보존, runtime-check는 실제 HTTP7경로/재시작·정리/제한을 담는다. native HTTP는 77개 안의 1시험이며 7경로를 추가 시험으로 합산하지 않는다. 선행 실패·반복 target 수행을 최종399에 다시 더하지 않는다. 새 B UI/AI 답변·전체 V41/Q20은 후속이다.

원문 본문/지침/DSN/세션/CSRF/키/SQL 오류행/전체 JUnit·log는 .runtime 비공개 자료이며 Git과 공개 증거에 넣지 않는다. 기존 A/B01/B02 증거는 당시 수행 결과로 보존한다. B03이 필요한 owner-scope 콘텐츠 읽기 권한을 추가한 현재 상태는 B03-db-boundaries에 기록하고 B02의 당시 권한 관측을 덮어쓰지 않는다.

B03 검증 소스 로컬 commit: `40a28621652d91b04ee7eb613955db5b0bb813f5`. 검증 소스의 SHA256을 대조한 후 후속 문서 commit에서 연결했다.


## B04 실행·정산·SSE 검증

2026-10-05: 전체 backend 467 pass/실패0/경고0/497.0초, 신규B04 68건(실제HTTP/프로세스 강제종료·재시작 포함), 기존A browser20 pass/build 성공/runner0/30.62초. 위 신규 건수를 전체 수에 중복 가산하지 않는다. paid AI0건/0원이고 OpenAI는 SDK 가짜 전송 검증만 수행했다.

B04-test-summary.json은 정확 소스 지문·검증 요약, B04-test-results.json은 개별 test ID/결과, B04-db-boundaries.json은 DB권한/원장 경계, B04-runtime-check.json은 008만 적용/보존/정리 결과다. 이전 A/B01~03 JSON은 그대로 보존했다. 비공개 로그·계정/DSN/claim/본문은 공개 증거에 포함하지 않는다. 로컬 검증 소스 commit은 다음 문서 commit에서 지문 대조 후 연결한다.

B04 검증 소스 로컬 commit: `4a2c925b257d00b63f2784b757df7768462cf3fc`. 검증 소스의 SHA256을 대조한 후 후속 문서 commit에서 연결했다.


## B05 현재 증거

- B05-test-summary.json: 현재 범위·477/51 통과·실호출0·소스 지문·미완료.
- B05-test-results.json: 정제 backend477/browser51 ID·상태·시간, 선행 실패/수정 구분. 재시험을 합계에 더하지 않는다.
- B05-db-boundaries.json: 조직/세대/현재권한/해제·canonical·revision·독립 전역 capability·unknown 예약·기본 DB 준비 변경과 보존.
- B05-runtime-check.json: 기본 A/B 실제 HTTP 준비 상태, 비공개 key/인증 줄 보존·준비 재실행0·web/meter 종료/임시DB·포트0.

재현: backend `pytest tests -q`, frontend `npm run build`와 `npm run test:e2e -- tests/auth-tenants.spec.ts tests/chat-operations.spec.ts`. 기본 시연 준비/서버 시작은 backend README B05 절을 따른다. 임시 브라우저 fixture에는 등록된 실제 key를 전달하지 않는다. 과거 JSON/PNG는 보존하며 본 README는 현재 단계의 증거 색인으로 갱신한다.
