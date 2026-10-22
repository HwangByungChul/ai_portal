---
title: AI Builder 고도화 구현 계획 목차
date: 2026-10-21
status: 실행 계획 · 사용자 실행 방식 선택 대기
tags: [ai-platform, builder, workflow, implementation-plan]
---

# AI Builder 고도화 구현 계획

## 목표와 기준선

코딩 경험이 거의 없는 현업 담당자가 자연어 빠른 시작 또는 단계별 제작으로 Agent/Workflow를 구성하고, 저장 전 제안을 직접 검토한 뒤 기존 버전·시험·평가·승인 경로를 사용한다. AI Studio 안에서 Agent와 Workflow를 전환하되 각각의 편집 모델은 독립적으로 유지한다.

현재 실제 앱은 AIStudioHubPage, Agent Builder의 불변 profile·시험·평가·증적, Workflow Canvas의 초안 저장과 승인 기반 실행을 보유한다. 자세한 현행/미완료 구분은 [[2026-10-21 AI Builder 고도화 통합 Studio 설계]], [[28 DP11 Agent Builder 프롬프트 RAG Playground 상세 개발 계획서]], [[11 DP11-04 이후 잔여 개발 항목과 진행 순서]], [[37 Workflow 중단 실행 수동 복구 구현 결과]]를 따른다.

## 독립 실행 계획과 순서

1. [[2026-10-21 AI Studio 공통 제작 흐름 구현 계획]] — 빠른 시작/단계별 제작 선택, 기존 Agent/Workflow 화면 및 초안 이어하기. UI 단위로 독립 검증한다.
2. [[2026-10-21 AI Builder 자연어 초안 생성 서비스 구현 계획]] — Gateway·정책·비용 원장 아래 typed proposal API와 Agent 연결. Mock provider로 독립 API와 Agent 흐름을 검증한다.
3. [[2026-10-21 Workflow Canvas 자연어 초안 연결 구현 계획]] — 제한된 graph 제안을 기존 Canvas에서 검토·수정하고 draft API로 저장한다. 승인/실행 경계와 분리해 검증한다.

## 선행 조건

- 현업 제작 권한은 DP16의 agent_developer capability와 심사자 분리를 따른다. 현재 코드/권한 상태를 먼저 확인한다. DP16이 준비되지 않았으면 USER를 TADMIN으로 승격하거나 기능에서 임의 admin 역할을 만들지 않고, 현행 허용 계정으로 UI 계약만 검증한다. 현업 UAT와 공개는 capability가 검증된 뒤 진행한다.
- 실행 순서는 공통 Studio UX → proposal API/Agent 연결 → Workflow 연결 → capability/UAT gate다.
- DB/fixture/browser harness는 공유 상태이므로 병렬 검증하지 않는다. 기존 migration을 수정하지 않는다. DB 변경 시 백업, 별도 fixture clone, 기존 행/checksum 보존을 먼저 검증한다.
- 실행 전에 기존 working tree 변경을 확인하고, 현재 미커밋 MCP/SSO 변경을 reset/stage/포함하지 않는다.

## 전체 완료 기준

- Agent/Workflow 각각에 빠른 시작과 단계별 제작이 있다.
- 자연어 제안은 편집 가능하며 생성만으로 저장, 시험, Tool 호출, 승인, 게시, 실행하지 않는다.
- 제안/초안 저장/시험/승인 요청/승인·반려/게시/운영 실행 상태를 구분한다.
- tenant/owner, 현행 자료 ACL, 승인 모델/Tool, 정책, 비용·감사 원장을 모든 생성·저장·시험 경계에서 지킨다.
- local/mock 검증, 외부 provider 품질, 실제 업무 전문가 평가, 기관 UAT, 운영 배포를 서로 다른 상태로 보고한다.

이 문서는 실행 계획이며 별도 실행 선택 전에는 코드를 변경하지 않는다.
