---
title: 포털 UI와 Agent 승인 통합 검증 결과
created: 2026-10-11
updated: 2026-10-11
status: local-verified
production_verified: false
tags: [ai-platform, portal, approval, testing]
---

# 포털 UI와 Agent 승인 통합 검증 결과

대상: [[200.프로젝트실행/250.구현/21 포털 UI 통합과 Agent 배포 승인 구현 결과]]. 기존 플랫폼의 다른 검증을 이번 작업의 신규 결과로 재사용하지 않았다. 이번 시험은 소유 표식이 검증된 폐기용 DB·합성 계정·모의 모델로 수행했다.

## 실행 결과와 범위

| 실행 | 결과 | 의미 |
|---|---|---|
| 승인19 + 기존 운영·이행·스키마 관련 backend | 147 passed / 200.83s | 요청·결정·권한·DB 계약·기존 운영 회귀 |
| 추가 next-run snapshot / real HTTP restart | 2 passed / 8.96s | 승인 config_version2/지시문 봉인, 재시작 전후 요청·결정 보존·결정 재전송 |
| 최초 browser 전체104 | 100 passed, 4 failed | 아래 기존 모바일 요약 동선 오류 수정 전 증거 |
| 선별17 | 15 passed, 2 failed | 모바일 3개·문서 회귀9·파일럿2·화면 캡처1 통과; 아래 2개 재수정 |
| 선별2 | 1 passed, 1 failed | D07_10 키보드 메뉴 통과, P270_03 예전 저장 문구가 남아 실패 |
| 마지막 P270_03 | 1 passed | 새 운영 상태 저장 문구와 중지 후 실행 거부까지 통과 |
| `npm run build` | typecheck + Vite 성공 | 42 modules; JS 338.97kB/gzip98.70kB; CSS19.89kB |
| `git diff --check` | 성공 | 변경 파일 공백 오류 없음 |

중복을 제외한 browser **108개 시나리오의 최신 결과**가 통과했다. 이는 104개 기본 회귀 + 추가 파일럿3 + 신규 화면 캡처1이며 단일 108개 일괄 실행은 아니다. backend **149개 관련 시험** 통과이며 전체 backend 전수 시험이라고 주장하지 않는다.

## 실패와 조치

- 승인 필요·대기 한도 오류의 사용자 메시지를 추가했다.
- 새로운 기본 홈에 맞춰 과거 기능 시험은 `/workspace`와 명시적 기능 메뉴를 사용하도록 수정했다. 세션 복원 완료·사이트 이동·모바일 숨은 메뉴의 열기를 기다리는 공통 도우미를 적용했다.
- 최초 D07_08/10/12/13 실패는 모바일/조건부 문서 이동에 공통 도우미가 빠졌기 때문이었다. 기능 검증을 삭제하지 않고 경로를 갱신했다.
- D07_10은 키보드로 메뉴를 먼저 열어야 했다. P270_03은 기존 저장 문구가 남아 실패했으며 `운영 상태가 저장되었습니다.`로 갱신했다. 실제 중지 API·실행 거부·개인 자료 보호 검증은 유지했다.
- 신규 승인 필터·검색에 label/ID를 연결했다. 승인 본인 금지·타인 실제 처리·응답 손실 후 동일 UUID 확인·빈 검색·조직 변경·관리 URL 거부를 검증했다.
- 과거 종료된 A05 시험 기록 때문에 시작이 거부되어 표식·PID 소멸·주 DB 분리·연결0 확인 후 폐기용 DB만 정리했다. 초기 실패 증거는 보존했다.

## 권한·저장 검증

일반 사용자403, 다른 조직 요청404, 본인 결정403, 권한 회수403, 직접 PATCH/RPC409, 제출/결정 중복, 다른 변경 충돌409, CAS, 감사 실패 전체 rollback, cursor 페이지·지시문 목록 제외, 중지 유지, 다음 실행 스냅샷과 실제 HTTP 서버 재시작을 확인했다. 일반 사용자에게 관리 페이지 숨김만으로 보안을 대신하지 않는다.

## DB 이행과 복원

소유 표식과 현재 migration 상태를 검증했다. 원래 개발 DB를 `.runtime/U11-migration/before-026.sql`에 mode0600(디렉터리0700)으로 백업하고 신규 표식 폐기용 DB에 복원했다. 복원 DB의 기존 데이터 지문을 대조한 뒤 폐기했고, 원래 DB에는 checksum 기반 migration026만 적용했다. 이전000~025 SQL은 변경하지 않았다.

이행 전후 `portal.agent_configs`, `ops.project_budget`, `ops.tenant_budgets`, `ops.call_attempts`, `ops.usage_events`, `portal.conversations`의 행 수·SHA가 일치했다. 원장을 초기화하거나 seed를 반복하지 않았다. DB 백업 복원 검증이며 별도 파일/blob 저장소의 전체 재해 복구 시험까지 완료한 것은 아니다.

원래 소유 API8000/화면5173 서비스를 정상 복구했고 health·`/home`·`/admin` HTTP200과 HTML 브랜드를 확인했다. 유료 실제 모델 호출은 없었다.

## 증거와 한계

[[200.프로젝트실행/280.통합시스템테스트/evidence/UI11-portal/verification-summary.json]], [[200.프로젝트실행/280.통합시스템테스트/evidence/UI11-portal/source-manifest.json]], [[200.프로젝트실행/280.통합시스템테스트/evidence/UI11-portal/migration-026.json]], [[200.프로젝트실행/280.통합시스템테스트/evidence/UI11-portal/service-health.json]]과 browser 개별 결과 JSON을 보존했다. 선별2 결과는 마지막 실행이 reporter 파일을 교체하기 전 도구에서 읽은 안전 JSON을 출처 명시하여 기록했다. 공개 증거는 ID·결과·시간·SHA·boolean만 포함하며 비밀·지시문·질문/문서 본문은 넣지 않았다.

1600/390 화면·모바일 넘침·키보드를 자동 확인하고 `src/frontend/.runtime/U11-views/{user-home,admin-home,approval-mobile}.png`를 실제 열어 육안 확인했다. PNG는 사적 파일(0600)이며 가상 조직/빈 목록 화면이다. Obsidian Markdown 저장·UTF8·연결 링크를 검증했으나 Obsidian 읽기 화면 자체의 렌더링은 확인하지 않았다.

운영 SSO/MFA·실계정·운영 DB·도메인·독립 배포·실모델 평가·운영 OS 문서 격리·부하·운영 관측/알림·파일 저장소 재해 복구는 미검증이다. [[100.프로젝트계획/12 사용자 관리자 사이트 분리와 상용 이행 설계]]의 다음 단계로 이어간다.
