-- Dedicated tenant-authorized read boundary. Preserve prior migration sources.
-- Aggregate all enabled Tools into a single ordered array, including the empty case.
CREATE FUNCTION security.mcp_tool_registry_list(p_session uuid, p_tenant uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, security, portal, pg_temp
AS $function$
DECLARE
    items jsonb;
BEGIN
    PERFORM security.operations_authorize(p_session, p_tenant, 'agent_admin', false);

    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'tool_id', d.tool_id,
        'name', d.name,
        'description', d.description,
        'source_type', d.source_type,
        'input_schema', coalesce(v.mcp_tool_spec->'inputSchema', '{}'::jsonb),
        'revision_number', v.revision_number,
        'enabled', d.enabled,
        'has_dev_profile', EXISTS(
            SELECT 1 FROM portal.mcp_tool_endpoint_profiles pd
            WHERE pd.tenant_id = d.tenant_id AND pd.tool_id = d.tool_id
              AND pd.target_env = 'development' AND pd.active
        ),
        'has_prd_profile', EXISTS(
            SELECT 1 FROM portal.mcp_tool_endpoint_profiles pp
            WHERE pp.tenant_id = d.tenant_id AND pp.tool_id = d.tool_id
              AND pp.target_env = 'production' AND pp.active
        )
    ) ORDER BY d.name, d.tool_id), '[]'::jsonb)
    INTO items
    FROM portal.mcp_tool_definitions d
    LEFT JOIN LATERAL (
        SELECT revision_number, mcp_tool_spec
        FROM portal.mcp_tool_versions
        WHERE tenant_id = d.tenant_id AND tool_id = d.tool_id
        ORDER BY revision_number DESC LIMIT 1
    ) v ON true
    WHERE d.tenant_id = p_tenant AND d.enabled;

    RETURN jsonb_build_object('items', items);
END;
$function$;

ALTER FUNCTION security.mcp_tool_registry_list(uuid, uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.mcp_tool_registry_list(uuid, uuid)
    FROM PUBLIC, ai_index, ai_meter;
GRANT EXECUTE ON FUNCTION security.mcp_tool_registry_list(uuid, uuid) TO ai_web;
REVOKE ALL ON portal.mcp_tool_definitions, portal.mcp_tool_versions,
    portal.mcp_tool_endpoint_profiles FROM PUBLIC, ai_web, ai_index, ai_meter;
