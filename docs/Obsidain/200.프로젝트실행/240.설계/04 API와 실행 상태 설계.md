---
title: API와 실행 상태 설계
created: 2026-10-04
updated: 2026-10-04
status: reviewed
stage: 240.설계
task: D240-03
user_review: pending
tags: [ai-platform, design, api, execution-state, errors, streaming]
---

# API와 실행 상태 설계

## 1. 결론·상태·입력

실행은 POST로 접수하고 GET으로 상태/결과를 조회한다. 답변 진행은 fetch 기반 SSE로 전달하되 **DB에 최종 결과를 저장한 뒤에만 완료**를 알린다. 같은 client_send_id의 재전송은 같은 실행을 반환한다. 취소 접수와 실제 종결, 통신 실패와 저장 실패를 구분하고 무권한 요청을 다른 조직/Agent로 우회하지 않는다.

D240-03 문서 작성/자체 점검 완료. 사용자 “네 진행 바랍니다”로D240-02 결과를 입력으로 API 설계를 진행했다. 이 문서는240 종합 검토 전 설계안이다. API/웹/DB/SDK 구현·OpenAPI 스키마 생성·서버 기동·모의/실제 요청 시험·유료 호출은 수행하지 않았다.

입력: [[200.프로젝트실행/240.설계/02 인증과 테넌트 권한 설계]], [[200.프로젝트실행/240.설계/03 데이터 모델과 RLS 설계]], [[200.프로젝트실행/220.요구정의/03 사용자 포털 요구사항]], [[200.프로젝트실행/220.요구정의/04 관리자 포털 요구사항]], [[200.프로젝트실행/220.요구정의/06 요구사항과 검증 추적표]], [[200.프로젝트실행/230.분석/05 합성 데이터와 평가 기준]].

| 전달안 | 장점·부담 | 이번 선택 |
|---|---|---|
| A. 접수POST + fetch SSE + 상태GET | 조직 헤더/쿠키를 유지하면서 부분 답변 표시, 끊김은GET으로 확인. 이벤트 처리 필요 | **권고**: 부분 실패/진행 요구와 일치 |
| B. 접수POST + 주기GET만 | 구현이 단순하고 최종 결과/상태 확인 가능 | SSE 끊김의 복구 경로. 초기 부분 응답 검증을 대체하지 않음 |
| C. WebSocket | 양방향 통신 가능 | 추가 프로토콜/운영 복잡도가 있어 이번에 도입하지 않음 |

네이티브 EventSource 대신 fetch로 text/event-stream을 읽어 필수 X-Tenant-ID를 명시한다. 서버는 연결 유무와 무관한 접수 실행 상태를 관리한다. 별도 Gateway·메시지 브로커·새 Agent 유형을 추가하지 않는다.

## 2. 공통 API 계약

기본경로는 `/api/v1`, health는 `/health`다. JSON은 UTF-8, ID는UUID, 시각은UTC ISO8601, enum은아래정의값을쓴다. URI/요청/오류를무작위자원탐색이나DB원문노출경로로사용하지않는다.

- 인증은D240-01의HttpOnly session cookie만 사용한다. role/user_id/DB자격/모델/API키를 요청으로 지정하지 않는다.
- tenant API는단일 X-Tenant-ID를 필수로 받고 현재 소속/역할을 검증한다. auth/me 목록과명시된platform 제어만예외다. 관리API도같은헤더를쓴다.
- 변경 요청은정확한Origin 및 X-CSRF-Token 검사. 로그인은JSON + X-Requested-With: ai-portal + Origin을검사한다. logout의반복무효세션은D240-01 예외를따른다.
- success JSON은 `data`와 `meta={request_id,tenant_id,server_time}`. tenant_id는검증된선택조직만반환하고,auth/platform은null이다. 에러도서버 request_id를반환한다. SSE/원문다운로드는고유콘텐츠형식을사용한다.
- request_id는서버의HTTP요청마다새로발급한다. 반환헤더 X-Request-ID와meta를일치시킨다. 클라이언트가보낸동일request_id를중복실행키로사용하지않는다.
- 목록은 `items,next_cursor`, 기본20/최대50개. opaque cursor는조직·주체·조회종류에묶고현재 권한을재검사한다. 정렬은created_at+UUID로안정화하며권한없는전체count를제공하지않는다.
- 변경가능한설정/role/Grant는expected_revision CAS를쓴다. 형식검증후 현재접근권한을검사하고,같은허용자원의revision불일치만409로알린다. 무권한 자원의현재revision은반환하지않는다.
- 모든개인/세션/근거/관리응답은Cache-Control: no-store. 비밀값/개인본문을URL query·예외·access log에넣지않는다. 캐시는현재ACL을대체하지않는다.

## 3. API 목록과 입력·권한·응답

아래 `{...}`는UUID path parameter다. 별도언급이없으면현재tenant의활성인증사용자만허용한다. “관리”는TADMIN 또는명시관리소속PADMIN이며개인본문read ACL을자동부여하지않는다. 경로는계약이며실제로라우트를등록하지않았다.

### 3.1 인증·본인조직

| ID | Method·경로 | 입력/권한 | 성공 응답 |
|---|---|---|---|
| API-01 | GET /health | 비민감 생존확인,tenant불필요 | 200 status=ok. DB주소/키/내부구성 없음 |
| API-02 | POST /auth/login | login_id,password·Origin/지정헤더·실패창 | 200 본인 user_id/display_name, session_expires_at, csrf_token + Set-Cookie. 인증token JSON 없음 |
| API-03 | GET /auth/me | 유효session,tenant불필요 | 200 본인정보/만료/CSRF. 자동poll은유휴연장안함 |
| API-04 | POST /auth/logout | CSRF/Origin,현재 session회수 | 200 logout_confirmed=true + cookie삭제. DB회수실패503 |
| API-05 | GET /me/tenants | 유효session,본인활성소속만 | 200 tenant_id/display_name/effective_role/can_manage. PADMIN관리대상만관리허용 |

