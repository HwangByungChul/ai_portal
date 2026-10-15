# 2026-10-14 원본 DB Task1 복구 조사·비공개 백업·복원 시험

상태: 백업 복원 검증 통과, 040 정확 원본 미확인으로 최신 migration 및 primary 이행 보류. 운영 배포·유료 호출·재seed 없음.

## 수행과 증거
- 계획33/AGENTS를 읽고 primary는 읽기만 수행했다. 40845 프로세스의 사용자 jwpios와 정확한 `-m scripts.portal_test_server` 명령, private 소유기록을 대조한 뒤 SIGTERM했다. A05-cleanup은 pool0/fixture 제거/credentials 제거/source store 제거/cluster running을 확인했다. 다른 프로세스·primary cluster 중지 없음.
- `db_restore_audit.py`: DevCluster ownership 및 FixtureDatabase marker 검증, transaction READ ONLY로 41개 적용 checksum과 모든 source hash 확인. 불일치는 040 하나. 53개 테이블. `audit.json`, `040-current-before.sql`, primary 함수 본문과 두 diff 보존.
- 현재040 SHA256 `49235a34ddcdb1a3c034c6ac42303cbd3bfadaddb20d3e2bf71830521e07fff4`, DB 이력 `ca78a8d3c17ee6c104d5703a01c500edda3efcb7c398b2f6d26e2ae64c661adb`. primary dynamic_favorite_mutate 본문은 action literal 두 위치만 dynamic_favorite로 다르고 published_agent_read 본문은 정확히 같다. 두 literal 수정 후보 `4ccf60654f96ea92312e97e8dcd9b63bf6d5849764677f217d0c2b64053b31cb`도 이력과 다르므로 적용하지 않았다.
- git040 이력/objects 없음. antigravity/tmp/.codex의 이름이 같은 SQL은 현재파일 하나. scoped archived session SQL 출력 후보는 현재 hash와 같았다. 줄바꿈·선행/후행 newline 변형과 bounded 2856개 blank/line 후보에도 정확 hash 없음. 과거 source를 추정하여 성공이라고 표시하지 않았다.
- 실제 primary catalog_mutations CHECK는 favorite/access_set만 허용한다. primary 함수의 dynamic_favorite literal과도 불일치하므로 기존 역사적 기능 결함 가능성이 있다. 역사SQL을 임의 수정하는 대신 새 migration에서 수정해야 한다.
- `db_restore_backup.py`: `.runtime/backups/db-restore-20261014` 0700에 pg_dump custom backup, app.env/roles/active fixture/fixture account secrets/비공개 계정 문서 사본을 각각0600으로 저장했다. dump SHA/size와 원본파일별 SHA는 `backup-restore-proof.json`에 있고 내용·비밀번호·DSN은 출력하지 않았다.
- 새 별도 소유marker DB `ai_portal_mvp_test_9006ab8b2a434b1a933877084b1af71a`에 pg_restore exit-on-error/single-transaction으로 복원했다. 모든53표의 기존열·행별 JSONB SHA 집합과 전체 digest가 정확하게 같았다. 13개 security.accounts 전체행(비밀번호 hash 포함) 정확 보존. `primary-pre-tables.json`과 proof 참조.
- 정상 `apply_migrations(restored)`는 MIGRATION_CHECKSUM_CHANGED로 실패했다. runner 예외 후 복원DB의 전표행/열 digest는 동일해 원자 rollback 확인. primary 역시 이전53표 digest와 같다. SQL/이력/runner 검증을 변경하지 않았다.
- 활성 accepted/running run0, call11개 모두 settled, unknown provider0, 예약금0. 새 provider 호출0.
- default `.runtime/source-store`는 존재하지만 파일0개이며 app.env source-root override 없다. rag.document_versions 2개는 DB전행보존 검증했으나 원문파일 retrieval/복구는 확인하지 못했다. 빈 source-store도 비공개 백업했다.

## 실제 명령
`PYTHONPATH=src/backend src/backend/.venv/bin/python /private/tmp/db_restore_audit.py`
`PYTHONPATH=src/backend src/backend/.venv/bin/python /private/tmp/db_restore_backup.py`
`PYTHONPATH=src/backend src/backend/.venv/bin/python /private/tmp/db_restore_finalize.py`
실행 script 사본은 본 evidence 폴더에 남긴다. 최초 finalize의 portal.documents 쿼리는 UndefinedTable 실패; 실제 rag.document_versions로 수정하여 재실행 성공. 복원 stderr는 비공개 backup 폴더에0600 보존. 전역DB나 실행 credential 변경 없음.

## 미완료 및 대안 제안
정확 ca78 원본 파일 확보 전 정상 runner를 통한 기존DB041~050 이행은 통과할 수 없다. live 서비스/기존 login 검증은 아직 수행하지 않았다. source SQL0개 변경이며 040 전후 동일하다. 복원DB와 privatebackup은 리뷰용으로 유지한다.

대안은 기존DB/기존 checksum 기록을 그대로 보존하고 새marker DB에 현재 승인 source000~040을 정상 runner로 적용하여 새source hash 이력을 만드는 별도 데이터 이행이다. 기존53표 중 infra.schema_migrations를 제외한52표 데이터를 전행·기존열·passwordhash 그대로 복사하고 새DB의 초기 데이터와 충돌을 사전에 조사해야 한다. UUID/FK 의존과 복수표순환, defaults/trigger/RLS/owner/grants, 시퀀스 여부를 검사하고 생성기본행을 fixture범위에서 명시적으로 제거한 뒤 단일 data restore를 검증한다. 원본history는 비공개sidecar 및 그대로 둔 원본DB에서 보존하며 새DBhistory에 옛 hash를 억지로 적지 않는다. 신규041~050의 정상runner 적용 후 oldcolumns 행digest·account login·HMAC/DSN 설정 및 원문파일 검증까지 필요하다. 이 방식은 기존DB역사 복구와 구분되는 새DB데이터 이행이며 live cutover는 별도 아키텍처 결정과 사용자 확인이 필요하다. 이 보고에서는 대안을 실행하지 않았다.

## 검토 후 범위·승인 근거 보완

백업/복원 proof의 '동일/변경 없음' 측정범위는53표의열명·rowJSON/digest(13계정 포함)와기록checksum이다. 전체DDL/RLS/grants/sequence를별도동일지문으로측정한것은아니며원자rollback은strict runnertransaction구조와전후row/column증거로판정한다. 다음비파괴이관시험에서RLS/owner/grants/sequence·제약과현재login/API를추가확인한다. 원문source파일 미검증을유지한다.

위대안문단의'사용자확인필요'는당시구현자의미실행제안해석이다. 사용자는기존계정/데이터로최신기능사용을요청하고작업을승인했으며, root는원본DB/이력보존·백업/복원검증·별도새DB데이터이관·검토후되돌릴수있는local설정전환을그범위안의구현방법으로결정하여계획33에추가했다. 원본직접migration/checksum우회권한으로확대하지않는다.
