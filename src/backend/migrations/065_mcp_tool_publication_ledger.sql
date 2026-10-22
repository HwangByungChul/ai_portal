-- 065_mcp_tool_publication_ledger.sql
-- Publication ledger for approved dynamic MCP tools.
-- Ensures immutable record of published exact revisions, risk policy signatures,
-- and PADMIN publication actor attribution.

CREATE TABLE IF NOT EXISTS portal.mcp_tool_publications (
    publication_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL REFERENCES portal.tenants(id),
    tool_id              text NOT NULL,
    version_id           uuid NOT NULL,
    revision_number      bigint NOT NULL,
    approval_request_id   uuid NOT NULL,
    schema_digest        text NOT NULL,
    risk_policy_id       text NOT NULL,
    risk_policy_revision bigint NOT NULL,
    published_by         uuid NOT NULL,
    published_at         timestamptz NOT NULL DEFAULT now(),
    retired_at           timestamptz,
    retired_by           uuid,
    status               text NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'retired', 'superseded')),
    CONSTRAINT uq_mcp_tool_publications_rev UNIQUE (tenant_id, tool_id, revision_number)
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_publications_lookup
    ON portal.mcp_tool_publications(tenant_id, tool_id, status);

ALTER TABLE portal.mcp_tool_publications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mcp_tool_publications_tenant_isolation ON portal.mcp_tool_publications;
CREATE POLICY mcp_tool_publications_tenant_isolation ON portal.mcp_tool_publications
    FOR SELECT
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid);

GRANT SELECT ON portal.mcp_tool_publications TO ai_web, ai_policy_executor;
GRANT ALL ON portal.mcp_tool_publications TO ai_policy_executor;
