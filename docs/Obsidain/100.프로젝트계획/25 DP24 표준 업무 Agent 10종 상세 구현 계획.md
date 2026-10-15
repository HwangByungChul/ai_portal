---
created: 2026-10-13
parent: "[[15 전체 기능명세서 잔여 기능 개발 실행 계획]]"
status: approved-for-development
---
# DP24 표준 업무 Agent 10종 및 단계별 평가 상세 구현 계획
## 1. 개요 및 목적
제안서 및 전체 기능명세서에 명시된 핵심 금융/공공 비즈니스 영역의 10대 표준 업무 Agent를 구현하고, 각 Agent가 사전 승인된 도구(Tool/MCP), 프롬프트 템플릿, 지식 베이스(RAG)와 결합하여 검증된 보조 업무를 수행할 수 있도록 표준 계약 및 실행 파이프라인을 구축한다.

특히 고객 민원, 여신 심사, 외환, 광고 심의 등 금융 규제 및 법적 책임이 수반되는 업무 Agent의 경우 **AI 단독 자동 확정을 원천 차단(`auto_decision_prohibited: true`)**하고, 원문 근거 및 담당자 검토 필수(Human-in-the-loop) 안전장치를 강제한다.

## 2. 10대 표준 업무 Agent 정의
- **AGENT_01: 규정 책무 관리 (Compliance & Duty)**
  - 대상: 내규/금융규정 검색 및 책무구조도 조회
  - 연계 도구: `kb_rule_query`
  - 제약: 규정 조항 번호 및 최종 개정일 원문 근거 명시
- **AGENT_02: 그룹웨어 문서 요약 (Doc Summary)**
  - 대상: 전자결재 기안문/공문 요약 및 핵심 쟁점 추출
  - 연계 도구: `data_view_reader`
  - 제약: 5대 핵심 불릿 및 결재 영향도 요약
- **AGENT_03: 회의록 및 액션아이템 (Meeting Minutes)**
  - 대상: 부서 회의 대화록 요약, 결정사항 및 담당자별 액션아이템 자동 도출
  - 연계 도구: -
  - 제약: 미정 사항 및 후속 일정 타임라인 구조화
- **AGENT_04: 공문 및 보고서 작성 (Report Drafting)**
  - 대상: 표준 공문 서식, 주간 업무보고, 기획 보고서 초안 생성
  - 연계 도구: `kb_rule_query`
  - 제약: 표준 공문서 기안 양식 준수 (발신/수신/제목/본문)
- **AGENT_05: 고객 민원 응대 보조 (VOC Assistant)**
  - 대상: 금융 민원 VOC 분류, 유사 선례 조회 및 답변 초안 제안
  - 연계 도구: `kb_rule_query`, `financial_product_lookup`
  - 제약: 자동 발송 금지, 소비자보호팀 담당자 승인 필수
- **AGENT_06: 광고 심의 점검 (Ad Compliance Review)**
  - 대상: 금융상품 광고/홍보 문구의 필수 고지사항 누락 및 과장광고 표현 점검
  - 연계 도구: `kb_rule_query`
  - 제약: 심의 통과/부적격 체크리스트 및 수정 권고안 제시
- **AGENT_07: 금융 상품 비교 안내 (Product Guide)**
  - 대상: 예/적금, 대출, 펀드 등 금융상품 금리/우대조건/가입대상 비교
  - 연계 도구: `financial_product_lookup`
  - 제약: 예금자보호법 적용 여부 및 유의사항 자동 고지
- **AGENT_08: 여신 심사 보조 (Credit Review Assistant)**
  - 대상: 차주 재무제표, 담보 평가액, DSR/LTV 산출 기준 보조 검토
  - 연계 도구: `data_view_reader`, `kb_rule_query`
  - 제약: **AI 대출 승인/거절 결정 원천 금지**, 심사역 검토 보조 의견서 초안 작성
- **AGENT_09: 외환 업무 가이드 (Forex Regulation)**
  - 대상: 외국환거래법, 해외송금 한도, 증빙서류 확인 기준 가이드
  - 연계 도구: `kb_rule_query`
  - 제약: 거래 사유별 필수 제출 서류 목록 체크리스트화
- **AGENT_10: 영업점 단말 내비게이션 (Branch Terminal Nav)**
  - 대상: 창구 단말 거래화면 코드, 조작 순서 및 서류 징구 절차 안내
  - 연계 도구: `kb_rule_query`
  - 제약: 화면번호(예: 0101, 2304) 및 단계별 단말 키 조작 순서 안내

## 3. 아키텍처 및 인터페이스
```
[사용자/업무 포털 UI (UseCaseWorkspacePage)]
        │
        ▼ (POST /api/v1/use-cases/{id}/execute)
[UseCase Router (app/use_cases/routes.py)]
        │
        ├─▶ [UseCaseCatalog (app/use_cases/catalog.py)]
        │       └─ 10대 Agent 메타데이터, 도구 바인딩, 금융 결정 안전장치 정책
        │
        ├─▶ [ToolRegistry (app/tools/registry.py)]
        │       └─ 승인 도구(kb_rule_query, financial_product_lookup 등) 실행
        │
        ├─▶ [Guardrail Engine (app/guardrails/engine.py)]
        │       └─ 입출력 PII 및 인젝션 방어
        │
        └─▶ [AiGateway / Model Router]
                └─ 시스템 프롬프트 합성 및 보조 답변 생성
```

## 4. 검증 계획
- **단위 및 수용 테스트 (`test_dp24_acceptance.py`)**:
  - 10대 업무 Agent 카탈로그 전수 등록 및 메타데이터 정합성 검증
  - 금융 결정 Agent 4종(여신/외환/민원/광고)의 `auto_decision_prohibited` 플래그 및 안내 배너 강제 검증
  - 연계 도구(`financial_product_lookup`, `kb_rule_query`) 통합 실행 및 답변 생성
  - 각 Agent별 모의 평가 케이스(정상 질의, 도구 연계 질의, 근거 요구 질의) 실행 검증
- **프론트엔드 빌드 및 E2E**:
  - `build:user` 및 `build:admin` 분리 빌드 경계 검증
  - 업무 Agent 워크스페이스 화면 렌더링 및 카테고리 필터링/실행 테스트
