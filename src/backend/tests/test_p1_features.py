"""Tests for P1 items: Regenerate message, Unified Catalog, and PDF Summary export."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.execution.exports import pdf_attachment, markdown_attachment
from app.catalog.repository import CatalogRepository


def test_pdf_attachment_generates_valid_pdf():
    fake_data = {
        'state': 'completed',
        'content_status': 'final',
        'result': {'text': 'This is an executive summary of the document.'},
        'evidence': [
            {
                'title': 'Test Document',
                'version_no': 1,
                'location': {'line_start': 10, 'line_end': 25}
            }
        ]
    }
    response = pdf_attachment(fake_data, "req-1234")
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert "attachment; filename=\"summary.pdf\"" in response.headers["Content-Disposition"]
    assert response.headers["X-Request-ID"] == "req-1234"

    # PDF header and EOF
    body = response.body
    assert body.startswith(b"%PDF-1.4")
    assert b"%%EOF" in body
    assert b"/Type /Catalog" in body
    assert b"/Type /Pages" in body


def test_pdf_attachment_raises_when_not_ready():
    fake_data = {
        'state': 'running',
        'content_status': 'draft',
        'result': None
    }
    with pytest.raises(Exception) as exc:
        pdf_attachment(fake_data, "req-5678")
    assert "SUMMARY_NOT_READY" in str(exc.value)


@pytest.mark.asyncio
async def test_catalog_repository_unified_search():
    pool = MagicMock()
    repo = CatalogRepository(pool)

    mock_row = {
        'data': {
            'items': [
                {
                    'asset_id': str(uuid4()),
                    'asset_type': 'agent',
                    'name': 'Test Agent',
                    'description': 'A helpful agent',
                    'version': 1,
                    'active': True
                }
            ],
            'has_more': False
        }
    }

    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = mock_row

    mock_conn = AsyncMock()
    mock_conn.execute.return_value = mock_cursor

    ctx = MagicMock()
    ctx.session_id = uuid4()
    ctx.tenant_id = uuid4()

    with patch('app.catalog.repository.tenant_transaction') as mock_tx:
        mock_tx.return_value.__aenter__.return_value = mock_conn
        result = await repo.unified_search(ctx, query="Test", asset_type="agent")

    assert result['items'][0]['name'] == 'Test Agent'
    assert result['has_more'] is False


@pytest.mark.asyncio
async def test_catalog_repository_unified_detail():
    pool = MagicMock()
    repo = CatalogRepository(pool)
    asset_id = uuid4()

    mock_row = {
        'data': {
            'asset_id': str(asset_id),
            'asset_type': 'tool',
            'name': 'MCP Echo Tool',
            'description': 'Echoes input',
            'version': 1,
            'active': True
        }
    }

    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = mock_row

    mock_conn = AsyncMock()
    mock_conn.execute.return_value = mock_cursor

    ctx = MagicMock()
    ctx.session_id = uuid4()
    ctx.tenant_id = uuid4()

    with patch('app.catalog.repository.tenant_transaction') as mock_tx:
        mock_tx.return_value.__aenter__.return_value = mock_conn
        result = await repo.unified_detail(ctx, asset_id)

    assert result['name'] == 'MCP Echo Tool'
    assert result['asset_type'] == 'tool'
