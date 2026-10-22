-- DP-10 확장: AI 자산 통합 카탈로그 뷰 (Agent + Tool + Workflow 통합 검색)
-- Prerequisite: migrations 000-071 applied.
SET search_path = security, public;

-- DP-10: Unified asset catalog view
CREATE OR REPLACE VIEW security.asset_catalog_unified AS
    -- Published dynamic agents
    SELECT
        asset_id,
        tenant_id,
        'agent'::TEXT           AS asset_type,
        name,
        description,
        category,
        COALESCE(tags, '[]'::jsonb) AS tags,
        revision                AS version,
        TRUE                    AS active,
        created_at,
        updated_at
    FROM security.dynamic_agents
    WHERE retired_at IS NULL
UNION ALL
    -- Approved MCP Tools (from mcp_tool_registry, published only)
    SELECT
        tool_id                 AS asset_id,
        tenant_id,
        'tool'::TEXT            AS asset_type,
        name,
        COALESCE(description, '') AS description,
        'tool'::TEXT            AS category,
        COALESCE(tags, '[]'::jsonb) AS tags,
        1                       AS version,
        (published_at IS NOT NULL AND retired_at IS NULL) AS active,
        created_at,
        updated_at
    FROM security.mcp_tool_registry
    WHERE retired_at IS NULL
UNION ALL
    -- Approved Workflows
    SELECT
        workflow_id             AS asset_id,
        tenant_id,
        'workflow'::TEXT        AS asset_type,
        name,
        COALESCE(description, '') AS description,
        'workflow'::TEXT        AS category,
        '[]'::jsonb             AS tags,
        version,
        active,
        created_at,
        updated_at
    FROM security.approved_workflows
    WHERE retired_at IS NULL;

-- GIN index on tags for fast tag-based search (agents table)
CREATE INDEX IF NOT EXISTS dynamic_agents_tags_gin
    ON security.dynamic_agents USING GIN(tags);

-- DP-10: Catalog search RPC (user-facing, RLS-scoped)
CREATE OR REPLACE FUNCTION security.catalog_unified_search(
    p_session    UUID,
    p_tenant     UUID,
    p_query      TEXT DEFAULT NULL,
    p_asset_type TEXT DEFAULT 'all',   -- 'all' | 'agent' | 'tool' | 'workflow'
    p_category   TEXT DEFAULT NULL,
    p_limit      INT  DEFAULT 20,
    p_cursor     TEXT DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE
    v_items  JSONB;
    v_count  INT;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);

    IF p_limit NOT BETWEEN 1 AND 50 THEN
        RAISE EXCEPTION 'LIMIT_INVALID' USING ERRCODE = 'A0400';
    END IF;

    SELECT jsonb_agg(row_to_json(t)::jsonb ORDER BY t.is_default DESC, t.name)
    INTO v_items
    FROM (
        SELECT
            asset_id::text,
            asset_type,
            name,
            description,
            category,
            tags,
            version,
            active,
            updated_at,
            (asset_type = 'agent' AND name ILIKE '%' || COALESCE(p_query, '') || '%') AS is_default
        FROM security.asset_catalog_unified
        WHERE tenant_id = p_tenant
          AND (p_asset_type = 'all' OR asset_type = p_asset_type)
          AND (p_category IS NULL OR category = p_category)
          AND (p_query IS NULL OR p_query = '' OR
               name ILIKE '%' || p_query || '%' OR
               description ILIKE '%' || p_query || '%')
        ORDER BY updated_at DESC
        LIMIT p_limit + 1
    ) t;

    SELECT COUNT(*) INTO v_count FROM jsonb_array_elements(COALESCE(v_items, '[]'::jsonb));

    RETURN jsonb_build_object(
        'items',       COALESCE(
            (SELECT jsonb_agg(x) FROM jsonb_array_elements(v_items) x LIMIT p_limit),
            '[]'::jsonb
        ),
        'has_more',    v_count > p_limit
    );
END;
$$;

-- DP-10: Single asset detail by type
CREATE OR REPLACE FUNCTION security.catalog_unified_detail(
    p_session  UUID,
    p_tenant   UUID,
    p_asset_id UUID
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_row JSONB;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT to_jsonb(t) INTO v_row
    FROM (
        SELECT asset_id::text, asset_type, name, description,
               category, tags, version, active, updated_at
        FROM security.asset_catalog_unified
        WHERE tenant_id = p_tenant AND asset_id = p_asset_id
        LIMIT 1
    ) t;
    IF v_row IS NULL THEN
        RAISE EXCEPTION 'ASSET_NOT_FOUND' USING ERRCODE = 'A0404';
    END IF;
    RETURN v_row;
END;
$$;

COMMENT ON VIEW security.asset_catalog_unified IS 'DP-10: Unified read-only view of all publishable AI assets (Agent/Tool/Workflow).';
