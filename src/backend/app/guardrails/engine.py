"""Guardrail policy engine — input/output content filtering.

Reuses proven PII / prompt-injection patterns from document_ingest policy
and adds prompt-specific forbidden-content rules.  The engine is stateless
and deterministic: no external I/O, no matched text is returned or logged.
"""
from dataclasses import dataclass, field
import hashlib
import re
import unicodedata
from typing import Literal

# ---------------------------------------------------------------------------
# Policy revision (bump on rule-set change)
# ---------------------------------------------------------------------------
REVISION = "guardrail-v1"

# ---------------------------------------------------------------------------
# Shared PII patterns (identical to document_ingest.py)
# ---------------------------------------------------------------------------
_PII_RRN = re.compile(
    r"(?<![0-9])[0-9]{6}[\s\u2010\u2011\u2012\u2013\u2014\u2212-]*[1-8][0-9]{6}(?![0-9])"
)
_PII_PHONE = re.compile(
    r"(?<![0-9])(?:01[016789]|\+82[ .-]*1[016789])[ .-]*[0-9]{3,4}[ .-]*[0-9]{4}(?![0-9])"
)
_PII_EMAIL = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,63}",
    re.I,
)
_PII_ACCOUNT = re.compile(
    r"(?:계좌(?:번호)?|account(?:\s+number)?)[\s:#：=]*([0-9][0-9 -]{8,30}[0-9])",
    re.I,
)

# ---------------------------------------------------------------------------
# Prompt-injection patterns (superset of document_ingest.py)
# ---------------------------------------------------------------------------
_INJECTION = re.compile(
    r"(?:"
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions"
    r"|(?:이전|기존|시스템)\s*(?:의\s*)?(?:지시(?:사항|문)?|명령|프롬프트)(?:를|을)?\s*무시"
    r"|(?:reveal|print|expose|show|output)\s+(?:the\s+)?system\s+prompt"
    r"|시스템\s*프롬프트(?:를|을)?\s*(?:공개|출력|보여)"
    r"|you\s+are\s+now\s+(?:DAN|jailbroken|unrestricted)"
    r"|(?:act|pretend|behave)\s+(?:as\s+)?(?:if\s+)?(?:you\s+(?:are|have)\s+)?(?:no\s+)?(?:restrictions|limits|filters)"
    r"|developer\s+mode\s+(?:enabled|activated|on)"
    r"|(?:개발자|관리자)\s*모드\s*(?:활성|시작|켜)"
    r")",
    re.I,
)

# ---------------------------------------------------------------------------
# Forbidden-content patterns (violence, discrimination, illegal guidance)
# ---------------------------------------------------------------------------
_FORBIDDEN = re.compile(
    r"(?:"
    r"(?:폭탄|폭발물|독극물|마약)\s*(?:제조|만드는|만들)\s*(?:법|방법|과정)"
    r"|(?:bomb|explosive|poison|drug)\s*(?:making|manufacturing|how\s*to\s*make)"
    r"|(?:자살|자해)\s*(?:방법|수단|도구)"
    r"|(?:suicide|self.harm)\s*(?:method|how\s*to)"
    r")",
    re.I,
)

# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------
INPUT_RULES: list[tuple[str, re.Pattern]] = [
    ("PII_RRN", _PII_RRN),
    ("PII_PHONE", _PII_PHONE),
    ("PII_EMAIL", _PII_EMAIL),
    ("PII_ACCOUNT", _PII_ACCOUNT),
    ("PROMPT_INJECTION", _INJECTION),
    ("FORBIDDEN_CONTENT", _FORBIDDEN),
]

OUTPUT_RULES: list[tuple[str, re.Pattern]] = [
    ("PII_RRN", _PII_RRN),
    ("PII_PHONE", _PII_PHONE),
    ("PII_EMAIL", _PII_EMAIL),
    ("PII_ACCOUNT", _PII_ACCOUNT),
    ("FORBIDDEN_CONTENT", _FORBIDDEN),
]

# ---------------------------------------------------------------------------
# PII masking helpers
# ---------------------------------------------------------------------------
_MASK_RRN = (
    _PII_RRN,
    lambda m: m.group(0)[:6] + "-" + "*" * 7,
)
_MASK_PHONE = (
    _PII_PHONE,
    lambda m: re.sub(r"[0-9]", "*", m.group(0)),
)
_MASK_EMAIL = (
    _PII_EMAIL,
    lambda m: m.group(0).split("@")[0][:2] + "***@" + m.group(0).split("@")[1],
)
_MASK_ACCOUNT = (
    _PII_ACCOUNT,
    lambda m: m.group(0).replace(m.group(1), re.sub(r"[0-9]", "*", m.group(1))),
)

