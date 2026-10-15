# 환경 설정

`local.json`, `dev.json`, `tb.json`, `prd.json`이 공개 배포 설정의 원본입니다. `AI_ENVIRONMENT=local|dev|tb|prd`로 선택합니다. 알 수 없는 환경·미설정 환경은 다른 환경으로 fallback하지 않습니다.

- local: 사용자 `http://127.0.0.1:5173/user/home`, 관리자 `http://127.0.0.1:5174/manage/admin`, API `http://127.0.0.1:8000`. 파일의 포트와 origin을 함께 수정합니다. 각 UI의 `/api` 프록시가 API에 연결합니다.
- dev/tb/prd: 실제 HTTPS origin과 port를 각각 채우고 `configured=true`로 전환해야 해당 환경 빌드가 가능합니다. 도메인이 없어도 인증서가 유효한 HTTPS IP+port 주소를 설정할 수 있습니다. 현재는 미설정이므로 실행·빌드가 실패합니다.
- `bind_host`는 현재 소유된 loopback 개발 실행을 위한127.0.0.1입니다. 외부환경 서비스는 인프라의 별도 TLS/reverse proxy/배포 실행 계약으로 구성합니다. 현재 local service controller와 fixture backend를 외부 환경으로 실행하는 것은 차단합니다.
- `session_mode`: local은 같은 호스트의 신뢰된 두 개발 UI가 공통 세션을 사용합니다. 쿠키는 port로 격리되지 않으며 다른 포트 BroadcastChannel도 전달되지 않습니다. 서버 로그아웃과 다음 focus/API 요청에서 세션 폐기를 확인합니다. dev/tb/prd는 site-sessions-required이며 실제 BFF/SSO 계약이 필요합니다.
- 공개 파일에는 DSN·사용자 계정·비밀번호·키를 넣지 않습니다. strict key validation이 임의 필드를 거부합니다. 기존 backend private env/비밀관리 주입은 별도로 유지합니다.
- 프런트 build에 주소가 반영되므로 설정 변경 후 재빌드/재실행합니다. backend 설정 변경 후 소유 서버를 정상 stop/start합니다. 운영 DB profile·TLS·SSO·CI 배포는 별도 후속 단계입니다.

예: `AI_ENVIRONMENT=local npm run build` (frontend), `AI_ENVIRONMENT=dev npm run build` (실제 dev 주소 설정 후). `npm run check:environments`는 네 파일 형식과 준비 상태를 검증합니다.

local 실행: `bash src/backend/start.sh`, `bash src/frontend/start.sh`, `bash src/frontend/admin-start.sh`. 관리자 정지: `bash src/frontend/admin-stop.sh`. 설정이 잘못되어도 소유 서비스 stop은 가능합니다. 다른 프로세스/주 DB는 정리하지 않습니다.

근거: https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5 , https://developer.mozilla.org/en-US/docs/Glossary/Origin

회귀 브라우저 시험은 Playwright가 세 포트의 소유 테스트 서비스를 실행합니다. `PORTAL_TEST_BUILT=1 npm run test:e2e -- tests/portal-ports.spec.ts`로 독립 빌드의 두 포트 통합을 확인합니다. 기존 개발 서비스를 정상 정지한 뒤 실행하고 완료 후 복구합니다. fixture/mock 시험이며 외부 환경 수용 시험을 대체하지 않습니다.
