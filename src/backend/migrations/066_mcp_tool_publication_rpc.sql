-- 066_mcp_tool_publication_rpc.sql
-- RPC for managing MCP tool publication lifecycle and self-approval block.
-- Requires PADMIN role and prohibits author self-publication.

CREATE OR REPLACE FUNCTION security.mcp_tool_publication_control(
    p_session uuid,
    p_tenant uuid,
    p_action text,
    p_tool text,
    p_request_id uuid,
    p_expected_revision bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,security,portal,pg_temp AS $body$
DECLARE
    u uuid;
    appr portal.tool_approvals%ROWTYPE;
    ver portal.mcp_tool_versions%ROWTYPE;
    pub_id uuid;
    desc_val jsonb;
    cur_pub portal.mcp_tool_publications%ROWTYPE;
BEGIN
    u := security.operations_authorize(p_session, p_tenant, 'agent_admin', p_action IN ('publish', 'retire'));

    IF p_action NOT IN ('publish', 'retire', 'query') THEN
        RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
    END IF;

    IF p_tool IS NULL OR p_tool !~ '^[a-zA-Z][a-zA-Z0-9_-]{1,99}$' THEN
        RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
    END IF;

    -- Query current publication status
    IF p_action = 'query' THEN
        SELECT * INTO cur_pub
        FROM portal.mcp_tool_publications
        WHERE tenant_id = p_tenant AND tool_id = p_tool AND status = 'active';

        IF NOT FOUND THEN
            RETURN jsonb_build_object(
                'tool_id', p_tool,
                'status', 'none',
                'has_active_publication', false
            );
        END IF;

        RETURN jsonb_build_object(
            'publication_id', cur_pub.publication_id,
            'tool_id', cur_pub.tool_id,
            'revision_number', cur_pub.revision_number,
            'status', cur_pub.status,
            'published_at', cur_pub.published_at,
            'has_active_publication', true
        );
    END IF;

    -- For publish and retire, enforce PADMIN role
    IF (SELECT effective_role FROM security.current_membership(p_session, p_tenant)) <> 'PADMIN' THEN
        RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text || ':tool-pub:' || p_tool, 0));

    -- Handle retirement
    IF p_action = 'retire' THEN
        SELECT * INTO cur_pub
        FROM portal.mcp_tool_publications
        WHERE tenant_id = p_tenant AND tool_id = p_tool AND status = 'active';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';
        END IF;

        UPDATE portal.mcp_tool_publications
        SET status = 'retired', retired_at = now(), retired_by = u
        WHERE publication_id = cur_pub.publication_id;

        INSERT INTO ops.audit_events(event_id, scope_kind, tenant_id, actor_id, action, opaque_target_id, result)
        VALUES(gen_random_uuid(), 'tenant', p_tenant, u, 'tool.retired', cur_pub.publication_id, 'ok');

        RETURN jsonb_build_object(
            'publication_id', cur_pub.publication_id,
            'tool_id', p_tool,
            'status', 'retired',
            'retired_at', now()
        );
    END IF;

    -- Handle publication
    SELECT * INTO appr
    FROM portal.tool_approvals
    WHERE tenant_id = p_tenant AND request_id = p_request_id AND tool_id = p_tool;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';
    END IF;

    -- Self-Approval Block: Creator cannot publish own requested review
    IF appr.requester_id = u THEN
        RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';
    END IF;

    -- Expected revision check
    IF appr.expected_head_revision <> p_expected_revision THEN
        RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
    END IF;

    desc_val := appr.descriptor;

    -- Lookup version row
    SELECT * INTO ver
    FROM portal.mcp_tool_versions
    WHERE tenant_id = p_tenant AND tool_id = p_tool AND revision_number = p_expected_revision;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';
    END IF;

    -- Supersede any existing active publication
    UPDATE portal.mcp_tool_publications
    SET status = 'superseded'
    WHERE tenant_id = p_tenant AND tool_id = p_tool AND status = 'active';

    -- Insert new active publication record
    pub_id := gen_random_uuid();
    INSERT INTO portal.mcp_tool_publications (
        publication_id,
        tenant_id,
        tool_id,
        version_id,
        revision_number,
        approval_request_id,
        schema_digest,
        risk_policy_id,
        risk_policy_revision,
        published_by,
        published_at,
        status
    ) VALUES (
        pub_id,
        p_tenant,
        p_tool,
        ver.version_id,
        ver.revision_number,
        p_request_id,
        coalesce(desc_val->>'digest', ''),
        coalesce(desc_val->>'risk_policy_id', 'dynamic-default-v1'),
        coalesce((desc_val->>'risk_policy_revision')::bigint, 1),
        u,
        now(),
        'active'
    );

    INSERT INTO ops.audit_events(event_id, scope_kind, tenant_id, actor_id, action, opaque_target_id, result)
    VALUES(gen_random_uuid(), 'tenant', p_tenant, u, 'tool.published', pub_id, 'ok');

    RETURN jsonb_build_object(
        'publication_id', pub_id,
        'tool_id', p_tool,
        'revision_number', ver.revision_number,
        'status', 'active',
        'published_by', u
    );
END;
$body$;

ALTER FUNCTION security.mcp_tool_publication_control(uuid, uuid, text, text, uuid, bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.mcp_tool_publication_control(uuid, uuid, text, text, uuid, bigint) FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT EXECUTE ON FUNCTION security.mcp_tool_publication_control(uuid, uuid, text, text, uuid, bigint) TO ai_web;
