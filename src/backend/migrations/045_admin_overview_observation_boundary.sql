-- Migration 045: Admin Overview Metrics and Monitoring RPC
-- Supports: GET /api/v1/admin/overview
-- Strictly tenant-scoped, no cross-tenant leakage, no internal secrets.

CREATE OR REPLACE FUNCTION security.admin_overview_read(
  p_session uuid,
  p_tenant uuid,
  p_date_from date,
  p_date_to date
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  v_member record;
  v_calls bigint := 0;
  v_unknown bigint := 0;
  v_reserved numeric := 0;
  v_confirmed numeric := 0;
  v_settings_count bigint := 0;
  v_dynamic_count bigint := 0;
  v_daily jsonb := '[]'::jsonb;
  v_pending_items jsonb := '[]'::jsonb;
BEGIN
  -- 1. Authorization: Valid session & can_manage membership (PADMIN or TADMIN)
  SELECT m.effective_role, m.can_manage INTO v_member
  FROM security.current_membership(p_session, p_tenant) m;
  IF NOT FOUND OR NOT v_member.can_manage THEN
    RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';
  END IF;

  -- 2. Validate date range (maximum 31 days)
  IF p_date_from IS NULL OR p_date_to IS NULL OR p_date_to < p_date_from OR (p_date_to - p_date_from) >= 31 THEN
    RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
  END IF;

  -- 3. Aggregations from ops.call_attempts
  SELECT
    count(*),
    count(*) FILTER (WHERE state = 'usage_unknown'),
    COALESCE(sum(reserved_krw) FILTER (WHERE state IN ('reserved', 'dispatched', 'usage_unknown')), 0)
  INTO v_calls, v_unknown, v_reserved
  FROM ops.call_attempts
  WHERE tenant_id = p_tenant
    AND (created_at AT TIME ZONE 'Asia/Seoul')::date >= p_date_from
    AND (created_at AT TIME ZONE 'Asia/Seoul')::date <= p_date_to;

  -- 4. Confirmed amount from ops.usage_events
  SELECT COALESCE(sum(delta_accounted_krw), 0)
  INTO v_confirmed
  FROM ops.usage_events
  WHERE tenant_id = p_tenant
    AND event_kind = 'settle'
    AND (created_at AT TIME ZONE 'Asia/Seoul')::date >= p_date_from
    AND (created_at AT TIME ZONE 'Asia/Seoul')::date <= p_date_to;

  -- 5. Daily trend series
  WITH days AS (
    SELECT generate_series(p_date_from::timestamp, p_date_to::timestamp, '1 day'::interval)::date AS day
  ),
  calls_by_day AS (
    SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS day, count(*) AS call_count
    FROM ops.call_attempts
    WHERE tenant_id = p_tenant
      AND (created_at AT TIME ZONE 'Asia/Seoul')::date >= p_date_from
      AND (created_at AT TIME ZONE 'Asia/Seoul')::date <= p_date_to
    GROUP BY (created_at AT TIME ZONE 'Asia/Seoul')::date
  ),
  usage_by_day AS (
    SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS day, COALESCE(sum(delta_accounted_krw), 0) AS amount
    FROM ops.usage_events
    WHERE tenant_id = p_tenant
      AND event_kind = 'settle'
      AND (created_at AT TIME ZONE 'Asia/Seoul')::date >= p_date_from
      AND (created_at AT TIME ZONE 'Asia/Seoul')::date <= p_date_to
    GROUP BY (created_at AT TIME ZONE 'Asia/Seoul')::date
  )
  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'date', to_char(d.day, 'YYYY-MM-DD'),
      'calls', COALESCE(c.call_count, 0),
      'confirmed_amount', COALESCE(u.amount, 0)
    ) ORDER BY d.day
  ), '[]'::jsonb)
  INTO v_daily
  FROM days d
  LEFT JOIN calls_by_day c ON c.day = d.day
  LEFT JOIN usage_by_day u ON u.day = d.day;

  -- 6. Pending deployments count & items
  SELECT count(*) INTO v_settings_count
  FROM portal.agent_deployments
  WHERE tenant_id = p_tenant AND status = 'pending';

  SELECT count(*) INTO v_dynamic_count
  FROM portal.asset_deployments
  WHERE tenant_id = p_tenant AND status = 'pending';

  WITH pending_all AS (
    SELECT
      'settings' AS kind,
      request_id,
      requester_id,
      created_at,
      COALESCE(proposed->>'name', agent_key) AS asset_name,
      base_version
    FROM portal.agent_deployments
    WHERE tenant_id = p_tenant AND status = 'pending'
    UNION ALL
    SELECT
      'dynamic' AS kind,
      request_id,
      requester_id,
      created_at,
      COALESCE(snapshot->>'name', body->>'asset_name', '동적 Agent') AS asset_name,
      expected_publication_revision AS base_version
    FROM portal.asset_deployments
    WHERE tenant_id = p_tenant AND status = 'pending'
  )
  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'kind', p.kind,
      'request_id', p.request_id,
      'requester_id', p.requester_id,
      'asset_name', p.asset_name,
      'base_version', p.base_version,
      'created_at', p.created_at
    ) ORDER BY p.created_at DESC
  ), '[]'::jsonb)
  INTO v_pending_items
  FROM (
    SELECT * FROM pending_all ORDER BY created_at DESC LIMIT 5
  ) p;

  -- 7. Response assembly
  RETURN jsonb_build_object(
    'as_of', clock_timestamp(),
    'period', jsonb_build_object('from', to_char(p_date_from, 'YYYY-MM-DD'), 'to', to_char(p_date_to, 'YYYY-MM-DD')),
    'timezone', 'Asia/Seoul',
    'metrics', jsonb_build_object(
      'calls', v_calls,
      'confirmed_amount', v_confirmed,
      'reserved_amount', v_reserved,
      'unknown_calls', v_unknown
    ),
    'daily_calls', v_daily,
    'pending', jsonb_build_object(
      'settings', v_settings_count,
      'dynamic', v_dynamic_count,
      'total', v_settings_count + v_dynamic_count,
      'items', v_pending_items
    ),
    'services', jsonb_build_array(
      jsonb_build_object('service_name', 'PostgreSQL Data Cluster', 'status', 'unknown', 'observed_at', NULL, 'source', 'unconfigured_collector', 'scope', 'tenant'),
      jsonb_build_object('service_name', 'AI Inference Gateway', 'status', 'unknown', 'observed_at', NULL, 'source', 'unconfigured_collector', 'scope', 'tenant'),
      jsonb_build_object('service_name', 'Guardrails Safety Engine', 'status', 'unknown', 'observed_at', NULL, 'source', 'unconfigured_collector', 'scope', 'tenant')
    )
  );
END;
$body$;

ALTER FUNCTION security.admin_overview_read(uuid, uuid, date, date) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.admin_overview_read(uuid, uuid, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.admin_overview_read(uuid, uuid, date, date) TO ai_web;