로그인성공이활성조직보유를보장하지않는다. 목록이비면조직없음상태로표시한다. 전역회원가입/계정정지/비밀번호변경API는추가하지않는다.

### 3.2 사용자·대화·근거

| ID | Method·경로 | 입력/권한 | 성공 응답 |
|---|---|---|---|
| API-06 | GET /agents | 현재 조직허용general/rules_rag | 200 agent_key/name/description/config_version/available/safe_block_reason. 키/내부system지시문 없음 |
| API-07 | POST /conversations | 본인,선택적client_conversation_id UUID | 201 conversation_id/tenant_id/created_at. 같은clientID 재전송은200기존본인대화 |
| API-08 | GET /conversations | 본인목록,cursor/limit | 200 최소목록·시각/최근state. 타인없음 |
| API-09 | GET /conversations/{conversation_id}/messages | 본인+현재 조직,cursor/limit | 200 질문/답변·run state/answer_kind·현재 권한으로표시한근거 |
| API-10 | POST /runs | client_send_id,conversation_id또는null,agent_key,prompt,document_refs선택 | 202 run_id/conversation_id/state/stage/revision/is_terminal/replayed=false. 같은 전송은200/202기존run |
| API-11 | GET /runs/by-send/{client_send_id} | 본인+현재 조직 | 200 접수된run참조/현재state. 응답 미수신시접수여부확인용 |
| API-12 | GET /runs/{run_id} | 본인+현재 조직 | 200 저장 state/stage/revision/answer_kind/content_status/usage_status/result(허용최종 결과만) |
| API-13 | POST /runs/{run_id}/cancel | 본인+현재 조직 | 진행취소접수202,즉시취소/이미종결200. 실제state와cancel_requested_at |
| API-14 | GET /runs/{run_id}/events | 본인+현재 조직,X-Tenant-ID,Accept:text/event-stream | 200 SSE snapshot/draft/status/terminal. 무권한은연결시404/401/403 |
| API-15 | GET /runs/{run_id}/evidence | 본인run + 현재source ACL | 200 허용ordinal/title/version/location/quote/link만. 회수된항목은내용없는unavailable표시 |
| API-16 | GET /runs/{run_id}/evidence/{ordinal}/source | 본인run + exact version/source ACL | 200 text/plain UTF-8 원문,Content-Disposition:attachment. 서버파일path/정적URL 없음 |
| API-17 | GET /documents | 현재조회가능한published버전만 | 200 document_id/version_id/title/visibility/safe_version_label. 조직/개인/공유범위필터 |

ordinal은0부터시작하는answer_evidence 순서정수로UUID가아니며범위0~19다. source의원소유tenant는저장된증거FK에서서버가얻는다. 링크사용자에게원소유tenant를수정해읽는권한을주지않는다. 공유조회헤더는수신B를유지한다. title/quote와원문은현재ACL이허용할때만반환한다.

document_refs는최대5개의 `{document_id,version_id}`이며문서범위를좁히는선택이다. 생략하면현재허용published자료를검색한다. 명시한무권한/삭제버전은질의임베딩/생성전에404로차단하고다른허용문서로자동대체하지않는다. 원소유tenant/Grant는서버가허용범위에서해결한다. 검색/버전선택·최종인용렌더링의상세는D240-05에서확정한다.

### 3.3 조직관리

