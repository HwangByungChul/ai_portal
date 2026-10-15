## Global Constraints

- 현재scope AGENT_03 하나, 나머지9종 추후확장; userA/adminA/approvalB·생성형AI플랫폼 유지.
- 현재개발DB51/source51·040일치이며옛DB/옛040이력은별도보존.000~050 checksum변경금지, 최초신규번호051을착수시재확인한다.
- 실행/부모/자식/최종조회 현재권한·CSRF·tenant/SOD/CAS·audit·봉인code/manifest·중복UUID·취소/정산 보존.
- 문서 최대3건, 본인이현재읽을수있는같은조직의개인/게시자료의exactversion/sha만선택. 비권한자료이름/본문노출금지. 삭제/회수/재게시·내용파일변경은실행및결과권한을재검사한다. 원문파일없는기존2건은자료사용불가로안내하며metadata를원문으로꾸미지않는다.
- 메모 또는 접근 가능한 문서가 최소1개 필요하다. 메모만 쓰는 기존 호출은 유지하고 문서만 선택한 입력도 허용한다. memo는4000자 상한유지, 실제모델에전달되는memo+문서+회의일context도기존Workflow/child4000자/token6000상한을준수한다. 초과는명시적거부/분량안내이며무단truncate/상한우회금지.
- 날짜는회의일ISO기준/한국업무표시이며시간/휴일추정없음. 오늘/내일/모레/N일후/이번주요일/다음주요일/명시ISO날짜의결정적규칙을문서화·시험한다. 다음주(요일없음)/조속히/영업일·애매한표현/기준일없음은due_date미확정과사유. 회의일당일의'오늘' 의미는실행일이아닌회의일. 기한원표현을근거quote에서확인하며모델의임의계산값을신뢰하지않는다.
- 결정/미정/액션은memo나선택문서의검증된원문인용과source_ref를갖는다. 담당자는해당quote내명시된경우만확정. 문서제목/페이지는현재ACL+servermapping으로표시하고모델의주장을그대로출처로사용하지않는다.
- 계약revision/code변경은새Workflow승인필요. 과거manifest snapshot/결과를소급변환/재승인하지않는다. Raw Workflow실행/조회에도같은회의록근거·날짜·문서권한정책을적용해우회경로를막는다.
- 유료모델호출/실기관정책·OCR/전사/9Agent/운영배포는이번기술구현밖. 실제모델품질평가의자료/정답/승인된provider준비와추후실측을명시한다.


## Task1 계약·날짜 및 평가 기준

Create `app/use_cases/meeting_dates.py`, `meeting_quality.py`, focused contract/date/quality tests and versioned synthetic evaluation fixtures. Modify `meeting.py` (compatibility-safe input/result additions and revision2), manifest `catalog.py` only ifnecessary. Pure tests noDB/paid. source_ref defaults memo for legacy result; typed documentrefs/date metadata and normalized deadline/sourceexpression/status. Validate source quotes exact and no inventedowner/deadline. Leap/year/week boundaries, missingbase/ambiguous/multiple conflictingdates rejectorunresolved, documentquote identity, legacydata tests. Rule/digest changes requirefreshapproval; implementation-readyflagnotartificiallyenabled. Report task1 scope not fullruntime.


## Exact initial interfaces
MeetingInput memo bound4000, meeting_date date|null, document_refs strict max3 unique {document_id:UUID,version_id:UUID}; blankmemo allowed onlynonemptyrefs (legacyblankstillinvalid). EvidenceItem source_ref:string default memo, doc source_ref=document:<versionUUID>; server supplied source map for exactquote validation, no arbitraryLLMdefinedsources. MeetingResult.check_evidence(source, document_sources optional mapping) backwardscompatible signature; action normalized fields due_expression/deadline_status/deadline_reason, serverderived. Prefer helper resolver dataclasses with deterministic results and human review flags. Keep due_date original field backwardscompatible. Document mapcontainsserververifiedtext only (Task2assembler). Contractrevision2 and server evaluation rubric purehelper; no inferredsemanticpass. Clearly separate machinecheckstats from humanquality. Test examples unsupportedambiguous/no meetingbase andpastdue flagged; explicitISO requirequote date. Pureevaluationfixtures synthetic, no paidcalls. NoSQL/DB/runtime integration yet.

Actual repo /Users/jwpios/antigravity/202610_AI 플랫폼; scopededit/test viaescalated. Existingliveuser/admin/backendrunningonnewDB currentlyvalid51: don'tstop orDBtests inTask1. No commits/other9/sourceSQLhistorical changes/Obsidiansharednotes. Preservehugedirtytree exactpre/post snapshots persistenttask1-review package. Use venv python purepytest coveringmeeting_contract+dates+quality only, nofixtures/PG roles. Sources type date parsingstrict ISOwire fromTask2 validator, dateshugeN bounded. Humanqualityrubric accuracy/omission/owner/deadline noweightednumericpseudoaccuracy. SourcefingerprintchangesmeanoldWorkflowfreshapproval required; codeflagnotforceenable.

Write task1-report.md exactchangedpaths commands/count/output/limits (pure vs integration), selfreview; generate task1-review/scoped.diff filesmanifest pre/post, no temp handoffs. No subagents.
