# Task2 비파괴 이관 staging 최종 검토 — 2026-10-14

판정: **승인된 되돌릴 수 있는 로컬 설정 전환 진행 가능. Critical 0 / Important 0 / Minor 3.** Spec은 새 DB 데이터 이관 대안 범위에서 충족하며, 원본 역사 040 복구·원본 직접 migration은 여전히 미충족/차단이다. 구현 품질은 일회성 로컬 staging 용도로 수용 가능하다. 운영 배포나 최신 기능 전체 수용을 뜻하지 않는다.

## 검토 방법 및 확인

stage.py, http_validation.py, finalize.py, report.md, proof.json 및 Task1 report/review를 정적으로 읽었다. 저장된 JSON을 파일에서만 재계산하여 primary-pre/final 53표 exact, fresh/copied catalog exact, copied business 52표 exact, upgraded old-column 52표 exact, final stage 기존 52표 전체 snapshot exact, upgraded/final catalog exact, FK 96건 위반0, HTTP route156건 pass, active12 logout200을 확인했다. 새51개 ledger hash는 현재 migration 파일 SHA256과 독립적으로 대조하여 일치했다. DB 접속·재실행·서비스/설정 변경은 하지 않았다. 실행 당시의 DB 실상은 실행자가 남긴 산출물에 의존하며 현재 DB 상태를 새로 측정한 검토가 아니다.

- stage.py:40–59는 기존 active DB, 검증된 dump digest와 Task1 원본 snapshot, 52 business표 및 별도 생성DB를 확인한다. 67표는 business66+infra1이며 원본53표는 business52+infra1이다.
- stage.py:65–76은 별도 신규 marker DB를 대상으로 단일 BEGIN/COMMIT 안에서 business표 TRUNCATE 및 data-only restore를 수행한다. ON_ERROR_STOP 실패 시 commit하지 않는 연결 종료 경로이며 historical ledger 데이터는 제외한다. trigger disable은 이 transaction의 restore에 한정된다. fresh/copied catalog의 user-trigger 상태·owner·RLS·grants·정책·함수·제약 동일 및 96 FK orphan 검증을 함께 확인했다. 영구 runtime 권한 확장 근거는 없다.
- stage.py:90–98 및 finalize.py:9–29는 현재 source 041–050 정상 적용, 원본 데이터·기록 이력 보존 및 새 정당한51개 이력을 구분한다. 계정13개 전체행 digest 동일은 password hash 보존을 포함한다. 과거 hash를 새 이력에 삽입한 증거는 없다.
- 공유 runtime role SCRAM verifier bytes는 정상 runner의 재설정으로 달라졌다. 역할 속성 동일 및 기존 password로 원본/stage 각3역할 실제 인증6건은 별도 증거다. cluster 전체 byte 불변이라고 표현할 수 없다.
- HTTP 검증은 별도 disposable clone이며 active12 로그인200, inactive401, tenant별 USER/TADMIN/PADMIN 읽기 guard156건을 확인한다. retained stage 및 원본에는 HTTP session/audit 변경을 남기지 않았다. child 종료/pool0/clone 제거와 private 설정파일 동일성도 final proof가 기록한다.

## 발견 사항

1. **Minor — http_validation.py:83–84, finalize.py:12–14:** logout 응답은 기록하지만 assert하지 않으며 capability 분리는 me 응답을 저장할 뿐 명시적 expected capability assert가 없다. 이번 저장 결과에서는 active12 logout200을 확인했으므로 현재 전환 차단 사유가 아니다. 보고서의 capability 확인은 응답 검토 근거로 한정하고, 이 스크립트를 재사용할 때 logout 및 계정별 expected capability 검증을 추가해야 한다.
2. **Minor — stage.py:25–33, finalize.py:10:** catalog 지문은 column type/default/generated 속성, 일반 index, schema/database ACL·connection limit, role membership, internal trigger 상태 전체를 포함하지 않는다. 따라서 “전체 schema/security exact”라는 무제한 표현은 근거를 넘는다. 현재 복원은 data-only이고 fresh/copied 명시 catalog exact 및 FK 행검증이 있어 이번 일회성 이관을 차단하지 않는다. 현 보고의 구체적 측정 항목 범위를 유지해야 한다. convalidated=0개만으로 trigger 일시 해제 중 데이터 적합성을 입증하는 것도 아니며, 별도96개 orphan 검증이 그 근거다.
3. **Minor — stage.py:70:** transaction 내부 marker 비교는 `<>`여서 marker가 NULL이면 SQL 3값 논리상 그 항목 자체가 실패를 유발하지 않는다. 앞선 db.verify와 fresh owned DB 생성, DB명 및 session user 검사가 현재 실행을 보호하므로 현 evidence에 반하는 위험 징후는 없다. 재사용 전 marker 조건을 `IS DISTINCT FROM`으로 바꾸면 transaction guard 자체도 NULL에 대해 닫힌다. 이 검토는 script를 수정하거나 다시 실행하지 않았다.

## 전환 범위 및 남은 한계

root는 원본DB·백업·옛 ledger 및 private 설정 원본을 보존한 채 app.env/active-fixture의 DB 대상만 일관되게 전환하고 service_control start 후 실제 health/login/API 수용을 확인할 수 있다. 두 파일의 개별 atomic replace가 두 파일 전체의 동시 원자성을 뜻하지 않으므로 서비스가 멈춘 상태에서 쌍의 대상 일치를 확인한 뒤 시작하고, 시작/수용 실패 시 두 파일을 함께 기존 대상으로 복귀해야 한다. HMAC·DSN credential·기타 설정을 유지하고 원본DB migration/seed 및 유료 호출은 이 단계에 포함하지 않는다.

문서버전2개 원문 bytes는 기존부터 없으며 복구되지 않았다. 문서00 계정 정보는 stale, 문서02의13계정은 현재 hash와 일치한다. private 비밀번호 tool transcript 노출 사고는 report에 남아 있고 재출력·복사·password reset은 본 검토에서 하지 않았다. 이번 통과는 원문 retrieval, Tool/Workflow 승인 쓰기·실행 전체 suite, 실 provider, 기관 guardrail 정책 등록 또는 운영 배포를 증명하지 않는다. 공유 Obsidian 진행·설계 기록은 root가 이 검토 및 실제 전환 결과를 합쳐 갱신한다.