| ID | Method·경로 | 입력/권한 | 성공 응답 |
|---|---|---|---|
| API-18 | GET /admin/memberships | 관리,cursor/limit | 200 현재 조직user_id/display_name/role/active/revision. 다른조직소속/비밀번호 없음 |
| API-19 | PATCH /admin/memberships/{user_id} | 관리,active,expected_revision. TADMIN은USER대상만 | 200 해당조직상태/revision. 전역계정/B소속자동정지 없음 |
| API-20 | PUT /admin/memberships/{user_id}/role | PADMIN관리소속,role USER/TADMIN,expected_revision | 200 새role/revision. 자기/다른PADMIN권한변경·PADMIN부여 불가 |
| API-21 | GET /admin/documents | 관리,cursor/limit | 200 opaque문서ID/범위/처리상태/삭제/버전·revision. 개인title는read ACL있을때만 |
| API-22 | POST /admin/documents | 관리,multipart file+metadata(client_upload_id,title,visibility,owner_user_id,reader_ids) | 202 document/version/index/job ID와queued또는reused상태. 등록≠색인완료 |
| API-23 | POST /admin/documents/{document_id}/versions | 관리,multipart file+metadata(client_upload_id,title,expected_revision). private는본문ACL도필요 | 202 새version/index/job. owner/scope/readers변경 없음 |
| API-24 | DELETE /admin/documents/{document_id} | 원 소유 조직관리,expected_revision | 200 access_state=deleted,cleanup_state=pending. 이미삭제되고관리허용이면200동일상태 |
| API-25 | GET /admin/jobs | 관리,cursor/limit | 200 opaque job/doc/version/index ID·stage/state/시각/safe_error_code. 본문/title/rawstack 없음 |
| API-26 | GET /admin/jobs/{job_id} | 관리,현재 조직 | 200 최소상태·retry_allowed/safe_reason,publication_state. 권한회수시본문없음 |
| API-27 | POST /admin/jobs/{job_id}/retry | 관리,client_retry_id,expected_revision. 현재작업/문서/Agent/한도 | 202 새Job/원Job연결,중복200/202기존Job. 불명call미해결이면409 |
| API-28 | GET /admin/share-recipients | 원소유관리조직,합성A/B의활성수신후보만 | 200 설정된recipient tenant_id/display_name. 관리소속/사용자/내용목록 아님 |
| API-29 | GET /admin/documents/{document_id}/versions/{version_id}/grants | 원 소유 조직관리,org문서 | 200 버전별Grant최소목록/active/revision |
| API-30 | POST /admin/documents/{document_id}/versions/{version_id}/grants | 원소유org관리,recipient_tenant_id,expected_publication_revision | 201 exact-version Grant,같은활성Grant중복200기존값. private/재공유거부 |
| API-31 | DELETE /admin/grants/{grant_id} | 원소유관리,expected_revision | 200 active=false/revoked_at/revision. 이미회수된동일허용Grant는200 |
| API-32 | GET /admin/agents/{agent_key} | 관리,general/rules_rag | 200 허용표시명/설명/기본지시문/enabled/config_version |
| API-33 | PATCH /admin/agents/{agent_key} | 관리,name/description/instructions/expected_revision | 200 저장설정/config_version. model/key/tool/URL/권한필드 거부 |
| API-34 | PUT /admin/agents/{agent_key}/availability | 관리,enabled,expected_revision | 200 변경enabled/config_version. 재개도공통중지/한도우회없음 |
| API-35 | GET /usage/me | 본인+현재 조직,기간기본10월 | 200 본인생성/임베딩·확정/예약/불명·기본한도상태. 조직전체잔여없음 |
| API-36 | GET /admin/usage | 관리,cursor/limit·현재기간 | 200 조직합계/최소call상태/예약/불명,개인질문/대화없음 |
| API-37 | GET /admin/budget | 관리 | 200 현재 조직배정/local cap/예약/확정/차단/revision |
| API-38 | PUT /admin/budget | 관리,local_cap_krw,expected_revision | 200 상위배정이하조직한도. 원장/프로젝트cap변경 없음 |

문서/Job관리API는개인운영정보와본문반환을구분한다. Jobstate/publication pointer·RLS/DBrole·원장직접삽입/수정API를제공하지않는다. 문서삭제는소유조직에서만되며수신공유목록을원본운영목록으로취급하지않는다.

### 3.4 제한된플랫폼공통 운영

| ID | Method·경로 | 입력/권한 | 성공 응답 |
|---|---|---|---|
| API-39 | GET /platform/summary | 현재PADMIN + global_usage_read,tenant불필요 | 200 프로젝트합계/예약/불명·공통중지/승인30,000원. 개인질문/전조직본문 없음 |
| API-40 | PUT /platform/availability | 현재PADMIN + global_stop_write,enabled,expected_revision | 200 공통중지/재개상태/revision. cap증액/조직별권한확대없음 |
| API-41 | PUT /platform/tenant-budgets/{tenant_id} | PADMIN + 해당관리소속,allocated_cap_krw,expected_revision. X-Tenant-ID는같은조직 | 200 프로젝트상한/잔여조건내조직배정,개별usage변조없음 |

API-41은조직별배정경로이므로tenant문맥을필수로한다. API-39/40만공통 운영문맥이다. recipient_tenant_id는Grant수신처이고요청의현재소유조직을변경하는입력이아니다. 일반HTTP body에owner_tenant_id/role/system principal을허용하지않는다.

## 4. 식별자·중복전송·변경확인

주요응답객체는아래필드를공통으로쓴다. 이표는논리계약이며아직OpenAPI/코드를생성하지않았다.

| 객체 | 공통필드·표시규칙 |
|---|---|
| RunView | run_id/tenant_id/conversation_id/agent_key/config_version/state/stage/revision/is_terminal/answer_kind/content_status/execution_mode/usage_status/error_code/created_at/ended_at/result |
| result | null 또는message_id/text/evidence. completed라도현재표시권한이없는자료는D240-05의render_current_answer 결과에따라본문/인용을차단·정제 |
| EvidenceView | ordinal/availability. available만document_id/version_id/title/location/quote/source_link. unavailable에는ordinal/일반안내만,원소유/version/title/quote 없음 |
| JobView | job_id/document_id/version_id/index_id/state/stage/revision/publication_state/retry_allowed/safe_reason/created_at/ended_at. 개인title/원문경로/raw오류 없음 |
| MutationView | 변경대상불투명ID/허용변경값/revision/server_time,저장성공뒤에만반환 |

expected_revision은양의정수,unknown필드는422로거부한다. 금액입력은음수/NaN/Infinity 없는Decimal 문자열로받고비교/예약은서버numeric/Decimal로한다. 최종상한/반올림은D240-04의계약을따른다. 등록시org문서owner는현재등록주체,private는같은조직의지정owner/reader를검사하고org에private reader설정을섞지않는다. 실제/모의실행모드도클라이언트입력필드가아닌서버실행설정이다.

| 식별 | 생성/용도 | 경계 |
|---|---|---|
| request_id | 서버의HTTP1회추적 | 전송중복판정키아님,provider call ID아님 |
| client_send_id | 사용자전송1건의UUID,응답전까지유지 | `(tenant,user,id)` UNIQUE. 별개의정상전송은새UUID |
| conversation_id / run_id | 서버생성대화/실행UUID | 같은조직+owner. 조직전환으로이동/다른owner연결없음 |
| client_conversation_id | 선택적대화생성재전송UUID | `(tenant,owner,id)` UNIQUE,제목/개인본문보관안함 |
| client_upload_id / client_retry_id | 관리자등록/재처리조작1건의UUID | `(tenant,initiator,id)` 범위별UNIQUE + request_hash. 같은ID다른내용409 |
| document_id / version_id / index_id / job_id | 서버생성원문/색인/처리UUID | 실제복합tenant/FK와공개 gate. 평가D/EV/R ID와별도 |
| call_id | 중앙AI의provider 시도1회UUID | run/Job/op/attempt에묶음. HTTP재조회·SSE연결마다새로만들지않음 |
| revision / config_version | 서버의지속변경버전 | 상태순서/CAS. 클라이언트임의새번호아님 |
| stream_epoch / seq | 현재process의단일run draft buffer세대/순서 | 영속전송완료증거아님,새연결snapshot은전체draft대체 |

