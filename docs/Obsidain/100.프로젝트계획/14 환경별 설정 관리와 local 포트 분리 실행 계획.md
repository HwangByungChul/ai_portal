---
title: 환경별 설정 관리와 local 포트 분리 실행 계획
created: 2026-10-12
updated: 2026-10-12
status: local-complete-external-pending
tags: [ai-platform, environment, configuration, ports]
---

# 환경별 설정 관리와 local 포트 분리 실행 계획

사용자 결정: 도메인 없이 포트로 사이트를 구분하고 local/dev/tb/prd 환경을 설정 파일로 관리한다. 기존 계획12의 환경 계약을 구체화한다. 사용자·관리자 A/A+B 디자인과 독립 빌드는 유지한다.

## 순서와 검증

1. `config/environments/{local,dev,tb,prd}.json`의 공개 설정을 단일 원본으로 저장한다. 주소·포트·진입·바인딩·세션 준비 상태를 관리하며 비밀/DSN/키는 기존 비밀 주입으로 분리한다. 미확정 환경은 configured=false와 null 주소로 표현하고 실행/빌드 시 실패한다.
2. Python/Node 엄격 검증을 적용한다. unknown 환경/필드·잘못된 포트·중복 포트·origin/port 불일치·credential/path/query를 포함한 origin·local 비loopback·외부 환경 HTTP를 거부한다. 비밀 값은 오류에 출력하지 않는다.
3. 실제 frontend Vite 프록시·포트·사이트 링크와 backend trusted Origin을 파일에서 읽는다. CSRF/단일 Origin 헤더/현재 API·DB 권한은 유지한다. wildcard CORS나 Origin 위조 프록시는 추가하지 않는다.
4. local 사용자5173/관리자5174/API8000의 소유 서비스 실행·정지를 지원한다. 설정이 잘못되어도 기존 소유 프로세스 정지는 가능하게 한다. 변경 전 소스 SHA/백업을 보존한다.
5. config 검증·기존 auth·새 Origin 거부/CSRF/API 경계·local 두 포트 실제 브라우저 로그인/이동/승인/서버 로그아웃 거부를 폐기용 DB로 시험한다. 기존 주 DB 초기화·새 migration·유료 모델 호출 없음.
6. build와 사용자 관리 코드 제외 검사를 유지하고 서비스 복구·Obsidian 구현/검증·원본 근거 링크를 기록한다.

- [x] 4개 환경 파일·엄격 검증·소비자 연결
- [x] local 두 포트 실행·실제 auth/승인 검증
- [x] 두 빌드·회귀·소유 서비스 복구
- [x] Obsidian 결과·증거·링크 갱신
- [ ] dev/tb/prd 실제 주소·인증/BFF·TLS·운영 DB·배포 수용 시험

## 인증 경계와 출시 상태

포트 차이는 다른 origin이며 쿠키는 port isolation을 제공하지 않는다. local 두 포트는 같은 신뢰 경계의 개발 UI·공통 세션을 사용한다. 역할·조직·승인자 분리의 최종 경계는 API/DB다. BroadcastChannel은 다른 포트로 전달되지 않으므로 다른 앱 로그아웃은 서버 세션 폐기와 다음 focus/요청의 재검증으로 확인한다. 즉시 다른 창 화면을 지우는 상용 로그아웃 계약은 별도 인증 단계다.

외부 환경은 HTTPS origin을 입력할 수 있는 구조로 마련하되 실제 주소/인증/운영 DB가 없으면 실행하지 않는다. 환경 파일을 추가했다고 기존 fixture DB가 운영 DB가 되는 것은 아니다. 상용 backend profile/BFF/site session 이행은 계획12 후속이다.

근거: [MDN Origin](https://developer.mozilla.org/en-US/docs/Glossary/Origin), [RFC6265 port cookie isolation](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5). 운영 비밀은 Git/공개 설정/프런트 번들에 넣지 않는다.

## 2026-10-12 · local 완료

[[200.프로젝트실행/250.구현/23 환경별 설정 관리와 local 포트 분리 구현 결과]]과 [[200.프로젝트실행/280.통합시스템테스트/24 환경 설정과 두 포트 통합 검증 결과]]를 따른다. dev/tb/prd 입력·상용 인증/runtime/DB·운영 배포는 미완료이며 별도 수용 시험이 필요하다.
