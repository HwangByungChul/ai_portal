-- 067_mcp_tool_audit_ledger.sql
-- Append-only audit ledger for MCP Tool Gateway invocations, outcomes, and safety events.
-- Blocks UPDATE and DELETE triggers to preserve non-repudiation audit trail.

CREATE TABLE IF NOT EXISTS portal.mcp_tool_audit_events (
    event_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL REFERENCES portal.tenants(id),
    tool_id            text NOT NULL,
    version_id         uuid,
    revision_number    bigint,
    actor_id           uuid NOT NULL,
    trace_id           text NOT NULL,
    event_type         text NOT NULL
                       CHECK (event_type IN ('invocation', 'result', 'error', 'rate_limit', 'circuit_open', 'approval', 'publication', 'retirement')),
    credential_ref_id  text,
    argument_digest    text NOT NULL,
    response_digest    text,
    duration_ms        int,
    status             text NOT NULL
                       CHECK (status IN ('success', 'failed', 'timeout', 'blocked')),
    error_code         text,
    chain_hash         text,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_audit_tenant_trace
    ON portal.mcp_tool_audit_events(tenant_id, trace_id, created_at);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_audit_tenant_tool
    ON portal.mcp_tool_audit_events(tenant_id, tool_id, created_at DESC);

-- Append-only enforcement trigger
CREATE OR REPLACE FUNCTION portal.prevent_audit_modification()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'AUDIT_LOG_IMMUTABLE' USING ERRCODE='A0403';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_events_immutable ON portal.mcp_tool_audit_events;
CREATE TRIGGER trg_audit_events_immutable
    BEFORE UPDATE OR DELETE ON portal.mcp_tool_audit_events
    FOR EACH ROW EXECUTE FUNCTION portal.prevent_audit_modification();

ALTER TABLE portal.mcp_tool_audit_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mcp_tool_audit_tenant_isolation ON portal.mcp_tool_audit_events;
CREATE POLICY mcp_tool_audit_tenant_isolation ON portal.mcp_tool_audit_events
    FOR SELECT
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid);

GRANT SELECT, INSERT ON portal.mcp_tool_audit_events TO ai_web, ai_policy_executor;