POST /runs는현재 인증/조직/자원권한을먼저확인하고기존client_send_id를찾는다. 요청hash에는원요청의prompt·agent·conversation요청값·정렬한document_refs를포함하고세션/전송시각/서버request_id는제외한다. prompt는공백여부만검사하고hash단계에서임의정규화하지않는다. 처음conversation_id=null이면대화생성과입력/run접수를동일트랜잭션으로저장하고재전송에서는처음생성한conversation을반환한다. 같은clientID 다른입력은409,provider0이다.

접수 전 provider 호출 없이 로컬 tokenizer로 필수 system/질문/허용 history의 token을 검사한다. 일반은6000, RAG는 검색 문맥2000을 남긴 base4000 상한이다. 기본 문맥은 최근본인메시지 최대6개 중 이한도에맞는최근완전메시지부터선택하며 질문/system을임의절단하지않는다. 질문/system만으로넘으면422,provider0이다. RAG 검색 뒤의 문맥은허용자료안에서2000token이하로조립한다. 최종직렬화/모델부가값검사에서6000을초과하면생성call은하지않고failed+TOKEN_LIMIT_EXCEEDED를기록한다. 그때이미실행된질의임베딩usage는보존하므로이후단계의token거부를모든provider0으로표시하지않는다. 정확tokenizer/부가여유·후보선택은D240-04/05에전달한다.

응답을못받으면먼저by-send GET을한다. 존재하면그run을추적한다.404면같은 전송ID/입력으로최대1회접수재전송한다. 새 ID로자동재실행하지않는다. 기존run이terminal이면200,접수/진행이면202와replayed=true다. 재조회가Agent중지뒤에도동일한이미허용본인run의상태를보여줄수있지만신규 provider허가는현재정책으로다시검사한다.

upload/retry도hash+UNIQUE와활동index/Job제약으로한번만접수한다. 단순버튼비활성화만중복 방지로쓰지않는다. 원장call/event는D240-02/04의시스템중복경계를따른다. 일반PATCH/PUT의통신결과불명은먼저GET현재revision을확인하고새값을자동덮어쓰지않는다. 삭제/회수반복도현재 권한을재검사한다.

**D240-02 보완 데이터 전달:** conversations에client_conversation_id, runs에origin_session_id·현재stage·실제/모의표시·execution_epoch/heartbeat_at/lease_expires_at, jobs에retry_of_job_id 및revision을추가한다. 대응UNIQUE와state enum을D240-08에서합친다.

관리자upload/retry의재전송은 **security.operation_receipts**에별도로저장한다. PK는 `(tenant_id,initiator_user_id,operation_kind,client_operation_id)`,필드는request_hash·문서/version/index/job의불투명참조·created_at이다. request_hash만보관하며본문/제목/파일명/원문hash/비밀은넣지않는다. 기존30개논리테이블에서이접수정본1개를추가하는설계보완이며새UI/서버가아니다. 원본테이블raw접근은금지하고현재관리권한의제한함수로접수/최소결과를조회한다. 결과payload와같은트랜잭션으로저장한다.

이렇게하면private 본문read ACL이없는등록관리자도반복upload의접수ID를확인할수있다. private document_versions를읽어중복검사하거나관리자본문우회를만들지않는다. 같은operation ID는같은결과를반환하고,다른ID라도이미완성된동일원문/index를재사용한결과를자기receipt로연결할수있다. 원문동일성/파일version재사용의실제판정은D240-05에서정한다. 실제DDL/DB행/fixture는생성하지않았다.

## 5. run 상태·답변 종류·최종 저장

### 5.1 저장 상태

| state | 종결 | 의미·허용전이 |
|---|---|---|
| accepted | 아니오 | 접수저장완료/provider미접수. running/cancelled/blocked/failed/interrupted로전이 |
| running | 아니오 | retrieval/generation/finalizing 진행. completed/failed/blocked/cancel_requested/interrupted로전이 |
| cancel_requested | 아니오 | 취소의지저장,현재call중단확인/정산중. cancelled 또는 interrupted로전이 |
| completed | 예 | 답변/근거및run완료를DB에commit. answer_kind=answer 또는insufficient_evidence |
| failed | 예 | 입력접수후검색/제공자/결과저장등명확실패. 안전한error_code저장 |
| cancelled | 예 | 신규call차단과서버실행종결확인. 실제기발생 usage보존 |
| blocked | 예 | 접수후정책/권한/Agent중지/한도로계속실행·공개불가. 콘텐츠없는사유만 |
| interrupted | 예 | 서버재시작/불확실한수행으로유효한최종 답변없음. usage_status가unknown일수있음 |

stage는 queued/authorization/retrieval/generation/finalizing/terminal이며state와별도다. 일반Agent는retrieval을사용하지않는다. 단계의숫자진행률을임의타이머로100%까지올리지않는다.

