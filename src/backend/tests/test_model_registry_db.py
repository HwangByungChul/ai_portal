"""Tests for DP-13: Model Registry DB — ModelRegistryRepository and model_routes_db."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.model_registry_db import ModelRegistryRepository, DBModelRow
from app.errors import AppError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ctx(role="PADMIN"):
    ctx = MagicMock()
    ctx.session_id = "aaaaaaaa-0000-4000-8000-000000000001"
    ctx.tenant_id  = "bbbbbbbb-0000-4000-8000-000000000002"
    ctx.effective_role = role
    return ctx


def _make_repo():
    pool = MagicMock()
    return ModelRegistryRepository(pool)


# ---------------------------------------------------------------------------
# DBModelRow.to_public_dict — credential_ref must never appear
# ---------------------------------------------------------------------------

def test_db_model_row_public_dict_no_credential():
    row = DBModelRow(
        model_id="mid-1",
        provider_key="openai",
        model_name="gpt-4o-mini",
        display_name="GPT-4o Mini",
        context_window=128000,
        max_output=4096,
        price_input_usd=Decimal("0.15"),
        price_out_usd=Decimal("0.60"),
        credential_ref="OPENAI_API_KEY",
        active=True,
        is_default=True,
        capabilities=("chat", "streaming"),
    )
    public = row.to_public_dict()
    assert "credential_ref" not in public
    assert public["model_id"] == "mid-1"
    assert public["is_default"] is True


def test_db_model_row_admin_dict_has_credential():
    row = DBModelRow(
        model_id="mid-2",
        provider_key="mock",
        model_name="mock-fast",
        display_name="Mock Fast",
        context_window=4096,
        max_output=512,
        price_input_usd=Decimal("0"),
        price_out_usd=Decimal("0"),
        credential_ref="MOCK",
        active=True,
        is_default=False,
        capabilities=("chat",),
    )
    admin = row.to_admin_dict()
    assert admin["credential_ref"] == "MOCK"
    assert "price_input_usd" in admin


# ---------------------------------------------------------------------------
# ModelRegistryRepository._parse
# ---------------------------------------------------------------------------

def test_parse_row():
    raw = {
        "model_id": "mid-3",
        "provider_key": "openai",
        "model_name": "gpt-4o",
        "display_name": "GPT-4o",
        "context_window": 128000,
        "max_output": 16384,
        "price_input_usd": "2.50",
        "price_out_usd": "10.00",
        "credential_ref": "OPENAI_API_KEY",
        "active": True,
        "is_default": False,
        "capabilities": ["chat", "rag", "streaming"],
    }
    row = ModelRegistryRepository._parse(raw)
    assert row.model_name == "gpt-4o"
    assert row.price_input_usd == Decimal("2.50")
    assert "rag" in row.capabilities


# ---------------------------------------------------------------------------
# list_active — happy path via mocked RPC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_active_returns_rows():
    repo = _make_repo()
    ctx  = _make_ctx()
    rpc_response = {
        "items": [
            {"model_id": "m1", "provider_key": "openai", "model_name": "gpt-4o-mini",
             "display_name": "GPT-4o Mini", "context_window": 128000, "max_output": 4096,
             "price_input_usd": "0.15", "price_out_usd": "0.60",
             "credential_ref": "OPENAI_API_KEY", "active": True, "is_default": True,
             "capabilities": ["chat", "streaming"]},
        ]
    }
    repo._rpc = AsyncMock(return_value=rpc_response)
    rows = await repo.list_active(ctx)
    assert len(rows) == 1
    assert rows[0].model_name == "gpt-4o-mini"
    repo._rpc.assert_awaited_once_with(ctx, "model_registry_list",
                                       (ctx.session_id, ctx.tenant_id))


# ---------------------------------------------------------------------------
# list_all_admin — PADMIN only check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_admin_returns_all():
    repo = _make_repo()
    ctx  = _make_ctx("PADMIN")
    repo._rpc = AsyncMock(return_value={"items": []})
    rows = await repo.list_all_admin(ctx)
    assert rows == []


# ---------------------------------------------------------------------------
# set_active — active/inactive toggle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_active():
    repo = _make_repo()
    ctx  = _make_ctx("PADMIN")
    from uuid import uuid4
    model_id = uuid4()
    repo._rpc = AsyncMock(return_value={"ok": True})
    await repo.set_active(ctx, model_id, False)
    repo._rpc.assert_awaited_once()


# ---------------------------------------------------------------------------
# set_default — calls correct RPC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_default():
    repo = _make_repo()
    ctx  = _make_ctx("PADMIN")
    from uuid import uuid4
    model_id = uuid4()
    repo._rpc = AsyncMock(return_value={"ok": True})
    await repo.set_default(ctx, model_id)
    call_args = repo._rpc.call_args
    assert call_args.args[1] == "model_registry_set_default"


# ---------------------------------------------------------------------------
# Error translation — A0403 → 403
# ---------------------------------------------------------------------------

def test_translate_forbidden():
    repo = _make_repo()
    err = MagicMock()
    err.sqlstate = "A0403"
    with pytest.raises(AppError) as exc:
        repo._translate(err)
    assert exc.value.status == 403


def test_translate_not_found():
    repo = _make_repo()
    err = MagicMock()
    err.sqlstate = "A0404"
    with pytest.raises(AppError) as exc:
        repo._translate(err)
    assert exc.value.status == 404
