---
created: 2026-10-12
status: passed-for-DP11-01
---
# 28 DP11-01 Builder 저장 버전 조합과 자료 권한 검증

[[28 DP11 Agent Builder 프롬프트 RAG Playground 상세 개발 계획서]] · [[27 DP11-01 Builder 템플릿 조합 검증 구현 결과]]. 실제 앱 DP11-01의 합성 fixture 검증이며 실제 모델 품질/기관 UAT/운영 배포 완료가 아니다.

| 검사 | 최신 결과 | 증거 |
|---|---|---|
| backend builder+기존 assets | 52 고유 사례 pass(50+추가2) | evidence/DP11-builder-composition/backend-safe.json |
| browser 기존 자산6+신규Builder3 | 9 고유 사례 pass | browser-safe.json |
| user/admin build·경계 | user23/admin23 pass | build-safe.json |
| 기존 SQL checksum | 30개 일치·새migration0 | migration-safe.json |
| fixture 정리 | pool0·DB/credential/source 제거 | cleanup-safe.json |
| local 복구·읽기 smoke | API8000/user5173/admin5174 HTTP200 | smoke-safe.json |
| 변경14 source hash | SHA256 기록 | source-hashes.json |

서버 사례는 중복 치환/JSON 단일괄호/invalid 문법·변수/크기/NULL/surrogate/CSRF/extra query/bodylimit/legacy/stale/타조직/일반권한·현재role회수/명시RAG refs/중복refs/실제게시·회수와 미리보기의 자산·버전·run·call·audit 행 무변경을 포함한다. browser는 저장/새버전/reload/escape/dirty/잘못된문법/자료미선택·조직전환중 늦은응답을 포함한다. 기존 자산 browser6은 직전 실행, 신규3은 ID등록 후 재실행의 최신 결과다.

첫 backend 실행48pass/1fail/1error: 새 오류 코드에 MESSAGES 누락으로KeyError, 기존local API8000과재시작시험 충돌. 서버메시지추가·소유서비스중단후50pass, 추가권한/실제문서회수2pass. 첫build는iterator.map타입오류, 배열spread로수정후pass. rawJUnit/진단은private tmp에만보존하고공개증거는sanitized집계다. primary모델/자산쓰기/paid호출0, primary전체행fingerprint는재측정하지않았다. ObsidianMarkdown파일은검사하며GUI렌더링미검증.
