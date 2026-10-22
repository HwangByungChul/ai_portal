"""DP-17: Data Import Approval — request, auto-scan, and human decision flow.

Auto-scan checks:
  1. Format scan: MIME type / file extension allowlist
  2. PII candidate scan: reuses existing PII regex patterns
  3. Malware scan: SHA-256 hash against a static blocklist (placeholder)

Human approval is PADMIN/TADMIN only and blocks self-approve via DB constraint.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".md", ".pdf", ".docx", ".xlsx",
})

# Known malicious SHA-256 hashes (placeholder — replace with real blocklist in production)
KNOWN_MALWARE_HASHES: frozenset[str] = frozenset()

# PII candidate patterns (reused from existing policies)
_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("주민등록번호",    re.compile(r'\b\d{6}-[1-4]\d{6}\b')),
    ("전화번호",        re.compile(r'\b0\d{1,2}-\d{3,4}-\d{4}\b')),
    ("이메일",          re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')),
    ("계좌번호",        re.compile(r'\b\d{10,14}\b')),
]


def scan_format(filename: str, mime_type: str | None) -> dict[str, Any]:
    """Check whether filename extension and MIME type are on the allowlist."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext_ok = ext in ALLOWED_EXTENSIONS
    mime_ok = mime_type in ALLOWED_MIME_TYPES if mime_type else False
    passed = ext_ok and mime_ok
    return {
        "passed": passed,
        "extension": ext,
        "mime_type": mime_type,
        "reason": None if passed else f"허용되지 않은 파일 형식입니다 ({ext or '알 수 없음'}).",
    }


def scan_pii(content_sample: str) -> dict[str, Any]:
    """Detect PII candidates in the first 4 000 characters of the document."""
    sample = content_sample[:4000]
    findings: list[dict] = []
    for label, pattern in _PII_PATTERNS:
        matches = pattern.findall(sample)
        if matches:
            findings.append({"type": label, "count": len(matches)})
    return {
        "passed": len(findings) == 0,
        "findings": findings,
        "reason": f"{', '.join(f['type'] for f in findings)} 후보가 감지되었습니다." if findings else None,
    }


def scan_malware(sha256: str) -> dict[str, Any]:
    """Check SHA-256 hash against known malware blocklist."""
    blocked = sha256.lower() in KNOWN_MALWARE_HASHES
    return {
        "passed": not blocked,
        "sha256": sha256,
        "reason": "알려진 악성 파일과 일치합니다." if blocked else None,
    }


def auto_scan(filename: str, mime_type: str | None,
              sha256: str, content_sample: str = "") -> tuple[dict, dict, dict, bool]:
    """Run all three scans; return (pii, format, malware, all_passed)."""
    pii    = scan_pii(content_sample)
    fmt    = scan_format(filename, mime_type)
    mal    = scan_malware(sha256)
    passed = pii["passed"] and fmt["passed"] and mal["passed"]
    return pii, fmt, mal, passed