answer_kind는answer/insufficient_evidence/null. 근거부족은권한내검색이정상완료되어충분한근거가없는결과이며completed+insufficient_evidence로저장한다. 검색 장애는failed+SEARCH_FAILED로구분한다. 무권한 자원요청은접수전404 또는접수후blocked이고근거부족답변으로감추지않는다. Q20의answer/hold/deny는평가라벨로보존하고APIstate로직접복사하지않는다.

content_status는pending/partial/final/unavailable. partial은현재연결의미저장draft,final은정상commit된답변,unavailable은종결실패/차단또는현재표시권한이없는결과다. usage_status는none/estimated/final/unknown으로별도관리한다. cancelled/failed/completed라고비용을0또는확정으로추정하지않는다. 실제/모의는 execution_mode=real/mock으로명시한다.

### 5.2 종결 CAS·저장 실패

accepted→running은서버worker가run revision/epoch를CAS로claim한후에만가능하며그전에는provider permit을발급하지않는다. 단일FastAPI process/worker를기본실행구성으로하고유료진행중auto reload는사용하지않는다. run lease60초/heartbeat20초·epoch로구worker의최종쓰기를차단한다. heartbeat/lease기한초과나프로세스재시작의미종결run은저장된call증거로interrupted/차단종결을판정하며새provider를자동호출하지않는다. 상태조정은본문을읽거나권한을확대하는경로가아닌metadata전용제한 함수다.

완료/취소/차단은D240-02의authority잠금순서와run revision으로단일 종결을결정한다. 완료는현재 session/소속/Agent·참조source허가를검사한뒤run이running인경우만답변message/근거+completed를같은트랜잭션으로commit한다. commit후terminal event를전송한다. 이미terminal인run은새답변으로덮어쓰지않는다.

최종 저장 실패시새provider호출을하지않는다. 메모리에있는동일결과의안전한DB저장은새트랜잭션에서최대1회재시도하며,재시도도실패하면현재state를CAS로확인하여running이면failed+RESULT_SAVE_FAILED, cancel_requested이면interrupted로metadata종결한다. 이미terminal이면그결과를보존한다. DB전체불가면서버가종결을확인했다고말하지않고delivery_error를전달한다. UI는“결과 저장 확인 필요”로표시하고GET재조회한다. 복구후lease/실제증거에따라interrupted 처리하며미저장 답변을completed로복구하지않는다.

이미기록된call/usage는답변저장 실패로삭제하지않는다. GET에서running이보여도heartbeat/lease의기한지난실행은새로운완료주장을하지않고복구판정을거친다. 과거답변본문·인용의재표시는D240-05의현재 권한렌더링계약을모든GET/terminal결과에공통적용한다.

## 6. 취소·중지·로그아웃·연결종료

| 사건 | 서버행동 | 사용자표시 |
|---|---|---|
| accepted run 취소 | provider미접수임을검사,즉시cancelled commit | 200 취소완료,기발생call없는경우만usage none |
| running run 취소 | cancel_requested commit→provider/검색에중단전파→종결/정산 | 202 취소요청접수,이후GET/SSE로종결확인 |
| 완료commit먼저/취소요청나중 | completed유지,새cancel flag없음 | 200 이미완료. 완료/취소동시표시안함 |
| 취소접수commit먼저/모델응답나중 | completed CAS불가,늦은응답최종 답변저장/전송안함 | cancelled또는interrupted.usage는실제로정산 |
| Agent/공통중지·권한회수 | 신규call차단,진행call에중단요청·공개재검사,정제blocked/종결 | 중지/권한변경과실제호출종료를구분 |
| SSEdisconnect/패널닫기/탭닫기 | 해당구독만정리,접수run은자동취소하지않음 | 연결끊김/서버상태확인.완료/무료아님 |
| 조직A→B전환 | A구독/캐시정리,전환세대증가. A실행owner/tenant유지 | B에서A의늦은이벤트/결과폐기. A실행취소는별도A권한요청 |
| 로그아웃/원session만료 | 새HTTP거부·구독종료. 해당session의미종결채팅run에중단요청,추가 provider/완료공개차단 | 로그인필요.중단요청을비용0으로표시안함 |

이번상태설계에서**채팅run의origin_session 유효성**을신규단계/provider허가·최종공개의조건으로한다. session이회수되면metadata만의취소/차단종결및기발생 usage정산을허용하고본문/새call은허용하지않는다. 이후재로그인하면본인현재 조직의저장된종결상태를조회할수있다. 이metadata처리예외를D240-02의제한 함수계약에전달한다.

색인Job은D240-01대로HTTPsession과수명이독립이며로그아웃만으로삭제/취소하지않는다. 현재initiator 계정/소속/작업권한과문서/Agent/공통정책을검사한다. provider의원격중단을보장하지않으며최대timeout뒤에도사용량불명은보존한다. 중지버튼은취소/차단정책이지원장삭제명령이아니다.

## 7. Job·색인공개 상태

| Job state | 의미·전이/재처리 |
|---|---|
| queued | 접수저장,아직claim안됨→running/blocked/interrupted |
| running | 유효lease에서parse/chunk/embed/extract/validate/publish. 현재 허가검사→completed/failed/blocked/interrupted/needs_review |
| completed | 검증과publication pointer/Job종결commit.새index가실제공개됨 |
| failed | 원인확인된실패. 현재 권한/한도와안전단계검사후새Job접수가능 |
| blocked | 삭제/권한회수/중지/한도차단.조건이복구되고현재 허가가있을때만새재처리 |
| interrupted | lease/프로세스중단,최종공개없음. 유료dispatch불명없음을확인한안전단계만수동재처리 |
| needs_review | dispatched call의실제결과/usage가불명. 자동/일반UI재처리불가,시스템대조후안전한판정으로이동 |

