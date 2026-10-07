"""Deterministic intake candidates; no matched text is returned or logged.

This minimum policy is not a general prompt-injection or PII classifier.
Normalization is detection-only, preserving source and evidence offsets.
"""
from dataclasses import dataclass
import re
import unicodedata
from app.errors import AppError

REVISION = "document-ingest-v1"
RULES = (
 ("PII_RRN", re.compile(r"(?<![0-9])[0-9]{6}[\s‐‑‒–—−-]*[1-8][0-9]{6}(?![0-9])")),
 ("PII_PHONE", re.compile(r"(?<![0-9])(?:01[016789]|\+82[ .-]*1[016789])[ .-]*[0-9]{3,4}[ .-]*[0-9]{4}(?![0-9])")),
 ("PII_EMAIL", re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,63}", re.I)),
 ("PII_ACCOUNT", re.compile(r"(?:계좌(?:번호)?|account(?:\s+number)?)[\s:#：=]*([0-9][0-9 -]{8,30}[0-9])", re.I)),
 ("PROMPT_OVERRIDE", re.compile(r"(?:ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions|(?:이전|기존|시스템)\s*(?:의\s*)?(?:지시(?:사항|문)?|명령|프롬프트)(?:를|을)?\s*무시|(?:reveal|print|expose)\s+(?:the\s+)?system\s+prompt|시스템\s*프롬프트(?:를|을)?\s*(?:공개|출력))", re.I)),
)

@dataclass(frozen=True)
class PolicyDecision:
 action: str
 rule_ids: tuple[str, ...]
 revision: str = REVISION

def evaluate_document_policy(text: str) -> PolicyDecision:
 if type(text) is not str or len(text)>40201:
  raise ValueError("POLICY_INPUT_INVALID")
 normalized="".join(c for c in unicodedata.normalize("NFKC",text) if unicodedata.category(c)!="Cf")
 matches=[]
 for rule,pattern in RULES:
  if rule=="PII_ACCOUNT":
   found=any(10<=sum(c.isdigit() for c in m.group(1))<=22 for m in pattern.finditer(normalized))
  else:found=pattern.search(normalized) is not None
  if found:matches.append(rule)
 return PolicyDecision("block" if matches else "allow",tuple(matches))

def require_document_policy(text: str) -> None:
 try:
  decision=evaluate_document_policy(text)
  if not isinstance(decision,PolicyDecision) or decision.action not in ("allow","block"):
   raise ValueError("POLICY_RESULT_INVALID")
 except Exception:
  raise AppError("DOCUMENT_POLICY_UNAVAILABLE",503) from None
 if decision.action=="block":raise AppError("DOCUMENT_POLICY_BLOCKED",422)
