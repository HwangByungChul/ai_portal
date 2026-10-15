# Task1 백업·복원 증거 검토 — 2026-10-14

판정: **백업·복원 단계 통과(증거 범위 한정), 비파괴 이관 대안 검증 착수 가능**. 정확한 과거 040 SQL 복구 및 원본 DB 직접 041~050 이행은 **차단 유지**. Task1 전체/최신 기능 수용/서비스 복구/원문 복구 통과를 뜻하지 않는다.

## 검토 범위와 방법
계획33의 원본 복구 목표와 추가 비파괴 이관 대안, report.md, audit.json, backup-restore-proof.json, primary-pre-tables.json, 세 실행 script 사본, 현행 migration runner/fixture 생성 코드를 정적으로 검토했다. 파일시스템 읽기만으로 dump SHA256·size, 비공개 폴더/파일 mode 및 현재040/보존040 byte hash 동일성을 별도 대조했다. DB 접속·SQL 실행·테스트 재실행·프로세스 제어·설정 변경은 하지 않았다. 실행 결과 JSON은 원 실행자의 증거이며 이번 검토에서 독립적으로 DB 상태를 재측정하지 않았다.

## 충족한 백업·복원 증거
- audit는 적용41개 중040만 불일치, primary53표를 기록한다. primary-pre-tables에는53표와 security.accounts13행이 있다.
- db_restore_backup.py:9~21은 marker 검증과 READ ONLY transaction에서 표별 column-name list, 행수, 정렬된 전체 JSONB 행 SHA256의 aggregate digest를 만든다. 중복행도 정렬 목록에 유지된다. accounts 전체행에 passwordhash 열이 포함되어 행digest 일치는 hash값 보존을 포함한다. 비밀번호 평문/직접 passwordhash값은 공개 proof에 없다.
- 같은 script:31~41의 custom dump 및 별도 새 fixture DB pg_restore는 exit-on-error/single-transaction으로 수행됐다. proof는 전체53표·accounts 동일을 기록한다. dump 파일의 SHA256/881955 bytes를 이번 파일 읽기 검토에서 재확인했다.
- private backup directory0700, dump/설정/역할/fixture secrets/계정문서/stderr0600, source-store0700을 현재 mode로 확인했다. 공개 산출물은 hash/count/경로/SQL 함수 구조이며 DSN·키·비밀번호·문서 원문을 포함하지 않는다.
- script:42~45와 proof는 정상runner의 MIGRATION_CHECKSUM_CHANGED, 복원본 및 primary row/column digest 동일을 기록한다. src/backend/scripts/migrate.py:95~130은 checksum 확인과 SQL 적용을 하나의 transaction으로 묶으며040 불일치는 신규041 적용 및 마지막 ALTER ROLE 단계 이전에 발생한다. 검증 완화·옛 checksum 덮어쓰기 경로가 없다.
- fixture create는 UUID 이름, 소유 marker, PUBLIC 권한 회수 및 connection limit0을 설정하고 snapshots/runner는 marker를 검사한다. 이는 같은 소유 DevCluster 안의 별도 DB이며 별도 cluster/별도 공유역할의 보안 격리를 의미하지 않는다. dump SQL과 기존 DB 함수를 같은 신뢰된 개발 source로 취급한 복원 증거이다.

## 구체적 발견 및 증거 한계
1. **[P2, 증거 표현 한정] db_restore_backup.py:19~20,44 / report.md의 원자 rollback 표현:** snapshot은 열 이름·행수·행digest만 비교한다. 열 type/default, constraint, function, trigger, RLS, grants, owner, sequence 및 database ACL/connection limit까지 catalog 동일을 직접 증명하지 않는다. 따라서 `runner_failure_atomic_no_row_or_schema_changes`는 실제 측정상 “행/열명 변화 없음”이다. 정상runner transaction 구조는 이번 checksum 예외의 rollback을 뒷받침하므로 백업 게이트를 막지는 않지만, 후속 이관에서 전체 schema/security 보존 증거로 재사용해서는 안 된다.
2. **[정보, 재현성] db_restore_backup.py:41~45,53:** after/post/primary-after 상세 snapshot은 저장하지 않고 equality boolean만 저장한다. 실행 script와 before snapshot이 있어 방법은 검토 가능하나 reviewer가 persisted 결과로 표별 차이를 재계산할 수는 없다. 후속 이관 검증에서는 민감값 대신 pre/post column별·table별 digest 증거와 catalog/sequence 비교를 저장하는 것이 필요하다.
3. **[차단 유지] db_restore_finalize.py:20 / audit.json / report.md:** 정확 이력040 SHA `ca78a8d3c17ee6c104d5703a01c500edda3efcb7c398b2f6d26e2ae64c661adb`와 현재/candidate byte hash는 다르다. 함수 두 literal 차이 및 whitespace 탐색 실패는 원본 확보를 뜻하지 않는다. 현재040은 보존본과 동일하며 runner 실패가 올바르게 유지됐다. 정확 bytes 복구/직접 원본DB 이행 spec은 미충족이다.
4. **[미검증] db_restore_finalize.py:8~18 / proof source_store:** source-store 파일0개와 DB 문서버전2행 보존은 문서 원문 retrieval/복구 가능성 증거가 아니다. 기존 account login, HMAC/DSN 설정 연결, 최신 API/서비스 수용도 수행하지 않았다.

## 다음 단계 게이트
계획33 추가 대안의 검증을 진행할 수 있다: 별도 marker DB에 현재 승인000~040 정상runner 적용 → 원본 infra.schema_migrations 제외52표 기존 데이터 이관(재seed/원본history 덮어쓰기 없음) → 정상041~050 적용 → 기존열/전행/passwordhash 및 FK·sequence·security/catalog·login/API·자료설정 검증. 초기 생성행 충돌 제거는 새 fixture 범위와 단일 data restore에 한정하고 원본DB/이력은 그대로 보존해야 한다. 검증 통과 후에만 승인된 설정 전환을 진행한다. 이 대안은 아직 구현/검증되지 않았으며 이번 백업 게이트 판정이 대안의 성공 또는 source040 복구 성공을 미리 승인하는 것은 아니다.
