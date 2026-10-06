---
title: 문서 색인 Job 권한 통합 검증 결과
created: 2026-10-06
updated: 2026-10-06
status: completed
stage: 280.통합시스템테스트
tags: [ai-platform, mvp, verification]
---

# 문서 색인 Job 권한 보완 결과

정상 접수된 색인 Job은 로그아웃·세션 만료·유휴 만료 후에도 진행한다. origin session은 감사 참조로 남기며 API의 로그인 검사는 유지한다. 현재 계정·조직·소속·관리 권한·문서·Agent와 저장된 작업 승인·lease·세대·증명 검사를 계속 적용한다. 이번 단위만 완료했으며 전체 T280은 진행 중이다.

## 실제 검증

| 구분 | 결과 | 범위 |
|---|---|---|
| 보완 전 재현 | 9건 실패 | 로그아웃/만료/유휴 × claim 전/호출 후/checkpoint 후 |
| 관련 서버 | 93건 통과 | 새 32건 포함, 권한·본문·lease 회귀 |
| 전체 서버 | 856건 통과, 0건 실패 | 현재 소스 전체 회귀 |
| 화면 | 64건 | 빌드 및 브라우저 시험, 세부 판정은 증거 JSON |
| 핵심 반복 | 36건 통과 | 정확한 시험 ID 및 반복 구분은 증거 JSON |

실제 HTTP 접수·로그아웃과 같은 DB의 서버 재시작으로 대기 작업 완료, 권한 회수 차단, 사용량 불명 호출의 자동 재발사 방지를 확인했다. 두 번째 재시작에서도 Job·원장·call을 보존했다. 권한 회수 시점의 14건은 합성 fixture를 변경한 시험이며 모든 실제 관리자 API 조합의 완료를 의미하지 않는다. 문서 정리 Job은 별도 잔여 항목이다.

## 보존 및 비용

새 018 migration을 기존 persistent DB에 적용해 총 19개가 됐다. 기존 18개 기록과 31개 업무 테이블의 기존 데이터, 원장, 비공개 설정, 원본 GraphRAG, 과거 증거를 보존했다. 유료 호출 0, 신규 비용 0원이다. 대표 총배정 500원과 A 기존 내부 추정액 0.19원을 유지했으며 B 실배정은 아직 없다. 기본 Mock/RAG 비활성 상태로 종료했다.

[[07 Job 권한 계약과 통합 검증 잔여 상세 작업 계획]]의 앞부분 색인 계약을 완료했다. 남은 정확한 입력 판정, 상세60·ACL16, 실제 RAG, 새 환경 설치/복원, 사용자 직접 피드백은 미완료다. 다음은 [[09 통합 검증 잔여 입력과 정리 Job 상세 작업 계획]]이다.

근거: [시험 목록](evidence/T280-job-principal/regression-cases.json), [관측과 한계](evidence/T280-job-principal/job-observations.json), [계약 변경](evidence/T280-job-principal/contract-update.json), [보존 확인](evidence/T280-job-principal/preservation.json). 소스 커밋: `05f88e17f059ac219fbf98e66a14ba5f3aa7636a`.
