# DP-01 IA115 화면 채택 추적

원본 ID/이름은 유지합니다. 관련 도메인의 목록/상세/등록/검토 패널 병합안이며 상세 화면 채택은 각 DP 설계에서 확정합니다. 신규 기능 수용은 모두 not_run입니다.

| ID | 앱 | 원본 화면 | 원본 URL | 관련 개발 작업 | 표현안 |
|---|---|---|---|---|---|
| SCR-COM-001 | 공통 | SSO 로그인·콜백 | /auth/callback | DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-COM-002 | 공통 | 접근권한 없음 | /error/403 | DP-16, DP-21 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-COM-003 | 공통 | Tenant 선택·전환 | /context/tenant | DP-09, DP-26 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-COM-004 | 공통 | 통합검색 결과 | /search | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-COM-005 | 공통 | 알림센터 | /notifications | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-COM-006 | 공통 | 통합 승인함 | /approvals | DP-10, DP-12, DP-17, DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-COM-007 | 공통 | 장기작업 상태 | /jobs | DP-05, DP-07, DP-12, DP-17 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-COM-008 | 공통 | 시스템 오류·점검 | /error | DP-02 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-HOM-001 | 사용자 통합 포털 | 통합 Home | /portal/home | DP-02, DP-09, DP-10, DP-16, DP-26 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-CHT-001 | 사용자 통합 포털 | AI Chat | /portal/chat | DP-03, DP-18, DP-21 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-CHT-002 | 사용자 통합 포털 | 출처·원문 상세 | /portal/chat/sources/:evidenceId | DP-04 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-CHT-003 | 사용자 통합 포털 | 대화 파일 업로드 | /portal/chat/upload | DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-CHT-004 | 사용자 통합 포털 | 개인 RAG 처리상태 | /portal/chat/personal-rag/jobs/:jobId | DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-CHT-005 | 사용자 통합 포털 | 전체 Prompt 조회 | /portal/chat/prompt | DP-11 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-CHT-006 | 사용자 통합 포털 | 응답 피드백 | /portal/chat/feedback | DP-04 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-CHT-007 | 사용자 통합 포털 | 대화·응답 Export | /portal/chat/export | DP-07 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-001 | 사용자 통합 포털 | My Agent 목록 | /portal/workspace/agents | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-002 | 사용자 통합 포털 | My Agent 상세 | /portal/workspace/agents/:agentId | DP-04, DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-003 | 사용자 통합 포털 | My Knowledge 목록 | /portal/workspace/knowledge | DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-004 | 사용자 통합 포털 | Knowledge 업로드 | /portal/workspace/knowledge/upload | DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-005 | 사용자 통합 포털 | Knowledge 상세 | /portal/workspace/knowledge/:knowledgeId | DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-006 | 사용자 통합 포털 | Knowledge 처리이력 | /portal/workspace/knowledge/:knowledgeId/jobs | DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-007 | 사용자 통합 포털 | Knowledge 설정·삭제 | /portal/workspace/knowledge/:knowledgeId/settings | DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-008 | 사용자 통합 포털 | 대화 이력 목록 | /portal/workspace/conversations | DP-03, DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-009 | 사용자 통합 포털 | 대화 이력 상세 | /portal/workspace/conversations/:sessionId | DP-03, DP-04, DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-010 | 사용자 통합 포털 | 즐겨찾기 | /portal/workspace/favorites | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MYW-011 | 사용자 통합 포털 | 개인설정·알림 | /portal/workspace/settings | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-001 | 사용자 통합 포털 | Marketplace Home | /portal/marketplace | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-002 | 사용자 통합 포털 | 통합 카탈로그 검색 | /portal/marketplace/search | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-003 | 사용자 통합 포털 | Agent 상세 | /portal/marketplace/agents/:assetId | DP-04, DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-004 | 사용자 통합 포털 | Prompt 상세 | /portal/marketplace/prompts/:assetId | DP-10, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-005 | 사용자 통합 포털 | MCP·Tool 상세 | /portal/marketplace/tools/:assetId | DP-10, DP-21, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-006 | 사용자 통합 포털 | Workflow 상세 | /portal/marketplace/workflows/:assetId | DP-10, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-007 | 사용자 통합 포털 | Knowledge 상세 | /portal/marketplace/knowledge/:assetId | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-008 | 사용자 통합 포털 | Model 상세 | /portal/marketplace/models/:assetId | DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-009 | 사용자 통합 포털 | 자산 사용신청 | /portal/marketplace/requests/new | DP-10, DP-12, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-010 | 사용자 통합 포털 | AI자산 템플릿 복제 | /portal/marketplace/templates/:assetId/clone | DP-10, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-011 | 사용자 통합 포털 | My Marketplace | /portal/marketplace/my | DP-04, DP-10, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-012 | 사용자 통합 포털 | 커뮤니티·지식공유 목록 | /portal/marketplace/community | DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-013 | 사용자 통합 포털 | 커뮤니티 게시물 상세 | /portal/marketplace/community/:postId | DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-MKT-014 | 사용자 통합 포털 | 커뮤니티 게시물 작성·편집 | /portal/marketplace/community/editor/:postId? | DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-001 | 사용자 통합 포털 | Agent 프로젝트 목록 | /portal/studio | DP-09, DP-26 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-002 | 사용자 통합 포털 | Agent 프로젝트 생성 | /portal/studio/projects/new | DP-09, DP-12, DP-26 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-003 | 사용자 통합 포털 | Agent 프로젝트 개요 | /portal/studio/projects/:projectId | DP-09, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-004 | 사용자 통합 포털 | Agent 기본설정 | /portal/studio/projects/:projectId/settings | DP-09, DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-005 | 사용자 통합 포털 | Prompt 편집기 | /portal/studio/projects/:projectId/prompt | DP-11, DP-12, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-006 | 사용자 통합 포털 | Prompt 버전 비교 | /portal/studio/projects/:projectId/prompt/versions | DP-09, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-007 | 사용자 통합 포털 | Workflow Canvas | /portal/studio/projects/:projectId/workflow | DP-09, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-008 | 사용자 통합 포털 | Workflow 노드 설정 | /portal/studio/projects/:projectId/workflow/nodes/:nodeId | DP-12, DP-21, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-009 | 사용자 통합 포털 | Workflow 실행이력 | /portal/studio/projects/:projectId/runs | DP-09, DP-21 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-010 | 사용자 통합 포털 | Knowledge 소스 목록 | /portal/studio/projects/:projectId/knowledge | DP-05, DP-12, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-011 | 사용자 통합 포털 | Knowledge 소스 추가 | /portal/studio/projects/:projectId/knowledge/new | DP-05, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-012 | 사용자 통합 포털 | RAG 검색설정 | /portal/studio/projects/:projectId/rag | DP-04, DP-05 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-013 | 사용자 통합 포털 | RAG 재인덱싱 상태 | /portal/studio/projects/:projectId/rag/indexes | DP-05, DP-09 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-014 | 사용자 통합 포털 | MCP·Tool 목록 | /portal/studio/projects/:projectId/tools | DP-12, DP-21, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-015 | 사용자 통합 포털 | MCP·Tool 연결 | /portal/studio/projects/:projectId/tools/new | DP-21, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-016 | 사용자 통합 포털 | Tool 연결 테스트 | /portal/studio/projects/:projectId/tools/:toolId/test | DP-21, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-017 | 사용자 통합 포털 | Agent Test Playground | /portal/studio/projects/:projectId/test | DP-09, DP-18, DP-21 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-018 | 사용자 통합 포털 | Trace·Debug | /portal/studio/projects/:projectId/traces/:runId | DP-09, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-019 | 사용자 통합 포털 | 평가 계획 | /portal/studio/projects/:projectId/evaluations/new | DP-09, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-020 | 사용자 통합 포털 | 평가 결과 | /portal/studio/projects/:projectId/evaluations/:evaluationId | DP-09, DP-12, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-021 | 사용자 통합 포털 | 승인·배포 요청 | /portal/studio/projects/:projectId/releases/new | DP-09, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-022 | 사용자 통합 포털 | Release 상태 | /portal/studio/projects/:projectId/releases/:releaseId | DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-STD-023 | 사용자 통합 포털 | 버전·Rollback 이력 | /portal/studio/projects/:projectId/versions | DP-09, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-HLP-001 | 사용자 통합 포털 | 도움말 센터 | /portal/help | DP-02 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-HLP-002 | 사용자 통합 포털 | 온보딩 튜토리얼 | /portal/help/tutorials/:tutorialId | DP-02 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-USR-HLP-003 | 사용자 통합 포털 | 기능 변경·릴리스 안내 | /portal/help/releases | DP-02, DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-DSH-001 | 관리자 포털 | 운영 통합 대시보드 | /admin/dashboard | DP-02, DP-14 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-DSH-002 | 관리자 포털 | 운영 KPI 드릴다운 | /admin/dashboard/metrics/:metricId | DP-14 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-DSH-003 | 관리자 포털 | 운영 리포트 Export | /admin/dashboard/export | DP-14 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-IAM-001 | 관리자 포털 | 사용자·역할 목록 | /admin/iam/roles | DP-10, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-IAM-002 | 관리자 포털 | 역할 상세 | /admin/iam/roles/:roleId | DP-10, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-IAM-003 | 관리자 포털 | 역할 생성·편집 | /admin/iam/roles/:roleId/edit | DP-10, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-IAM-004 | 관리자 포털 | 사용자 권한 부여·회수 | /admin/iam/entitlements | DP-10, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-IAM-005 | 관리자 포털 | 결재라인 관리 | /admin/iam/approval-lines | DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-IAM-006 | 관리자 포털 | 접속·활동 이력 | /admin/iam/activity | DP-15, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-IAM-007 | 관리자 포털 | 위임·비상권한 관리 | /admin/iam/delegations | DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-AST-001 | 관리자 포털 | AI서비스·자산 목록 | /admin/assets | DP-09, DP-10, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-AST-002 | 관리자 포털 | AI서비스·자산 등록 | /admin/assets/new | DP-09, DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-AST-003 | 관리자 포털 | AI서비스·자산 상세 | /admin/assets/:assetId | DP-09, DP-10, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-AST-004 | 관리자 포털 | 공개·공유범위 설정 | /admin/assets/:assetId/visibility | DP-09, DP-10 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-AST-005 | 관리자 포털 | 서비스 생명주기 관리 | /admin/assets/:assetId/lifecycle | DP-09, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-AST-006 | 관리자 포털 | 모델·데이터 반입 승인 | /admin/assets/imports | DP-17 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-PRJ-001 | 관리자 포털 | AI 과제 목록 | /admin/projects | DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-PRJ-002 | 관리자 포털 | AI 과제 등록·편집 | /admin/projects/editor/:projectId? | DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-PRJ-003 | 관리자 포털 | AI 과제 상세 | /admin/projects/:projectId | DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-PRJ-004 | 관리자 포털 | AI 과제 검토·결재 | /admin/projects/:projectId/approval | DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-RES-001 | 관리자 포털 | GPU·CPU 자원 현황 | /admin/resources | DP-27 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-RES-002 | 관리자 포털 | Quota 정책 관리 | /admin/resources/quotas | DP-27 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-RES-003 | 관리자 포털 | 자원 할당·예약 | /admin/resources/allocations | DP-25, DP-27 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-RES-004 | 관리자 포털 | 자원 사용·경보 상세 | /admin/resources/usage/:resourceId | DP-14, DP-27 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-REL-001 | 관리자 포털 | Release 목록 | /admin/releases | DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-REL-002 | 관리자 포털 | Release 상세·승인 | /admin/releases/:releaseId | DP-12, DP-17 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-REL-003 | 관리자 포털 | 배포 Pipeline 상세 | /admin/releases/:releaseId/pipeline | DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-REL-004 | 관리자 포털 | Rollback 실행·이력 | /admin/releases/:releaseId/rollback | DP-09, DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-REL-005 | 관리자 포털 | 환경·승격경로 관리 | /admin/releases/environments | DP-12 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-OPS-001 | 관리자 포털 | 통합 모니터링 | /admin/operations | DP-14, DP-18, DP-27 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-OPS-002 | 관리자 포털 | 서비스·Agent 성능 상세 | /admin/operations/services/:serviceId | DP-14, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-OPS-003 | 관리자 포털 | 미터링 사용량 | /admin/operations/usage | DP-14 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-OPS-004 | 관리자 포털 | 빌링·정산 | /admin/operations/billing | DP-14 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-OPS-005 | 관리자 포털 | 운영 알림·장애조치 | /admin/operations/alerts | DP-14, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SEC-001 | 관리자 포털 | 가드레일 정책 목록 | /admin/security/guardrails | DP-15, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SEC-002 | 관리자 포털 | 가드레일 정책 편집·배포 | /admin/security/guardrails/:policyId/edit | DP-15, DP-18, DP-21 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SEC-003 | 관리자 포털 | 서비스별 정책·예외 | /admin/security/exceptions | DP-15, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SEC-004 | 관리자 포털 | 가드레일 위반 현황 | /admin/security/violations | DP-15, DP-18 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SEC-005 | 관리자 포털 | 데이터 Scope 정책 | /admin/security/data-scopes | DP-09, DP-15, DP-19, DP-26 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SEC-006 | 관리자 포털 | 개인정보·복호화 예외승인 | /admin/security/privacy-exceptions | DP-15, DP-18, DP-19 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SEC-007 | 관리자 포털 | 감사로그 검색·상세 | /admin/security/audit | DP-15, DP-16, DP-18, DP-26 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-CMS-001 | 관리자 포털 | 공지·콘텐츠 관리 | /admin/content | DP-02, DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-CMS-002 | 관리자 포털 | 커뮤니티·게시판 관리 | /admin/content/community | DP-02, DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-CMS-003 | 관리자 포털 | 도움말·튜토리얼 관리 | /admin/content/help | DP-02, DP-25 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-CMS-004 | 관리자 포털 | 사이트·메뉴 설정 | /admin/content/site | DP-02 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SYS-001 | 관리자 포털 | Tenant·기준정보 관리 | /admin/system/tenants | DP-16, DP-26 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SYS-002 | 관리자 포털 | 연계 Connector 관리 | /admin/system/connectors | DP-09, DP-20, DP-22 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
| SCR-ADM-SYS-003 | 관리자 포털 | 시스템 상태·운영로그 | /admin/system/health | DP-09, DP-14, DP-16 | 같은도메인 목록/상세/모달 병합 가능; ID별 수용 유지 |
