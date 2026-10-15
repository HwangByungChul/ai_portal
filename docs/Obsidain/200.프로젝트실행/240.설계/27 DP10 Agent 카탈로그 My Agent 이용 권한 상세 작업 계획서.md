---
created: 2026-10-12
updated: 2026-10-12
status: local-unit-accepted
scope: DP10-01
---
# DP10 Agent 카탈로그 My Agent 이용 권한 상세 작업 계획서

## 요청과 목표

사용자는 전체 기능명세서의 조사 결과에 따라 상세 계획을 Obsidian에 저장한 뒤 개발을 진행하도록 승인했다. 목표는 실제 DB·인증·API·React 화면이 연결된 서비스 기능이다. 현재 개발 결과를 즉시 운영에 배포하라는 요청과 구분한다.

개발 전에 이 계획을 저장하고 진행 기록02에 착수를 기록했다. 본문은 구현 검토에서 확인한 요약의 기존 Agent 연결 관계를 포함해 읽기 쉽도록 정리했다. 이전 결정은 아래 연결 노트와 진행 기록에 보존한다.

- 사용자 홈 A안 업무 허브, 관리자 홈 관리 A안, 승인·검증은 관리 B안 목록·상세 패널을 유지한다.
- 제품 명칭은 생성형 AI 플랫폼이다. 사용자·관리 사이트는 별도 포트로 제공하고 local/dev/tb/prd 설정을 유지한다.
- 선행 결과: [[25 DP09-02 실행 자산 식별과 출처 봉인 구현 결과]], [[26 DP09-02 실행 출처 호환과 보존 검증 결과]].
- 상위 일정: [[15 전체 기능명세서 잔여 기능 개발 실행 계획]].

## 이번 수용 범위

DP10-01은 실행 가능한 고정 운영 Agent 두 종류의 카탈로그·개인 즐겨찾기·조직 내부 이용 대상 관리다. 초안 자산은 사용자 목록·상세·즐겨찾기·실행에 포함하지 않는다.

1. 사용자 AI 카탈로그: 이름·설명 검색, 일반 업무/지식 검색 범주, 서버 페이지, 상세 설명과 실행 상태.
2. My Agent: 개인 즐겨찾기 저장·해제·재조회. 즐겨찾기는 이용 권한을 부여하지 않는다.
3. 관리자: 조직의 활성 사용자 전체 또는 선택한 활성 사용자만 허용. 정책 변경·회수·권한 버전·감사 기록을 저장한다.
4. 서버: 기존 Agent 키, 연결 자산 UUID, 대화 생성, 실행 준비·claim·허가·저장·응답 스트림에 현재 권한을 적용한다.
5. 문서 요약: 기존 구현에서 `rules_rag` Agent를 사용한다. 규정 검색 이용 대상 정책을 요약 제출·재시도·worker에도 적용하고 관리자 화면에 안내한다.

동적 승인·게시 자산은 DP12 이후다. 모델은 DP13, Prompt/Tool/Workflow는 해당 실행 스키마 완료 이후 확장한다. 태그·평가/사용량 랭킹·복제·구독·부서·기한·권한 신청 승인·계열사 공유는 이번 완료 범위에 포함하지 않는다. 전체 DP10 또는 원문 F 요구사항의 완료로 표시하지 않는다.

## 저장·권한 계약

신규 SQL029만 추가한다. SQL000~028과 기존 데이터·snapshot·문서 ACL·비용 정산은 유지한다.

| 저장 대상 | 계약 |
| --- | --- |
| `portal.agent_access` | 조직/Agent별 `all` 또는 `restricted`, 활성 사용자 UUID 최대200개, revision. 정책 행이 없으면 기존 전체 허용을 유지한다. |
| `portal.agent_favorites` | 조직/사용자/Agent별 active와 revision. 회수된 즐겨찾기는 숨기되 보존한다. 해제는 허용하고 재허가 후 기존 선호를 다시 표시한다. |
| `portal.catalog_mutations` | 사용자 요청 UUID·action·대상·body·receipt를 INSERT만 허용해 보존한다. 동일 요청 재확인은 이전 receipt, 다른 body는409다. |

- 세 표 모두 `ai_owner` 소유·forced RLS. web/index/meter 직접 읽기·쓰기 권한을 주지 않는다.
- 정책 수정은 현재 관리 가능한 조직의 TADMIN 또는 관리 범위가 지정된 PADMIN만 허용한다. 서버에서 세션·조직·현재 권한을 다시 확인한다.
- 활성 계정·동일 조직의 활성 membership, 중복·NULL·다른 조직 UUID, 전체 허용과 비어 있지 않은 목록의 모순을 검증한다.
- 사용자별 요청 직렬화와 expected_revision CAS를 사용한다. 정책은 Agent 행 FOR UPDATE, 실행 허가는 같은 행 FOR SHARE로 순서를 보장한다.
- 권한 회수는 다음 허가 경계에서 차단한다. 이미 발사한 외부 요청의 비용은 보존하며 완료된 개인 이력의 소유 접근은 유지한다.
- 감사 기록에는 action·불투명 대상·revision만 저장한다. 지시문이나 이용 대상 목록을 감사 필드에 넣지 않는다. 감사/receipt 실패 시 변경 전체를 취소한다.