queued/running만활동중이다. 실패/중단/차단된Job을재처리할때새job_id와retry_of_job_id를만들고이전종결이력은보존한다. 동일index/진행Job/client_retry_id는같은참조를반환한다. 이미동일pipeline index가완료되면reused=true로기존완료Job을반환하며재임베딩하지않는다. needs_review는증거를대조하는운영/시스템절차로만interrupted/failed등안전상태를판정하고사람이usage를임의0 수정하는API를만들지않는다.

index_build는staging/building/validated/published/failed/interrupted 상태를사용한다. publications의pointer가해당index를가리킬때만공개다. 문서관리응답은processing_state와publication_state를별도로반환한다. 새버전실패가다른유효버전을숨기거나Job진행률100으로위조하지않도록D240-05에서현재검색버전/cleanup세부를정한다.

## 8. SSE·재연결·권한재검사

### 8.1 이벤트와신뢰순서

SSE는UTF-8 `event`와JSON `data`를사용한다. 각data에는run_id,검증된tenant_id,stream_epoch,seq,server_time이있다. events GET은provider실행명령이아니라이미접수된run의구독이다. 서버처리는HTTP POST 수명/구독수와분리한다.

| event | 내용 | 계약 |
|---|---|---|
| snapshot | 저장 state/stage/revision + 미종결run의현재유효buffer가있으면draft전체/seq | 초기에전체draft를대체. POST→구독사이토큰누락을보완 |
| draft_delta | 권한검사된추가본문/seq | partial/미완성.최종message나완료증거아님 |
| status | state/stage/revision | 취소접수/정책차단/오류등metadata만 |
| terminal | DBcommit된종결state/revision,final_message_id선택 | UI는GETcanonical결과/현재근거ACL을확인. SSE EOF와구분 |
| delivery_error | STREAM_DELIVERY_FAILED/RESULT_SAVE_UNCONFIRMED/ACCESS_REVOKED 등정제code/request_id | 저장상태를위조하지않음.본문/title/source정보없음 |

buffer는run당최대64KiB의휘발성draft로두고,최대250ms단위로묶어전송한다. 구독은현재전체snapshot 뒤의seq부터받으며중복seq는무시한다. seq누락/다른epoch/브라우저재연결은draft이어붙이기를중지하고저장 state를GET한다. 새buffer snapshot이있으면전체를대체하고,없으면부분재생을주장하지않고최종 결과를기다린다. 종결뒤buffer는폐기하고재연결에는저장 state/terminal metadata만보내며본문은현재 권한의GET결과를사용한다. 별도영속event replay저장소/Last-Event-ID 재생은이번MVP에추가하지않는다.

### 8.2 회수와실패

연결처음과**각본문batch/snapshot 전송전**에현재 session/소속·사용자run소유·Agent/관련source Grant/버전유효성을짧은DB검사로확인한다. 읽기검사와회수의순서는D240-02 authority잠금/최신statement를따른다. 하나라도회수/검사실패면새본문을전송하지않고구독을종료하며run중단/차단정책을전파한다. 15초keepalive에도권한을검사하되session 유휴시간을연장하지않는다. 주기권한검사/DB읽기실측부담은D240-07 측정대상이다.

이미전송된본문이나검사직후OS/network buffer에전달된본문을되돌릴수있다고주장하지않는다. 신규요청/다음batch/최종공개는회수commit을반영한다. DB검사가불가능하면fail-closed하여전송을보류/종료한다. heartbeat timeout으로provider완료나cancelled를추정하지않는다.

HTTP200stream 시작후발생한오류는status/delivery_error로알리고header를500으로바꿨다고표시하지않는다. 스트림EOF/에러후GET /runs로서버state를확인하며2초간격poll로종결을기다릴수있다. 단순 GET 5xx/연결실패만1초/3초대기최대2회재시도,401/403/404는중단,429는Retry-After를따르고새call을발사하지않는다. 같은클라이언트run의SSE중복연결은이전구독을닫고새1개로대체하며추가 provider비용이없다.

AbortController는SSEfetch/조회수신을끝내는것이며업무취소가필요하면별도POST cancel을한다. 프론트는현재tenant와선택세대/run_id를비교하여A→B전환전이벤트를B의질문/이력/근거에쓰지않는다. 재조회도현재 권한검사를통과해야한다.

## 9. HTTP·오류·비노출 계약

JSON오류형식은 `error={code,message,field_paths,retryable}, meta={request_id,tenant_id,server_time}`다. field_paths에는필드명만넣고invalid input값/개인본문을echo하지않는다. retryable은같은안전한요청을확인/재조회할수있는지이며유료재실행허가가아니다.

| HTTP | code | 처리/정보경계 |
|---|---|---|
| 400 | TENANT_CONTEXT_INVALID, MALFORMED_REQUEST | tenant중복/누락/형식·잘못된JSON,기본조직대입안함 |
| 401 | AUTH_REQUIRED, SESSION_EXPIRED, LOGIN_FAILED | 재로그인. 로그인존재/비활성여부의개별사유외부비노출 |
| 403 | TENANT_ACCESS_DENIED, ROLE_FORBIDDEN, CSRF_REJECTED | 인증후조직선택/행동불가. 조직존재·개인자원내용없음 |
| 404 | RESOURCE_UNAVAILABLE | 자원미존재/무권한/회수/타tenant ID의일관된응답.숨겨진title/version/존재여부없음 |
| 409 | REVISION_CONFLICT, SEND_ID_CONFLICT, OPERATION_ID_CONFLICT | 현재허용자원의수정경합/같은ID다른입력,권한확인전revision반환안함 |
| 409 | AGENT_STOPPED, PLATFORM_STOPPED, QUOTA_EXCEEDED, REVIEW_REQUIRED | 신규실행/재처리차단,자동모델/조직우회없음.일반사용자에게다른조직잔여액없음 |
| 413 | PAYLOAD_TOO_LARGE | 제한payload/file/문자초과,provider미호출 |
| 415 | UNSUPPORTED_MEDIA_TYPE | JSON/multipart/TXT/Markdown제한,OCR/Office자동변환없음 |
| 422 | INPUT_INVALID, TOKEN_LIMIT_EXCEEDED | 필드형식/빈질문/완성입력token상한,안전한field_paths만 |
| 429 | RATE_LIMITED, EXECUTION_CAPACITY_EXCEEDED | Retry-After 초,현재 조직최소 안내.중복run은새slot없이조회 |
| 500 | INTERNAL_ERROR | request_id/일반안내. DB/SDK/raw stack/SQL/key없음 |
| 503 | STORAGE_UNAVAILABLE, SERVICE_UNAVAILABLE | 접수/변경/최종 저장확인불가,성공위조없음.새 실행자동재시도없음 |

