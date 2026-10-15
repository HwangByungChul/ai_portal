-- Migration 052: MCP Tool Auto-Wrapping and Dynamic Environment Routing Schema
-- Supports T-035: Auto-wrapping of OpenAPI/WSDL/JDBC/Financial packets, and dev/prd dynamic routing based on approval status.

CREATE TABLE IF NOT EXISTS portal.mcp_tool_definitions (
    tool_id text NOT NULL,
    tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
    name text NOT NULL,
    description text NOT NULL,
    source_type text NOT NULL CHECK(source_type IN ('openapi', 'wsdl', 'jdbc', 'financial_packet', 'custom_mcp')),
    category text NOT NULL DEFAULT 'general',
    enabled boolean NOT NULL DEFAULT true,
    created_by uuid NOT NULL REFERENCES security.accounts(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(tenant_id, tool_id)
);

CREATE TABLE IF NOT EXISTS portal.mcp_tool_versions (
    version_id uuid NOT NULL DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
    tool_id text NOT NULL,
    revision_number bigint NOT NULL CHECK(revision_number > 0),
    mcp_tool_spec jsonb NOT NULL,
    raw_source_spec jsonb NOT NULL,
    execution_timeout_sec int NOT NULL DEFAULT 10,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(tenant_id, version_id),
    UNIQUE(tenant_id, tool_id, revision_number),
    FOREIGN KEY(tenant_id, tool_id) REFERENCES portal.mcp_tool_definitions(tenant_id, tool_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS portal.mcp_tool_endpoint_profiles (
    profile_id uuid NOT NULL DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
    tool_id text NOT NULL,
    target_env text NOT NULL CHECK(target_env IN ('development', 'production')),
    protocol_type text NOT NULL CHECK(protocol_type IN ('mcp_http_sse', 'rest_http', 'soap_xml', 'tcp_socket', 'jdbc_view')),
    base_endpoint_url text NOT NULL,
    encrypted_credential text,
    connection_timeout_ms int NOT NULL DEFAULT 5000,
    active boolean NOT NULL DEFAULT true,
    updated_by uuid NOT NULL REFERENCES security.accounts(user_id),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(tenant_id, profile_id),
    UNIQUE(tenant_id, tool_id, target_env),
    FOREIGN KEY(tenant_id, tool_id) REFERENCES portal.mcp_tool_definitions(tenant_id, tool_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS portal.mcp_tool_audit_logs (
    log_id uuid NOT NULL DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
    user_id uuid NOT NULL REFERENCES security.accounts(user_id),
    asset_id text,
    tool_id text NOT NULL,
    publication_status text NOT NULL CHECK(publication_status IN ('draft', 'trial', 'approved_published')),
    routed_env text NOT NULL CHECK(routed_env IN ('development', 'production')),
    routed_endpoint text NOT NULL,
    execution_status text NOT NULL CHECK(execution_status IN ('success', 'failed', 'timeout', 'blocked')),
    duration_ms int NOT NULL DEFAULT 0,
    client_request_id uuid,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(tenant_id, log_id)
);

ALTER TABLE portal.mcp_tool_definitions OWNER TO ai_owner;
ALTER TABLE portal.mcp_tool_versions OWNER TO ai_owner;
ALTER TABLE portal.mcp_tool_endpoint_profiles OWNER TO ai_owner;
ALTER TABLE portal.mcp_tool_audit_logs OWNER TO ai_owner;

ALTER TABLE portal.mcp_tool_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.mcp_tool_definitions FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.mcp_tool_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.mcp_tool_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.mcp_tool_endpoint_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.mcp_tool_endpoint_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.mcp_tool_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.mcp_tool_audit_logs FORCE ROW LEVEL SECURITY;

REVOKE ALL ON portal.mcp_tool_definitions, portal.mcp_tool_versions, portal.mcp_tool_endpoint_profiles, portal.mcp_tool_audit_logs FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT, UPDATE ON portal.mcp_tool_definitions TO ai_policy_executor;
GRANT SELECT, INSERT ON portal.mcp_tool_versions TO ai_policy_executor;
GRANT SELECT, INSERT, UPDATE ON portal.mcp_tool_endpoint_profiles TO ai_policy_executor;
GRANT SELECT, INSERT ON portal.mcp_tool_audit_logs TO ai_policy_executor;

CREATE POLICY mcp_tool_def_tenant ON portal.mcp_tool_definitions TO ai_policy_executor
    USING(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND security.can_read_agent(tenant_id))
    WITH CHECK(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND security.can_manage_current_tenant(tenant_id));

CREATE POLICY mcp_tool_ver_tenant ON portal.mcp_tool_versions TO ai_policy_executor
    USING(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND security.can_read_agent(tenant_id))
    WITH CHECK(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND security.can_manage_current_tenant(tenant_id));

CREATE POLICY mcp_tool_prof_tenant ON portal.mcp_tool_endpoint_profiles TO ai_policy_executor
    USING(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND security.can_manage_current_tenant(tenant_id))
    WITH CHECK(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND security.can_manage_current_tenant(tenant_id));

CREATE POLICY mcp_tool_audit_tenant ON portal.mcp_tool_audit_logs TO ai_policy_executor
    USING(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND security.can_manage_current_tenant(tenant_id))
    WITH CHECK(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
