# 첫 기능 A 통합 검증 증거

2026-10-05 I250-A06. **A의 인증·조직·관리 기능 완료**. 백엔드176pass/경고1/185.06초, 프론트build/실제Chromium20pass/runner error0. 과거A01~05 증거는 당시 이력이며 현재 횟수에 합산하지 않는다.

- `summary.json`: 현재 범위판정·V41 상태·버전/실측·소스SHA256·보존·미완료.
- `test-results.json`: 백엔드176+브라우저20건. A06 상세4관측은176 안의4개 시험 설명이며 추가4건으로 계산하지 않는다.
- `db-boundaries.json`: 새합성DB에서 실제ai_web 로그인역할/권한/소유/RLS/고정함수·최소행수·종료연결0. DSN·비밀·본문 없음.
- A05 빈로그인2장은 기존파일 그대로 보존했다. 민감화면/trace/video를 공개 저장하지 않는다.

실제child API 재시작·동일쿠키/8h/30m/회수/실패창/RLS보존, 실제55432 DB stop/start와login/logout/member read/write503·복구후명시변경1/감사1·logout401을 확인했다. 인증된 `GET /api/v1/me/tenants` 20회(별도warmup1/keep-alive/동시1)의nearest-rank p95 **5.766ms**, 목표300ms이내다. 국소환경 측정이며GraphRAG/실AI/기관운영SLA 결과가 아니다.

pool 대기는 A 승인계획의5초다. 공통240 설계의2초 및idle transaction5초는 B01에서 정합시킬 항목으로 명시했다. 현재값을 달성했다고 쓰지 않는다. 고정SQL/짧은transaction·statement5초/lock2초·권한회수/rollback은 실제 검증했다.

V001/002/013/014/015는 A범위pass. V026/027/035~041은 A하위만pass이며 전체는not_run, 그 외B/C 요구와 원본Q20도not_run. AI/원장/문서/Graph/Grant 완료를 주장하지 않는다. 유료AI0원. 원본자료/합성9개/기존migration5개/private환경/primary11테이블 보존, 모든시험DB/비밀번호파일·pool정리/전용DB정지.

재현: backend전용환경에서 `.venv/bin/python -m pytest tests -q`, frontend의Node22.23.1 환경에서 `npm run build`, `npm run test:e2e -- tests/auth-tenants.spec.ts`. 8000/5173에기존서버가있으면먼저자신의서버를종료한다. 도구는낯선프로세스를종료하지않는다. private원본실패로그/JUnit/credentials는공유하지않고 정제된집계만전달한다.

실제검증소스commit은 `291eec857d0a241b8bc7a49d8b14aae8616fbf55`다. `commit`/`tested_source_commit`은이소스revision, `baseline_commit`은검증전이력이다. 소스파일지문과대조한후문서후속commit에서기록하여자기SHA를미리기입하지않는다. 개인학습/순수자동작업시간은미측정이고달력경과를80h실투입에서차감하지않는다.
