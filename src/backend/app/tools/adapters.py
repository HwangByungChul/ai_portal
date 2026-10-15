"""Tool execution adapters — separation between fixture mock data and real institutional connectors."""
import re
from typing import Any
from app.errors import AppError

# Disallow path traversal, raw SQL keywords, arbitrary URLs
_DANGEROUS_PATTERNS = re.compile(
    r"(?:\.\./|\.\.\\|https?://|ftp://|file://|/\.\.|\\.\.|"
    r"\b(?:select|insert|update|delete|drop|union|truncate|exec|execute)\b)",
    re.IGNORECASE
)

def validate_tool_argument_safety(val: Any) -> None:
    """Recursively inspect argument values for dangerous injection strings."""
    if isinstance(val, str):
        if len(val) > 1000:
            raise AppError("TOOL_ARGUMENTS_INVALID", 422)
        if _DANGEROUS_PATTERNS.search(val):
            raise AppError("TOOL_ARGUMENTS_INVALID", 422)
    elif isinstance(val, dict):
        for k, v in val.items():
            if not isinstance(k, str) or len(k) > 100:
                raise AppError("TOOL_ARGUMENTS_INVALID", 422)
            validate_tool_argument_safety(v)
    elif isinstance(val, list):
        if len(val) > 50:
            raise AppError("TOOL_ARGUMENTS_INVALID", 422)
        for item in val:
            validate_tool_argument_safety(item)


class BaseToolAdapter:
    def handle_financial_product_lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def handle_kb_rule_query(self, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def handle_data_view_reader(self, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class FixtureToolAdapter(BaseToolAdapter):
    """Deterministic fixture adapter for local tests and development."""
    def handle_financial_product_lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        validate_tool_argument_safety(args)
        category = args.get("category", "deposit")
        query = args.get("query", "").lower()
        words = [w for w in query.split() if len(w) >= 2]
        catalog = [
            {"code": "DP-001", "name": "BNK 디지털 정기예금", "category": "deposit", "rate_percent": 3.45, "term_months": 12},
            {"code": "DP-002", "name": "BNK 첫만남 우대적금", "category": "savings", "rate_percent": 4.50, "term_months": 12},
            {"code": "LN-001", "name": "AI 직장인 신용대출", "category": "loan", "rate_percent": 4.85, "max_limit_krw": 100000000},
        ]
        results = [
            item for item in catalog
            if (category == "all" or item["category"] == category)
            and (not words or any(w in item["name"].lower() for w in words))
        ]
        return {"matched_count": len(results), "items": results, "source": "fixture"}

    def handle_kb_rule_query(self, args: dict[str, Any]) -> dict[str, Any]:
        validate_tool_argument_safety(args)
        section = args.get("section", "all")
        keyword = args.get("keyword", "").lower()
        words = [w for w in keyword.split() if len(w) >= 2]
        rules = [
            {"rule_no": "R-101", "title": "고객 정보 보호 및 암호화 지침", "section": "security", "summary": "고객 식별정보는 전송 및 저장 시 AES-256 이상으로 암호화해야 합니다."},
            {"rule_no": "R-204", "title": "AI 모델 결과물 검증 절차", "section": "ai_governance", "summary": "외부 제공 답변 전 환각 및 유해성 검사를 필수로 수행해야 합니다."},
            {"rule_no": "R-305", "title": "업무 데이터 반입 및 승인 기준", "section": "data", "summary": "대외비 이상의 문서는 부서장 이상의 승인을 받아야 플랫폼에 반입할 수 있습니다."},
        ]
        matched = [
            r for r in rules
            if (section == "all" or r["section"] == section)
            and (not words or any(w in r["title"].lower() or w in r["summary"].lower() for w in words))
        ]
        return {"found": len(matched), "rules": matched, "source": "fixture"}

    def handle_data_view_reader(self, args: dict[str, Any]) -> dict[str, Any]:
        validate_tool_argument_safety(args)
        view_name = args.get("view_name")
        if view_name != "branch_daily_stats":
            raise AppError("VIEW_NOT_FOUND", 404)
        return {
            "view_name": view_name,
            "rows_count": 2,
            "columns": ["branch_code", "customer_count", "consultation_score"],
            "data": [
                {"branch_code": "BR-01", "customer_count": 142, "consultation_score": 94.5},
                {"branch_code": "BR-02", "customer_count": 118, "consultation_score": 96.0},
            ],
            "source": "fixture"
        }


class RealInstitutionalToolAdapter(BaseToolAdapter):
    """Real institutional connector interface. Must fail explicitly with 409 if not configured."""
    def __init__(self, endpoint: str | None = None, api_key: str | None = None):
        self.endpoint = endpoint
        self.api_key = api_key

    def handle_financial_product_lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        validate_tool_argument_safety(args)
        if not self.endpoint or not self.api_key:
            raise AppError("FEATURE_NOT_READY", 409)
        raise AppError("FEATURE_NOT_READY", 409)

    def handle_kb_rule_query(self, args: dict[str, Any]) -> dict[str, Any]:
        validate_tool_argument_safety(args)
        if not self.endpoint or not self.api_key:
            raise AppError("FEATURE_NOT_READY", 409)
        raise AppError("FEATURE_NOT_READY", 409)

    def handle_data_view_reader(self, args: dict[str, Any]) -> dict[str, Any]:
        validate_tool_argument_safety(args)
        if not self.endpoint or not self.api_key:
            raise AppError("FEATURE_NOT_READY", 409)
        raise AppError("FEATURE_NOT_READY", 409)
