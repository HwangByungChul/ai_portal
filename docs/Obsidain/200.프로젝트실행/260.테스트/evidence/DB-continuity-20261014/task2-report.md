# Task2 비파괴 데이터 이관 staging — 2026-10-14

**상태: staging·실제 HTTP 검증 통과, root 검토 대기. active 설정 및 live 서비스 전환 미실행.**

원본 DB `ai_portal_mvp_test_b9a06099c0954eccb570ccbd37c92343` 및 원본 41개 checksum 이력을 보존했다. 별도 신규 marker DB `ai_portal_mvp_test_6b83243d57fe44c3964d5ecf73a9aa26`를 root 검토용으로 유지·명시적으로 인계한다. 역사 040 ca78 원본 bytes를 복구한 작업이 아니다. 현재 source 000–040의 새 정당한 적용 이력을 정상 runner로 생성하고 기존 데이터를 이관한 뒤 정상 041–050을 적용했다. 51개 새 이력 hash는 현재 각 source byte hash와 전부 일치한다. 원본 41개 이력은 원본 DB, 검증된 private custom backup, `historical-ledger-sidecar.json`에 그대로 있다.

## 데이터·schema/security 검증

- 검증된 Task1 custom dump SHA256을 실행 전에 재대조했다. 원본 53표 snapshot은 Task1 snapshot과 정확히 같았다.
- source/destination의 이름·marker·bootstrap user와 DevCluster 소유를 검사하고 destination이 primary/Task1 restore DB와 다름을 assert한다. data restore 내부 transaction에서 DB/marker/user를 재검사하고 migration advisory transaction lock250002를 획득했다. primary에는 READ ONLY snapshot/SELECT만 수행했다.
- 현재000–040 정상 적용 후 신규 DB에 52개 business표와 infra ledger가 존재하며 business 초기행은0개였다. 신규 marker DB business52표만 단일 transaction TRUNCATE 후 private custom backup data-only restore를 수행했다. infra.schema_migrations TOC entry만 제외하고 새 정당한 ledger41개를 유지했다. 계정 seed·fixture 생성자료·원본 truncate·원본checksum 덮어쓰기·runner검증완화 없음.
- FK 순환/append-only trigger 때문에 pg_restore의 `--disable-triggers`를 bootstrap 소유 권한으로 신규DB restore transaction 안에서만 사용했다. commit 전 정상 trigger enable 문이 실행되며 restore 전후 tables/owners/RLS/FORCE RLS/grants/column grants/policies/functions/constraints/user triggers catalog가 정확히 같다. ai_web 영구 권한을 확장하지 않았다. 모든96개 FK의 기존행 orphan count를 직접 확인했고0개였다. 최종67표 constraint 중 unvalidated0개. sequence는 원본·현재DB 모두0개로 값 조정 불필요하다.
- copy 직후52표 전열·전행 JSONB hash multiset digest가 exact, 041–050 적용 후에도 기존52표 기존열·전행 digest가 exact이다. security.accounts13개 전체행(비밀번호hash 포함)이 exact이다. pre/copied/upgraded/final table별·column-name·rowcount·digest 파일을 보존했다. 신규14표는 기존000–040표와 별도 확인하고 초기 count를 proof에 기록한다.
- 최종 원본53표 digest 및 원본DB table/owner/RLS/grants/column grants/policies/constraints/functions/triggers/sequence catalog가 unchanged이다. 현재040 소스 파일을 수정하지 않았으며 원본함수와 현재040 차이를 새DB historical복구 성공으로 표시하지 않는다.
- **공유역할 verifier 한정:** 정상runner가 기존 runtime password 값으로 `ALTER ROLE ... PASSWORD`를 재실행하므로 세 runtime역할 SCRAM verifier salted bytes가 바뀌었다. global 역할의 login/super/bypass/inherit/create/replication attributes는 동일하다. 이는 원본DB 자체DDL/계정hash 변경이 아니다. 기존 runtime password 값으로 원본DB·stageDB 각 ai_web/ai_meter/ai_index 실제인증6건 성공을 별도 증명했다. 전체cluster verifier byte unchanged라고 주장하지 않는다.
- active runs0, unknown provider0, reserved0. private app.env/active fixture/runtime roles/fixture account secret/두 계정 문서는 Task1 backup SHA와 모두 동일하다. active DB/DSN/HMAC/키/mode·서비스 설정 변경 없음.

## 실제 HTTP 검증

stagedDB를 private custom dump로 복제한 별도 marker DB에서 실제 uvicorn loopback ephemeral port로 실행했다. 주서비스8000/5173/5174와 기존harness를 사용하지 않았다. stage/원본의52개 historical business행을 login/session/audit/read-window 변화로 오염시키지 않기 위한 disposable 검증clone이다. clone 시작시 staged67표 snapshot exact를 확인했다. factory는 mode mock, 실행/index disabled, real API key None으로 고정하여 provider 호출0을 보장했다. test account·문서 생성 없음.

