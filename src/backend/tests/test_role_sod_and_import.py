"""Tests for DP-16/17: Role SOD service and Data Import auto-scan."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.auth.role_sod import RoleSODRepository
from app.data_import.scanner import scan_format, scan_pii, scan_malware, auto_scan
from app.errors import AppError


# ===========================================================================
# Role SOD — RoleSODRepository
# ===========================================================================

def _make_ctx():
    ctx = MagicMock()
    ctx.session_id = "aaaaaaaa-0000-4000-8000-000000000001"
    ctx.tenant_id  = "bbbbbbbb-0000-4000-8000-000000000002"
    ctx.effective_role = "PADMIN"
    return ctx


def _make_sod_repo():
    return RoleSODRepository(MagicMock())


@pytest.mark.asyncio
async def test_role_grant_calls_rpc():
    repo = _make_sod_repo()
    ctx  = _make_ctx()
    from uuid import uuid4
    uid = uuid4()
    repo._rpc = AsyncMock(return_value={"grant_id": "g-001"})
    grant_id = await repo.grant(ctx, uid, "REVIEWER")
    assert grant_id == "g-001"
    repo._rpc.assert_awaited_once()
    call_func = repo._rpc.call_args.args[1]
    assert call_func == "role_grant"


@pytest.mark.asyncio
async def test_role_revoke_calls_rpc():
    repo = _make_sod_repo()
    ctx  = _make_ctx()
    from uuid import uuid4
    uid = uuid4()
    repo._rpc = AsyncMock(return_value={"ok": True})
    await repo.revoke(ctx, uid, "REVIEWER", note="test")
    call_func = repo._rpc.call_args.args[1]
    assert call_func == "role_revoke"


def test_sod_translate_conflict():
    repo = _make_sod_repo()
    err = MagicMock()
    err.sqlstate = "A0409"
    with pytest.raises(AppError) as exc:
        repo._translate(err)
    assert exc.value.status == 409


# ===========================================================================
# Data Import Scanner
# ===========================================================================

# --- scan_format ---

def test_scan_format_allowed_pdf():
    result = scan_format("report.pdf", "application/pdf")
    assert result["passed"] is True


def test_scan_format_disallowed_exe():
    result = scan_format("malware.exe", "application/octet-stream")
    assert result["passed"] is False
    assert result["reason"] is not None


def test_scan_format_allowed_docx():
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    result = scan_format("doc.docx", mime)
    assert result["passed"] is True


def test_scan_format_txt_no_mime():
    result = scan_format("notes.txt", None)
    # extension ok but mime None → fails mime check
    assert result["passed"] is False


# --- scan_pii ---

def test_scan_pii_clean_text():
    result = scan_pii("일반적인 업무 문서 내용입니다. 위험 정보 없음.")
    assert result["passed"] is True
    assert result["findings"] == []


def test_scan_pii_detects_rrn():
    result = scan_pii("주민번호: 900101-1234567 입니다.")
    assert result["passed"] is False
    types = [f["type"] for f in result["findings"]]
    assert "주민등록번호" in types


def test_scan_pii_detects_email():
    result = scan_pii("담당자 이메일: test.user@company.com 으로 연락하세요.")
    assert result["passed"] is False
    types = [f["type"] for f in result["findings"]]
    assert "이메일" in types


def test_scan_pii_empty_content():
    result = scan_pii("")
    assert result["passed"] is True


# --- scan_malware ---

def test_scan_malware_clean_hash():
    sha = "a" * 64
    result = scan_malware(sha)
    assert result["passed"] is True


# --- auto_scan ---

def test_auto_scan_clean_document():
    pii, fmt, mal, passed = auto_scan(
        "meeting_notes.txt", "text/plain",
        "b" * 64, "정기 회의 내용입니다."
    )
    assert fmt["passed"] is True
    assert pii["passed"] is True
    assert mal["passed"] is True
    assert passed is True


def test_auto_scan_bad_format_fails():
    pii, fmt, mal, passed = auto_scan(
        "script.exe", "application/octet-stream",
        "c" * 64, "binary data"
    )
    assert fmt["passed"] is False
    assert passed is False


def test_auto_scan_pii_triggers_review():
    pii, fmt, mal, passed = auto_scan(
        "data.txt", "text/plain",
        "d" * 64, "연락처: 010-1234-5678"
    )
    assert fmt["passed"] is True
    assert pii["passed"] is False   # PII detected → review needed
    assert passed is False           # overall not clean