MASKING_RULES = [_MASK_RRN, _MASK_PHONE, _MASK_EMAIL, _MASK_ACCOUNT]


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------
Direction = Literal["input", "output"]
Severity = Literal["block", "warn", "log"]


@dataclass(frozen=True)
class GuardrailResult:
    """Evaluation outcome — no matched text is stored."""
    direction: Direction
    action: Literal["allow", "block", "mask"]
    rule_ids: tuple[str, ...]
    revision: str = REVISION
    masked_text: str | None = None


@dataclass
class GuardrailPolicy:
    """In-memory policy configuration."""
    revision: int = 1
    input_enabled: bool = True
    output_enabled: bool = True
    pii_severity: Severity = "block"
    injection_severity: Severity = "block"
    forbidden_severity: Severity = "block"
    output_pii_action: Literal["mask", "block"] = "mask"


# ---------------------------------------------------------------------------
# Singleton policy store (in-memory, no DB table needed)
# ---------------------------------------------------------------------------
_CURRENT_POLICY = GuardrailPolicy()


def get_policy() -> GuardrailPolicy:
    return _CURRENT_POLICY


def update_policy(*, expected_revision: int, **kwargs) -> GuardrailPolicy:
    global _CURRENT_POLICY
    if _CURRENT_POLICY.revision != expected_revision:
        raise ValueError("REVISION_CONFLICT")
    new = GuardrailPolicy(revision=expected_revision + 1, **{
        k: kwargs.get(k, getattr(_CURRENT_POLICY, k))
        for k in (
            "input_enabled", "output_enabled", "pii_severity",
            "injection_severity", "forbidden_severity", "output_pii_action",
        )
    })
    _CURRENT_POLICY = new
    return new


# ---------------------------------------------------------------------------
# Text normalizer
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKC", text)
        if unicodedata.category(c) != "Cf"
    )


# ---------------------------------------------------------------------------
# Evaluation functions
# ---------------------------------------------------------------------------
def evaluate_input(text: str, policy: GuardrailPolicy | None = None) -> GuardrailResult:
    """Check user prompt against input guardrail rules."""
    policy = policy if policy is not None else get_policy()
    if not policy.input_enabled:
        return GuardrailResult("input", "allow", ())

    if not isinstance(text, str) or len(text) > 50000:
        return GuardrailResult("input", "block", ("INPUT_TOO_LARGE",))

    normalized = _normalize(text)
    matched: list[str] = []

    for rule_id, pattern in INPUT_RULES:
        if rule_id == "PII_ACCOUNT":
            found = any(
                10 <= sum(c.isdigit() for c in m.group(1)) <= 22
                for m in pattern.finditer(normalized)
            )
        else:
            found = pattern.search(normalized) is not None
        if found:
            matched.append(rule_id)

    if not matched:
        return GuardrailResult("input", "allow", ())

    return GuardrailResult("input", "block", tuple(matched))


def evaluate_output(text: str, policy: GuardrailPolicy | None = None) -> GuardrailResult:
    """Check AI output and apply masking or blocking."""
    policy = policy if policy is not None else get_policy()
    if not policy.output_enabled:
        return GuardrailResult("output", "allow", ())

    if not isinstance(text, str):
        return GuardrailResult("output", "block", ("OUTPUT_INVALID",))

    normalized = _normalize(text)
    matched: list[str] = []

    for rule_id, pattern in OUTPUT_RULES:
        if rule_id == "PII_ACCOUNT":
            found = any(
                10 <= sum(c.isdigit() for c in m.group(1)) <= 22
                for m in pattern.finditer(normalized)
            )
        else:
            found = pattern.search(normalized) is not None
        if found:
            matched.append(rule_id)

    if not matched:
        return GuardrailResult("output", "allow", ())

    # Forbidden content in output → hard block
    if "FORBIDDEN_CONTENT" in matched:
        return GuardrailResult("output", "block", tuple(matched))

    # PII in output → mask or block depending on policy
    if policy.output_pii_action == "mask":
        masked = text
        for pattern, replacer in MASKING_RULES:
            masked = pattern.sub(replacer, masked)
        return GuardrailResult("output", "mask", tuple(matched), masked_text=masked)

    return GuardrailResult("output", "block", tuple(matched))


def text_hash(text: str) -> str:
    """SHA-256 hash of text for audit (no raw text stored)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