- 보존한 기존 private fixture password13개가 현재 account hash와 모두 일치한다. 실제 HTTP active12개 login200·me200·tenants200·logout200, inactive1개401 확인.
- current tenant의 USER/TADMIN/PADMIN 역할별 current catalog/published Agent/사용자 실행이력/기존 문서/tools/workflow catalog와 admin overview/guardrail policy/violation/tool approval/workflow approval/data import 읽기156건을 예상200/403과 assert했다. USER 관리조회403, TADMIN guardrail403, PADMIN guardrail200 등 guard 유지. data-import 목록은 현행계약상 USER도200이며 이를 관리권한 확장 성공으로 표현하지 않는다.
- p-a/p_read_only/p_write_only/p_none의 global usage/availability capability 분리를 auth/me로 확인했다. 기존 tenant 데이터에 별도 capability/default-policy seed backfill을 넣지 않았다. 신규 policy/version tables는 초기0행이며 existing-tenant PADMIN policy read가 기존 함수의 default policy 반환으로200이다. 기관 실 guardrail 정책 등록/운영 승인을 뜻하지 않는다.
- 개발 계정 문서02는13개 password 모두 current hash 일치. 과거 시연 문서00은13개 모두 불일치하여 stale로 기록한다. 비밀번호를 갱신하거나 문서를 재작성하지 않았다.
- 마지막 API child 종료·pool0·validation clone 삭제를 확인했다. stagedDB runtime 연결0, 원본53표/retained stage52표 기존열·행 final exact를 확인했다.

## 실패·정정 기록

1. 최초 read-only catalog query는 pg_get_functiondef가 aggregate(avg)에 적용되어 WrongObjectType 실패. primary mutation 및 stage 생성 전이었다. prokind='f' 제한을 추가했다.
2. staging 마지막 catalog exact assert는 global역할 SCRAM salt hash에만 차이가 있어 실패했다. 데이터를 이관하고 신규migration 적용한 stage는 정상 유지했다. source database catalog와 shared role attribute를 분리하고 existing runtime값 실제인증6건을 추가했다. final read-only 검증은 성공했다.
3. 최초 실제 HTTP login403은 validation client의 필수 X-Requested-With: ai-portal 누락이었다. 실패결과를 `http-validation-failed-missing-request-header.json`에 보존하고 clone/process를 정리했다. header 추가 후 전체검증 성공했다.
4. private 문서 구조 확인 중 불완전한 regex redaction이 tool output에 한 비밀번호를 노출했다. 값은 본 report/proof에 복사하지 않았으며 후속검증은 문서를 메모리에서만 파싱하고 booleans/counts를 저장했다. 비밀번호 reset·외부전송 없음. 단순 redaction된 excerpt도 다시 출력하지 않았다.

## 실제 명령·재현자료

프로젝트 root에서 실행:

```
PYTHONPATH=src/backend src/backend/.venv/bin/python .superpowers/sdd/db-data-migrate-20261014/stage.py
PYTHONPATH=src/backend src/backend/.venv/bin/python .superpowers/sdd/db-data-migrate-20261014/http_validation.py
PYTHONPATH=src/backend src/backend/.venv/bin/python .superpowers/sdd/db-data-migrate-20261014/finalize.py
```

stage.py는 신규DB만 생성한다. 단계별 검토 대상 script, 승인 source000–040 copy, source/new ledger, primary/fresh/copied/upgraded/final table·catalog snapshots, FK validation, active-file digest preservation, HTTP 결과, final proof를 본 폴더에 보존했다. restore SQL/dump/TOC/stderr/API log는 `.runtime/backups/db-restore-20261014` 0700/0600에 보존한다. 보고 proof는 비밀번호/DSN/HMAC/원문을 저장하지 않는다. shared Obsidian 기록은 root 담당이다.

## 미완료·후속

- live cutover/config/service start는 아직 하지 않았으며 root scoped review 이후에만 진행한다. 원본DB/backup/Task1 restore/stage를 삭제하지 않았다.
- source-store 원본파일0개와 DB document_versions2개의 원문bytes 부족은 선행손실·미복구 상태이며 새 이관으로 복구됐다고 주장하지 않는다. document/version 데이터행은 exact이고 이관에 의한 추가 유실은 확인되지 않았다. 원문retrieval의 성공·내용품질·기관수용·운영배포/실제provider 검증은 미완료다.
- historical040 정확 source 미확인 및 원본직접migration 차단 유지. 새DB 기능읽기 검증은 Tool/Workflow 승인쓰기/실행 전체 suite를 대신하지 않는다.