고정 capability: `agent_access_allowed(tenant,agent)`, `agent_access_guard(tenant,agent)`, `catalog_read(session,tenant,action,asset,body,period,mode)`, `catalog_write(session,tenant,action,asset,agent,body,trace)`.

## 실행 순서

### 1. DB·API

- 실패하는 수용 테스트부터 작성한다.
- 위 세 표와 네 capability를 추가하고 현재 허용된 Agent metadata만 투영한다. 읽을 때 정책·즐겨찾기 행을 만들지 않는다.
- `/agents` 필터와 최신 실행 함수의 기존 본문을 보존한 gate를 SQL029에 추가한다. 요약 제출·재시도도 현재 `rules_rag` 권한을 먼저 확인한다.
- API: GET `/api/v1/catalog/assets`, GET 상세, PUT 즐겨찾기, GET/PUT `/api/v1/admin/agent-access/{agent_key}`, GET 활성 이용 후보 `/api/v1/admin/agent-access/{agent_key}/members`.
- 검색 최대80자·literal substring, 범주 enum, limit1~50, UUID cursor, strict bool/정수·필드 검증, 중복/알 수 없는 query 거부, JSON 실측32768byte 제한을 적용한다.
- CSRF·fresh context·공유 요청 제한을 사용한다. 현재 권한 거부는403, 숨겨야 할 자산/초안/다른 조직은404, 수정 충돌은409로 처리한다.
- `app/catalog`, main router, 공통 오류, 기존 readiness helper를 연결한다. 새로운 Agent 실행 경로나 임의 SQL을 만들지 않는다.

### 2. 실제 React 화면

- 사용자 `/user/catalog`, `/user/my-agents`와 홈 바로가기를 연결한다. 홈 중심 탐색 순서를 유지한다.
- `CatalogPage`는 검색·구분·목록/상세·더 보기·즐겨찾기·empty/loading/error 상태를 제공한다.
- 카탈로그 실행은 `ChatLaunch.assetId`를 전달한다. 선택 Agent가 달라지면 이전 자산 UUID를 함께 전송하지 않는다. 동일 실행 재시도 payload를 유지한다.
- `AgentAccessEditor`는 현재 정책·활성 사용자 페이지·선택/해제·적용 확인을 제공한다. 규정 검색 정책의 문서 요약 적용을 안내한다.
- 저장 결과 불명확 시 같은 UUID/body로 재확인하고 입력을 고정한다.409는 최신 값을 읽고 사용자가 새 변경을 선택하도록 한다.
- 조직/계정/페이지 전환은 늦은 응답과 이전 개인 데이터를 폐기한다. 모바일·키보드 label·권한 회수 안내를 확인한다.
- 사용자 번들에 관리자 모듈·관리 API 구현이 포함되지 않는 분리 빌드를 검증한다.

### 3. 검증·로컬 이행·기록

- 정상 저장, 타 사용자/조직 은닉, 초안 거부, 현재 관리자 권한, 비활성 사용자, strict schema, 같은 UUID 재확인·충돌, 동시 CAS, 감사 실패 rollback을 검증한다.
- 신규 및 진행 중 실행의 claim/reserve/dispatch/finish/stream 차단, 기존 비용 보존, 규정 검색·요약·요약 재시도 gate를 검증한다.
- 실제 HTTP 서버 재시작 후 즐겨찾기·권한·요청 receipt 보존과 기존 기능 회귀를 검증한다. DB/HTTP와 브라우저는 같은 포트를 동시에 사용하지 않는다.
- 브라우저는 합성 계정·격리 DB·모의 제공자로 검색/상세, My Agent 재조회·출처 연결, 관리자 회수와 재허가, 조직 전환·모바일, 결과 불명확/409 처리를 검증한다.
- SQL028까지의 격리 DB에029 적용 후 기존 표의 전체 행 지문·29개 migration checksum 보존, 신규 세 표0행, 재적용 무변경을 확인한다.
- primary local은 private pg_dump와 소유 marker/port/name 검증 후029만 적용한다. 기존37표 행과 prior29개 checksum을 비교한다. primary reset·모의 자산/질문 생성·유료 호출은 하지 않는다.
- 프로젝트 소유 API8000·사용자5173·관리5174를 복구하고 health와 읽기 smoke, 자기 smoke 세션 logout을 확인한다.
- 구현26·시험27·안전 evidence와 계획15/설계23/로그02/요구 추적/AGENTS/단계 안내를 갱신한다. 실패·보정·미검증·운영 배포 여부를 분리한다. Obsidian 파일 저장 대사는 수행하되 GUI 렌더링은 별도다.

## 다음 순서와 완료 판정

DP10-01 수용 후 DP13 모델 Registry/Gateway 상세 계획으로 이어간다. 이후 Builder와 일반 자산 승인·게시가 완료되면 동적 자산 카탈로그를 연결한다. Entra ID는 선정·테스트 환경 준비 예정 상태이며 실제 기관 연동은 별도 검증이다. 전체 명세 출시일과 기관 수용 완료를 이번 단위 검증으로 확정하지 않는다.

최종 수용 증거는 [[26 DP10 Agent 카탈로그 My Agent 이용 권한 구현 결과]], [[27 DP10 카탈로그 권한과 보존 검증 결과]]에 기록한다.

## 2026-10-12 수용 결과

DB/API·화면·보존 이행·서비스 복구·기록을 완료했다. 최종 결과는 구현26·시험27을 따른다. 전체 DP10과 후속 기능은 미완료다.
