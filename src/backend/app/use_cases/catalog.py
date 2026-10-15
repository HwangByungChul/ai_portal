"""10 Standard Business Agents Manifest Catalog.

Defines the 10 domain business agents for financial and enterprise workflows:
1. AGENT_01: 규정 책무 관리 (Compliance & Duty)
2. AGENT_02: 그룹웨어 문서 요약 (Doc Summary)
3. AGENT_03: 회의록 및 액션아이템 (Meeting Minutes)
4. AGENT_04: 공문 및 보고서 작성 (Report Drafting)
5. AGENT_05: 고객 민원 응대 보조 (VOC Assistant) - 금융결정 자동확정 금지
6. AGENT_06: 광고 심의 점검 (Ad Compliance Review) - 심의 자동확정 금지
7. AGENT_07: 금융 상품 비교 안내 (Product Guide)
8. AGENT_08: 여신 심사 보조 (Credit Review Assistant) - 여신판정 자동확정 금지
9. AGENT_09: 외환 업무 가이드 (Forex Regulation) - 외환승인 자동확정 금지
10. AGENT_10: 영업점 단말 내비게이션 (Branch Terminal Nav)
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UseCaseManifest:
    use_case_id: str
    name: str
    category: str  # compliance, document, customer, finance, operation
    description: str
    approved_asset_version: str
    required_tools: list[str]
    role_scope: list[str]
    auto_decision_prohibited: bool
    disclaimer: str | None
    system_prompt: str
    example_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_case_id": self.use_case_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "approved_asset_version": self.approved_asset_version,
            "required_tools": self.required_tools,
            "role_scope": self.role_scope,
            "auto_decision_prohibited": self.auto_decision_prohibited,
            "disclaimer": self.disclaimer,
            "example_queries": self.example_queries,
        }


# ---------------------------------------------------------------------------
# Catalog Registry (10 Standard Business Agents)
# ---------------------------------------------------------------------------
STANDARD_AGENTS: dict[str, UseCaseManifest] = {
    "AGENT_01": UseCaseManifest(
        use_case_id="AGENT_01",
        name="규정 책무 관리 Agent",
        category="compliance",
        description="내부통제 규정, 책무구조도 및 관련 금융 법령을 검색하고 조항 근거를 명시하여 답변합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["kb_rule_query"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=False,
        disclaimer=None,
        system_prompt="당신은 금융기관 규정 및 내부통제 전문 AI입니다. 질문에 대해 규정 조항(조, 항, 호)과 출처를 명확히 제시하십시오.",
        example_queries=[
            "고객 개인정보 암호화 관련 내부통제 지침을 알려주세요.",
            "AI 모델 결과물 검증 시 필수 준수 사항은 무엇인가요?",
        ],
    ),
    "AGENT_02": UseCaseManifest(
        use_case_id="AGENT_02",
        name="그룹웨어 문서 요약 Agent",
        category="document",
        description="전자결재 기안문 및 보고서 문서를 신속하게 요약하고 핵심 쟁점과 결재 영향도를 분석합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["data_view_reader"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=False,
        disclaimer=None,
        system_prompt="당신은 전자결재 문서 요약 전문 AI입니다. 기안문의 주요 목적, 예산 및 인력 영향, 추진 일정을 구조화된 5대 불릿으로 요약하십시오.",
        example_queries=[
            "신규 클라우드 인프라 도입 기안문의 핵심 내용을 요약해 주세요.",
            "차세대 시스템 프로젝트 예산 변경 기안서의 주요 쟁점을 정리해 주세요.",
        ],
    ),
    "AGENT_03": UseCaseManifest(
        use_case_id="AGENT_03",
        name="회의록 및 액션아이템 Agent",
        category="document",
        description="회의 대화록 및 메모를 바탕으로 핵심 결정사항, 부서별 액션아이템, 마감기한을 자동 구조화합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=[],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=False,
        disclaimer=None,
        system_prompt="당신은 비즈니스 회의록 정리 전문 AI입니다. 회의 대화 내용에서 결정사항(Decision), 미정 쟁점, 담당자별 액션아이템(Action Item) 및 타임라인을 명확히 분리하여 정리하십시오.",
        example_queries=[
            "오늘 진행된 주간 운영회의 대화 메모를 바탕으로 액션아이템을 정리해 줘.",
            "디지털혁신위원회 1차 회의 요약본과 후속 추진 과제를 도출해 주세요.",
        ],
    ),
    "AGENT_04": UseCaseManifest(
        use_case_id="AGENT_04",
        name="공문 및 보고서 작성 Agent",
        category="document",
        description="금융 및 공공 표준 공문서 서식에 맞추어 발신, 수신, 제목, 붙임, 본문 초안을 정격 작성합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["kb_rule_query"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=False,
        disclaimer=None,
        system_prompt="당신은 표준 행정/금융 공문서 작성 전문 AI입니다. 공문서 표준 양식(두문, 본문, 결문)과 격식 있는 비즈니스 어조를 준수하여 작성하십시오.",
        example_queries=[
            "금융감독원 정기검사 수검 관련 자료제출 요청 공문 초안을 작성해 주세요.",
            "타 기관과의 업무협약(MOU) 체결 추진 보고서 초안을 작성해 줘.",
        ],
    ),
    "AGENT_05": UseCaseManifest(
        use_case_id="AGENT_05",
        name="고객 민원 응대 보조 Agent",
        category="customer",
        description="접수된 고객 민원(VOC)의 핵심 요구사항을 분석하고, 선례 및 규정에 기반한 회신 가이드 초안을 작성합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["kb_rule_query", "financial_product_lookup"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=True,
        disclaimer="[주의] 본 답변은 민원 담당자의 사실 확인 및 내부 결재를 위한 보조 초안입니다. AI 단독으로 고객에게 직발송하거나 최종 민원 결정을 확정할 수 없습니다.",
        system_prompt="당신은 금융소비자보호 민원 응대 전문 AI입니다. 고객의 불편사항에 대해 공감하며, 관련 약관과 규정을 근거로 정중하고 명확한 회신문 초안을 작성하십시오.",
        example_queries=[
            "모바일뱅킹 간편송금 오류로 발생한 이체 지연 민원에 대한 회신 초안을 작성해 줘.",
            "예금 만기 자동해지 안내 미수신 불만 민원에 대한 검토 의견을 제시해 주세요.",
        ],
    ),
    "AGENT_06": UseCaseManifest(
        use_case_id="AGENT_06",
        name="광고 심의 점검 Agent",
        category="compliance",
        description="금융상품 마케팅 및 광고 문구의 필수 고지사항 누락 여부와 금융소비자보호법상 금지 표현을 점검합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["kb_rule_query"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=True,
        disclaimer="[주의] 본 검토 결과는 준법감시부 심의 신청을 위한 사전 자체점검 보조 자료이며, 준법감시인 최종 심의필을 대신할 수 없습니다.",
        system_prompt="당신은 금융 광고 심의 전문 AI입니다. 금융상품 광고의 필수 표기사항(위험고지, 예금자보호법 등) 누락과 '원금보장', '확정수익' 등 오인 유발 표현을 엄격히 검토하십시오.",
        example_queries=[
            "신규 적금 출시 카드뉴스 문구에 금소법 위반 소지가 있는지 점검해 줘.",
            "비대면 신용대출 홍보 배너 카피의 필수 고지문구를 검토해 주세요.",
        ],
    ),
    "AGENT_07": UseCaseManifest(
        use_case_id="AGENT_07",
        name="금융 상품 비교 안내 Agent",
        category="finance",
        description="수신, 여신, 신탁 등 금융상품 카탈로그를 조회하여 고객 조건에 적합한 상품별 금리와 우대조건을 비교합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["financial_product_lookup"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=False,
        disclaimer=None,
        system_prompt="당신은 금융상품 안내 전문 AI입니다. 고객의 요구 조건에 맞추어 예금, 적금, 대출 상품의 금리와 조건을 객관적으로 비교 안내하십시오.",
        example_queries=[
            "현재 가입 가능한 1년 만기 정기예금과 적금 금리를 비교해 줘.",
            "직장인 대상 신용대출 상품의 기본 금리와 한도를 안내해 주세요.",
        ],
    ),
    "AGENT_08": UseCaseManifest(
        use_case_id="AGENT_08",
        name="여신 심사 보조 Agent",
        category="finance",
        description="차주의 소득 및 재무 데이터, 담보 현황, 신용지표를 바탕으로 여신 규정 부합 여부와 리스크 보조 검토 의견을 제시합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["data_view_reader", "kb_rule_query"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=True,
        disclaimer="[주의] 본 결과물은 여신심사역의 심사 결정을 돕기 위한 보조 분석 자료입니다. AI가 대출 승인/거절을 독자적으로 결정할 수 없으며 심사역 전결 절차가 필수입니다.",
        system_prompt="당신은 여신 심사 분석 보조 AI입니다. 차주의 상환능력, LTV/DSR 규제 한도, 담보 평가액을 데이터 기반으로 산출하고 여신심사 의견서 초안을 작성하십시오.",
        example_queries=[
            "연소득 7천만원 차주의 주택담보대출 신청 시 DSR 40% 한도 충족 여부를 검토해 줘.",
            "중소기업 운전자금 대출 신청 기업의 최근 3개년 재무 안정성을 분석해 주세요.",
        ],
    ),
    "AGENT_09": UseCaseManifest(
        use_case_id="AGENT_09",
        name="외환 업무 가이드 Agent",
        category="finance",
        description="외국환거래법령 및 규정에 따른 해외송금 한도, 사유별 필수 징구서류, 외환 신고 절차를 안내합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["kb_rule_query"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=True,
        disclaimer="[주의] 외환 거래 규정 및 증빙 서류 적합성 판단은 창구 외환 담당자의 실물 확인이 필수이며, AI의 안내만으로 외환 송금을 자동 승인할 수 없습니다.",
        system_prompt="당신은 외국환거래 전문 AI입니다. 외국환거래 규정 및 한국은행/외국환은행 신고 대상 여부를 판별하고 필요 서류 체크리스트를 안내하십시오.",
        example_queries=[
            "유학생 송금 지정 및 연간 지급증빙서류 미제출 한도를 알려주세요.",
            "해외 부동산 취득을 위한 사전 외환 신고 절차와 제출 서류를 안내해 줘.",
        ],
    ),
    "AGENT_10": UseCaseManifest(
        use_case_id="AGENT_10",
        name="영업점 단말 내비게이션 Agent",
        category="operation",
        description="창구 직원의 영업점 단말기 화면번호, 거래코드, 단계별 전산 조작 및 실물 서류 스캔 순서를 안내합니다.",
        approved_asset_version="v1.0.0-std",
        required_tools=["kb_rule_query"],
        role_scope=["USER", "PADMIN"],
        auto_decision_prohibited=False,
        disclaimer=None,
        system_prompt="당신은 영업점 단말 전산 및 창구 매뉴얼 안내 전문 AI입니다. 행원 질의에 대해 정확한 화면번호(예: 0101 계좌신규)와 단계별 단말 조작 순서를 일목요연하게 설명하십시오.",
        example_queries=[
            "법인 계좌 개설 시 단말 화면번호와 거래 순서를 안내해 줘.",
            "비대면 실명확인 실패 고객의 오프라인 OTP 재발급 단말 조작 절차를 알려주세요.",
        ],
    ),
}


def get_use_cases() -> list[UseCaseManifest]:
    """Return all 10 standard business agents."""
    return list(STANDARD_AGENTS.values())


def get_use_case(use_case_id: str) -> UseCaseManifest | None:
    """Return specific business agent by ID."""
    return STANDARD_AGENTS.get(use_case_id)
