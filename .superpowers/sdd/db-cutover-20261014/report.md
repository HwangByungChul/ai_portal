# Task3 로컬 DB 대상 전환 및 서비스 복구 — 2026-10-14

상태: **DONE — 실제 기존 계정 로그인·역할별 읽기·로그아웃 검증 통과, 서비스 실행 유지.** 운영 배포 또는 전체 기능 UAT 완료를 뜻하지 않는다.

원본 `ai_portal_mvp_test_b9a06099c0954eccb570ccbd37c92343`을 보존하고 검토된 새 marker DB `ai_portal_mvp_test_6b83243d57fe44c3964d5ecf73a9aa26`로 기존 로컬 설정의 DB 대상만 전환했다. 실제 변경 파일은 `src/backend/.runtime/app.env`, `src/backend/.runtime/active-fixture.json`이다. AI_WEB_DSN/AI_METER_DSN/AI_INDEX_DSN의 DB 이름만 바뀌었으며 credential/HMAC/key/mode는 동일하다. fixture registry는 database 필드만 바뀌고 원래 secret_path·actor IDs 등은 유지된다. private 원본·staged 설정은 `.runtime/backups/db-cutover-20261014` 0700/0600에 보존하며 symlink를 거부한다. 기존 Task1 설정 SHA를 먼저 대조했다.

전환 직전 source/stage marker, 원본53표 exact, stage의 기존52표 기존열·행 exact, 계정13 password hash 및 기존 secret match, 현재 source와 새51 ledger SHA 일치, run/job/workflow/tool/call의 active/unknown/미정산 예약0을 확인했다. 원본 DB의53표는 HTTP 검증 후에도 exact이다. stage 변경은 정상 auth/session/audit3표에 한정하며 계정·나머지 사업 데이터는 exact이다. retained stage pre/post digest는 본 폴더 JSON에 있다. 원본·historical ledger sidecar·Task1 backup·Task1 restore·stage는 삭제하지 않았다.

8000/5173/5174는 시작 전 비어 있었고 service_control로 backend/frontend/admin-frontend만 시작했다. health 200, 사용자 `/user/home`200, 관리자 `/manage/admin`200을 확인했다. a-u1/a-adm/p-a의 기존 private password로 login/me/tenants/logout 모두200을 assert했다. 실제 current tenant 역할별 admin overview/tool approval/workflow approval/tools/workflow catalog/use-cases 읽기18건 pass, USER의 관리자3경로는403이다. API 실행/쓰기·provider 호출은 하지 않았다. 원래 AI_MODE=mock과 실행 설정은 보존했다.

## 실패·복구 검증

첫3차 시도는 별도 readiness 검사에서 관리 frontend root `/`의302를200으로 잘못 기대하여 중단되었다. 1차 assertion에는 안전한 상태 설명이 없었고, 2차 HTTP_READINESS_FAILED를 기록했다. 3차 환경 프록시를 배제했으나 같은 실패가 지속되어 원인검사를 했다. 전환하지 않은 상태에서 서비스_control 관리 frontend만 시작하여 `/`302 Location `/manage/`, `/manage/admin`200을 직접 확인했다. 실제 진입 경로200을 검사하도록 수정한 4차는 통과했다. 실패3건 모두 아직 auth 이전이었으며 원본 두 설정이 byte exact로 함께 복구되고 이 작업이 시작한 소유 서비스만 종료되었다. `attempt1/2/3-failure.json`에 안전한 실패·복구 증거를 보존했다. 현재는 새 target으로 두 설정 일치, 서비스 실행 유지이다.

## 재현과 rollback

검토된 일회성 실행 소스는 `cutover.py`, 최종 증거는 `proof.json`이다. 성공 후 재실행용 일반 도구가 아니며 전제 조건은 원본 설정 SHA·서비스 포트가 비어 있음이다. rollback은 사용자 작업을 먼저 멈추고 service_control로 이번 소유 세 서비스를 정상 종료한 후 private app.env.original/active-fixture.json.original 두 파일을0600 atomic replace로 복구하며 pair byte SHA를 확인한다. 원본DB schema040 checksum 문제가 알려져 있어 옛 backend가 최신 앱에서 정상 시작한다고 보장하지 않는다. 원본 데이터에 복원/seed/migration을 자동 적용하지 않는다.

## 남은 한계

040 역사 원본 bytes 미발견 및 원본 직접upgrade 차단 유지. 원문 파일0개·document_versions2개 원문 bytes는 선행 미복구이며 이관으로 복구됐다고 주장하지 않는다. private 문서02의13 계정 password 보존·match, 문서00 stale 유지. 문서02는 이번 agent가 변경하지 않았다. 기존 catalog evidence는 검토된 tables/owners/RLS/grants/policies/functions/constraints/user-trigger 항목에 한정되며 전체 schema/security 무제한 exact 주장이 아니다. 최신 Tool/Workflow 승인 쓰기·실행 전체 UAT, 실provider, 기관 정책 등록, 운영 배포는 미검증이다. Obsidian 지속 기록·페이지 열기는 root가 본 최종 evidence를 반영한다.