401에는 `WWW-Authenticate: Session realm="ai-portal"`을이포털의cookie session challenge로사용한다. bearer token 요청/응답으로전환하지않는다. 정상조회GET은200,생성201,비동기접수202를쓰며상태변경실패는2xx로감추지않는다. successful run의근거부족은200결과+answer_kind이며 HTTP404/검색 장애와구분한다.

provider timeout/검색오류는이미접수된run의failed/interrupted + safe code이고상태조회HTTP자체는200이다. GET실패의503은현재run이failed라고단정하는응답이아니다. 운영로그/원장에는비밀·본문·민감title를남기지않고provider status/request ID의필요최소값만시스템으로기록한다.

## 10. MVP 고정상한·시간·재시도

아래는2026-10-31/최소비용MVP를위한설계선택값이다. 실제환경성능/품질검증을완료한수치가아니다. D240-04/05/07에서연결해종합점검하고요구범위를바꾸면이력을남긴다.

| 항목 | 기준 |
|---|---|
| 질문 | 공백 불가,최대4000 Unicode codepoint + UTF-8 16KiB. JSON request전체32KiB |
| 대화문맥/모델입력 | 최근본인메시지최대6개,최종조립입력6000token상한(system/질문/history/RAG포함),출력1024token. 접수전필수입력/허용history를로컬tokenizer로검사. RAG문맥은최대2000token별도배분,초과처리는아래정의 |
| Agent 편집 | name80자/description500자/instructions2000자. 모델/키/도구/URL입력금지 |
| 문서등록 | 한요청TXT/Markdown1파일,원문128KiB/UTF-8 40000문자이하,metadata16KiB·multipart전체160KiB. title200자,reader_ids최대10 |
| 문서/검색참조 | 평가논리6종/7버전유지,기본규모5~10논리문서. document_refs최대5,근거최대20. 임베딩batch/token/청킹상한은D240-04/05의책임 |
| 실행동시성 | user별미종결run1개,tenant별2개,프로젝트4개. tenant색인Job1개/프로젝트2개,provider 진행call tenant1개/프로젝트2개(생성/임베딩합산) |
| 접수율 | 인증된user/tenant별신규run 1분10회,등록/재처리1분5회. HTTP조회1분120회. DB원자창으로구현,로그인창은D240-01/02유지 |
| 구독/조회 | 브라우저run SSE1개,user SSE2개. poll2초,keepalive15초,draft batch≤250ms/64KiB. 숨긴탭은poll정지 |
| HTTP요청대기 | auth/일반JSON10초,upload30초. 접수후작업은이HTTPtimeout과별도 |
| provider/작업기한 | 생성60초/임베딩30초의시도기한,run전체180초,Job처리300초. 취소/중지즉시종결보장없음,timeout이면usage확정여부별도 |
| DB/pool | statement_timeout 5초,lock_timeout 2초,idle_in_transaction_session_timeout 5초. web4/index2/meter2 connection,overflow0,pool대기2초 |
| 재시도 | provider 자동재시도0(암묵SDK재시도도해제). GET일시실패2회,run응답불명같은ID접수재전송1회,안전DB저장/경합1회. 관리자실패Job은현재검사된수동재처리 |

요청동시상한은UIcount가아니라D240-02의account/tenant/project 행잠금과저장 state로판정한다. 로그인성공이후IP공유자만으로여러조직쿼터를합치지않는다. provider 슬롯은call/permit과함께원자예약하고불명call을즉시무료/미실행으로해제하지않는다. 확정종결/대조와slot 해제는D240-04가정한다.

rate windows는D240-02의login_windows를purpose별로구분하여재사용하고HMAC user/tenant/purpose key와고정창을쓴다. 기존login 실패/IP창과namespace를공유해reset하지않는다. 조회/SSEkeepalive는session 유휴시간을연장하지않는다. 이필드보완도D240-08 데이터계약에반영한다.

## 11. 요청/상태 검증 입력

아래는실행할시험의입력/기대값이며실제 시험은모두**미수행**이다. D240-07에서관련V/ACL/F fixture·증거에연결한다.

