# 로컬 DB 전환·서비스 연속성 최종 검토 — 2026-10-14

판정: **현재 완료된 일회성 로컬 전환 수용 가능. Critical 0 / Important 0 / 신규 Minor 2.** 계획33의 승인된 비파괴 이관 대안과 기존 계정 기반 최신 서비스 접근 목표는 제공된 증거 범위에서 충족한다. 원본040 byte 복구·원본 직접 migration 목표는 차단 유지한다. 구현 품질은 이번 완료 실행에 수용 가능하며 일반화된 장애복구 도구로 승인하는 판정은 아니다.

## 방법과 독립 대조
계획33, Task1 report/review, Task2 report/review, cutover report/proof/script, stage snapshot 함수, service_control을 읽었다. DB 접속·테스트 재실행·설정 변경·프로세스 시작/중지는 하지 않았다. private app.env/계정 문서/secret 내용을 출력하거나 읽지 않았다. 저장된 JSON과 script bytes만 독립 대조했다. 현재 서비스와 설정에 대한 root의 별도 실측은 이 검토와 구분한다.

- cutover.py SHA256은 proof의 f81cff5c9f7eaf13c0a5ed37e2f40d8b2131e93cd0723890a7069b31ca3757fb와 일치한다.
- stage pre/post digest 차이는 ops.audit_events/security.login_windows/security.sessions 세 표뿐이다. security.accounts13행 전체 digest가 동일하다. Task2 source pre/final53표는 동일하다. cutover.py:67은 HTTP 이후 원본53표 exact를 다시 assert하며 그 결과는 실행자 proof에 의존한다.
- 실제 저장 결과는 a-u1 USER/a-adm TADMIN/p-a PADMIN 각각 login/me/tenants/logout200, 총18개 읽기 assertion을 기록한다. USER 관리자3경로403, 나머지 읽기200이다. paid/provider 실행 경로가 없다.
- 실패1~3 결과는 모두 FAILED/config_pair_restored=true다. 관리자 root302는 정상 redirect이며 실제 /manage/admin200을 검사한 최종 readiness200 3개와 구별되어 보고된다.

## 안전성·spec 통합 판단
cutover.py:24–27은 Task1 설정 SHA와 정확히 대조하고, :10–16은 symlink 거부/0600 임시파일 fsync/개별 atomic replace를 수행한다. :28–29는 서비스 포트가 비어 있음을 요구하고, :31–34와 stage.py:10–12는 원본/대상 marker 및 기존 데이터·새51개 현재 source checksum을 확인한다. :40–46은 기존 fixture DB와13개 account password를 검증하며 DSN 세 값의 DB 이름만 바꾸고 fixture database 이외 필드를 유지한다. 기존 secret_path/actor IDs와 HMAC/keys/mode 보존은 해당 변환 및 실제 설정 전후 검증으로 제한된다. cluster role verifier bytes 전체 불변을 주장하지 않는다.

:51–56은 두 설정을 모두 바꾸고 대상 일치를 확인한 후 서비스를 시작한다. 두 파일을 하나의 원자 transaction으로 바꾸는 것은 아니지만, 서비스 중지 상태에서 쌍을 구성하는 이번 방식과 실패3회의 복구 증거는 일관된다. service_control.py:22–62,80–105는 PID 시작시각 identity와 service 기록에 의한 소유 확인 후만 종료하며 다른 프로세스에 신호를 보내지 않는다. 현재 성공 경로는 서비스 실행을 유지한다.

원본53표와 역사41개 ledger 보존, 새DB의 정당한 현재51개 ledger, 이관52개 업무표를 구별한다. 새DB 데이터 이관은 기존 계정 재seed가 아니다. Task2의 scoped catalog/FK 검증과 실제 credential 인증을 통합해 현재 전환을 수용하되 전체 schema/security 무제한 동일성으로 확대하지 않는다.

## 신규 발견 사항
1. **Minor — cutover.py:71–77:** 실패 복구에서 service stop 예외를 삼키고 첫 설정 복구가 실패하면 둘째 설정 복구와 최종 proof 저장에 도달하지 못한다. 따라서 임의의 I/O 오류나 서비스 종료 실패에도 두 파일 복구를 보장하는 범용 도구는 아니다. 현재3회 실제 실패는 paired byte restoration에 성공했고 최종 실행도 성공했으므로 현재 서비스 전환의 차단 사유는 아니다. 재사용 전 각 restore를 독립 시도하고 stop/restore 결과를 각각 보존하며 불완전 복구를 명시적으로 보고해야 한다.
2. **Minor — cutover.py:61–65:** expected role은 반환된 membership에서 유도하고 items 비어 있음/계정별 expected role/총18건을 script에서 assert하지 않는다. 잘못된 role이나 빈 membership을 일반 검증에서 놓칠 수 있다. 이번 proof를 독립 읽은 결과 세 역할과18건은 정확하므로 현재 수용 증거는 충족한다. 재사용 전 계정별 기대 role/tenant와 결과 cardinality를 명시적으로 검증해야 한다.

## 유지되는 한계
Task2의 Minor3(전 단계 logout/capability assertion, catalog coverage, SQL NULL marker 비교)는 기존 검토 이력으로 유지한다. cutover logout은 명시 assert로 보완되었으며 이번 marker는 db.verify로 검증된다. 정확 역사040 bytes 미발견, 원문파일0개/문서버전2개 기존 원문 부재, stale 문서00과 유효한 문서02 구분, 이전 private tool-output 노출 사고 기록을 유지한다. 이 검토는 비밀을 재출력하지 않았다. Tool/Workflow 승인 쓰기·실행 전체 UAT/실provider/기관정책/운영 배포는 미검증이며 현재 로컬 로그인·읽기 수용과 구분한다. Obsidian과 비공개 문서02의 좁은 현황 보완은 root가 처리한다.
