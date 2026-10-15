---
title: 환경별 설정 관리와 local 포트 분리 구현 결과
created: 2026-10-12
updated: 2026-10-12
status: local-configured
production_deployed: false
tags: [ai-platform, environment, ports]
---

# 환경별 설정 관리와 local 포트 분리 구현 결과

사용자가 도메인 없이 포트로 구분하고 `local/dev/tb/prd`를 설정 파일로 관리하도록 요청했다. [[100.프로젝트계획/14 환경별 설정 관리와 local 포트 분리 실행 계획]]을 저장한 뒤 구현했다. 사용자 A 업무 홈·관리 A 운영 홈·B 승인 목록/상세와 독립 산출물은 유지했다. 이전 같은5173 출처 단계는 이력으로 보존하고 현재 두 포트 구성을 적용했다.

## 설정과 실제 파일

| 설정 | 관리 방식 |
|---|---|
| 환경 선택 | `AI_ENVIRONMENT`에 local/dev/tb/prd 지정; 생략 시 local, 오타는 오류 |
| 단일 공개 원본 | `config/environments/{local,dev,tb,prd}.json`, `README.md` |
| 구성 | schema version·환경·configured·bind_host·session_mode·user/admin/api의 origin/port/entry |
| local | user5173 `/user/home`, admin5174 `/manage/admin`, API8000. 각 UI의 같은 출처 `/api` 프록시 |
| dev/tb/prd | configured=false·origin=null. 실제 HTTPS IP+port 또는 도메인 주소 입력 전 build/start 차단 |
| 비밀 | 공개 JSON에 DSN/비밀번호/키 금지. 기존 private env/비밀 주입 유지 |

Python `src/backend/app/environment.py`와 Node `src/frontend/scripts/environment.mjs`가 같은 네 원본을 엄격 검증한다. unknown key/environment, origin/port 불일치, origin에 credentials/path/query/hash, 중복/범위 밖 포트, local 비loopback, 외부환경 HTTP를 거부한다. 오류는 값이나 비밀을 출력하지 않는 일반 코드다. 파일이 없거나 미설정이면 local로 대체하지 않는다.

`app/config.py`, `main.py`, `auth/guards.py`는 선택 환경의 정확한 trusted origin을 사용한다. 단일 Origin 헤더·요청 헤더·CSRF 검증과 역할·조직·자가 승인 금지는 유지한다. 두 개발 origin을 허용하는 것 외에 wildcard CORS/프록시 Origin 변경/권한 승격은 없다.

`vite.config.ts`와 공통 `PortalShell.tsx`는 파일에서 사이트 링크·포트·API 프록시를 읽는다. 주소는 build에 포함되므로 환경/주소 변경 후 재빌드한다. `scripts/service_control.py`는 소유 API/사용자/관리자 프로세스에 별도 PID/로그/설정 SHA를 관리한다. 설정 변경 시 정상 재시작을 요구하고 invalid config여도 소유 stop은 가능하다. `src/frontend/admin-start.sh`/`admin-stop.sh`를 추가했다.

실행: 프로젝트 루트에서 `AI_ENVIRONMENT=local bash src/backend/start.sh`, `bash src/frontend/start.sh`, `bash src/frontend/admin-start.sh`. 프런트 폴더에서 `npm run check:environments`, `npm run test:config`, `AI_ENVIRONMENT=local npm run build`. 외부환경 build는 실제 공개 주소 설정 후 같은 selector로 실행한다. 현재 service controller/Vite 개발 서버와 fixture backend의 외부 환경 실행은 별도 상용 runtime 계약 전까지 차단한다.

## 세션·상용 경계

서로 다른 포트는 다른 origin이며 쿠키는 port로 격리되지 않는다. local은 같은 신뢰 경계의 공통 개발 세션이고 서버 로그아웃 이후 다른 포트의 다음 focus/API/navigation에서 재인증한다. 다른 포트의 BroadcastChannel 즉시 전파는 보장하지 않는다. 출처: [MDN Origin](https://developer.mozilla.org/en-US/docs/Glossary/Origin), [RFC6265 8.5](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5).

local Vite는 개발 서버이며 운영 정적 호스트/BFF의 자산 격리나 관리 네트워크 경계를 대체하지 않는다. dev/tb/prd는 site-sessions-required를 명시했으나 실제 SSO/BFF·별도 사이트 세션·TLS·운영 DB/비밀관리·CI 배포는 미구현/미검증이다. JSON을 채웠다고 운영 준비 완료가 되지 않는다. 기존 fixture 보호를 해제하거나 주 DB를 초기화하지 않았다. 새 migration/유료 호출/외부 배포 없다.

## 결과와 다음

[[200.프로젝트실행/280.통합시스템테스트/24 환경 설정과 두 포트 통합 검증 결과]]에 설정19·backend75·정적 포트/기존 홈10·정적 독립 앱7·수정 후 개발 포트4를 개별 실행으로 기록했다. 최종 타입/두 빌드/관리 코드 제외 검사 성공. 관리자 개발 경로404를 수정하고 세 서비스 HTTP200 및 올바른 entry/중복 시작 방지를 확인했다. Obsidian Markdown 파일 갱신 완료이며 앱의 렌더링 확인은 수행하지 않았다.

다음: 실제 dev/tb/prd 주소/인프라 입력 → IdP와 사이트별 클라이언트·BFF/세션 계약 → 운영 DB profile/비밀/TLS/배포 수용 시험. 계획12의 상용 전환 순서를 유지한다.