| 입력ID | 행동 | 기대값·연결 |
|---|---|---|
| REQ-01 | 빈질문/큰payload/지원외파일/접수전필수입력token초과 | 413/415/422정제오류,접수전provider0; V-004/028/040 |
| REQ-02 | 같은client_send_id동시POST/응답유실GET/재전송,다른UUID같은질문 | 같은ID실행1개/원장중복없음,다른ID정상별개또는동시상한명시거부; V-004/028 |
| REQ-03 | 취소CAS먼저vs완료CAS먼저 | 한종결,접수/실제종결분리,이미완료보존; V-008/031 |
| REQ-04 | POST접수후늦은SSE연결/seq중복·gap/EOF | snapshot대체/GET canonical,EOF로완료아님; V-007/010 |
| REQ-05 | A→B전환후A늦은응답/두탭각조직 | B화면혼입없음,Aresource소유불변; ACL07/14,V-002/036 |
| REQ-06 | wrongtenant/타인run/개인문서직접ID/role승격 | 403/404정보비노출,provider0,role불변; ACL01~08,V-026/027/038 |
| REQ-07 | Grant회수/문서삭제/Agent중지후새request·다음draft·공개 | 다음현재검사거부,제목/본문/근거비노출·기발생 usage보존; ACL09~13,V-019/020/022/034 |
| REQ-08 | 세션회수후SSE/신규call/최종공개,로그아웃후indexJob | chat중단/새콘텐츠차단,indexJob은최신주체권한으로독립; V-001/026/031 |
| REQ-09 | 최종 저장 실패/DB완전불가/재시작 | terminal성공없음,저장미확인/실패·interrupted,usage삭제/자동provider재호출없음; V-007/037 |
| REQ-10 | 권한내검색근거부족 vs검색 장애 vs무권한명시doc | completed+insufficient_evidence vs failed vs404,Q20라벨별비교; V-006/012/033 |
| REQ-11 | 재처리중복/Joblease중단/불명call | 이전실패보존·index/Job중복없음,needs_review재처리차단; V-018/032/037 |
| REQ-12 | capacity/rate/timeout/보호필드·private운영목록·usage | bounded거부/Retry-After,SDK암묵retry0·prompt/키/SQL없음; ACL15/16,V-023/038/040 |

## 12. 요구 대조·후속 책임

| 관련 요구 | 이문서계약 |
|---|---|
| UP-001·UP-002, AP-001, CP-001 | 인증/조직headers·API01~05/18~20/39~41·로그아웃/선택세대 |
| UP-003·UP-004·UP-005·UP-007·UP-008·UP-010·UP-011, CP-003·CP-006 | API06~14·식별/중복·run/CAS·stream/취소·오류/상한 |
| AP-002·AP-003·AP-005·AP-006·AP-009·AP-010, CP-010 | API18~27/32~34·현재 관리 권한·Job/retry·revision/최소감사 |
| NFR-001·NFR-002·NFR-003·NFR-005 | tenant늦은응답/현재검사·저장/재시작/불명·비노출·고정상한/검증입력 |

계획의 관련 요구24개를대조했다. UP-006·UP-009·UP-012, AP-004·AP-007·AP-008·AP-011·AP-012·AP-013, CP-002·CP-004·CP-005·CP-007·CP-008·CP-009도API연결/현재 권한/usage 영향으로포함했다. 전체API목록의행수는기능구현/시험통과수가아니다. 상태enum·오류·보완필드는D240-08에서02/03/05/06/07/08 문서와일치시킨다.

D240-04는모든generation/query/document embedding의현재 허가·중지/한도·provider0/고정timeout/암묵retry0·permit/call/usage/불명/slot·가격snapshot과정산을책임진다. D240-05는source버전선택/청킹/Graph/evidence·과거답변인용렌더링/삭제정리를, D240-06은7화면의표시/동작을, D240-07은미생성fixture와시험/성능측정을책임진다. 이번작업에서이후명세를완료로표시하지않는다.

## 13. 자체 점검·다음 D240-04 상세 계획

문서자체대조로API ID/경로·권한/필드,요구/상태/종결·중복/저장 실패·Job공개·stream/현재 권한·오류/상한을검토했다. 다음stage의유료호출·정산·과거인용정책은담당을명시했다. 실제 서버/HTTP/DB/SSE/model시험은없고Q20결과도not_run이다.

다음산출물은 **05 AI 호출과 사용량 원장 설계.md**, 문서 작업예상35분이다. 기존215분/80시간안의배분으로신규공수를추가하지않는다.

| 순서 | 예상 | 구체작업·출력 |
|---|---:|---|
| 1 | 5분 | 기본모델2개유지,생성/문서·질의임베딩의중앙호출인터페이스/실제·모의provider 구분 |
| 2 | 7분 | 현재계정/session또는Job권한→조직/Agent중지→한도/slot→원자permit/예약→호출순서 |
| 3 | 8분 | call/event/예약·확정·해제·불명·취소/timeout·중복/경합/재시작계약,회수후기발생 usage정산 |
| 4 | 5분 | Agent설정snapshot/조직·공통중지·상위배정과local한도·재개시현재검사 |
| 5 | 5분 | 승인30,000원안의단순보수추정/중지여유·고정단가snapshot/대조,키서버전용·직접SDK우회차단 |
| 6 | 5분 | 모의오류/대표실제호출의검증입력과실제호출전공식API/단가확인책임·자체점검,다음D240-05 상세계획 |

이번에도모델 비교/동적가격UI/정교한청구·키수집/계정설정·유료호출을추가하지않는다. 구체명세를작성/점검한후240 종합검토로모으고250 코드계획에전달한다.

## 14. 공식 기술 근거

2026-10-04 확인. 아래는HTTP/브라우저기능근거이며상태/상한값은프로젝트설계선택이다.

- [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): 요청/응답·상태코드·조건부수정·안전한조회/재전송 의미참고.
- [WHATWG Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html): UTF-8 text/event-stream 이벤트/연결의기술형식참고. 이번fetch parser가영속replay를구현했다고주장하지않음.
- [MDN Using Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): headers/credentials·response stream·AbortController와HTTP오류처리참고. fetch중단과업무취소는별도설계.
