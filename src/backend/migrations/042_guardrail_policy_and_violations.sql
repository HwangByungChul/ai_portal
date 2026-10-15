-- Migration 042: Guardrail Policy & Violation Audit Persistence
-- Tables: ops.guardrail_policy_versions, ops.guardrail_policy_heads, ops.guardrail_violations

CREATE TABLE IF NOT EXISTS ops.guardrail_policy_versions (
  tenant_id uuid NOT NULL,
  revision int NOT NULL CHECK(revision > 0),
  engine_revision text NOT NULL,
  policy jsonb NOT NULL,
  actor_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, revision),
  FOREIGN KEY (tenant_id) REFERENCES security.tenants(tenant_id)
);

ALTER TABLE ops.guardrail_policy_versions OWNER TO ai_owner;
ALTER TABLE ops.guardrail_policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.guardrail_policy_versions FORCE ROW LEVEL SECURITY;

REVOKE ALL ON ops.guardrail_policy_versions FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT ON ops.guardrail_policy_versions TO ai_policy_executor;

DROP POLICY IF EXISTS guardrail_policy_versions_tenant ON ops.guardrail_policy_versions;
CREATE POLICY guardrail_policy_versions_tenant ON ops.guardrail_policy_versions TO ai_policy_executor USING (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
) WITH CHECK (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);


CREATE TABLE IF NOT EXISTS ops.guardrail_policy_heads (
  tenant_id uuid NOT NULL PRIMARY KEY,
  current_revision int NOT NULL CHECK(current_revision > 0),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (tenant_id) REFERENCES security.tenants(tenant_id)
);

ALTER TABLE ops.guardrail_policy_heads OWNER TO ai_owner;
ALTER TABLE ops.guardrail_policy_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.guardrail_policy_heads FORCE ROW LEVEL SECURITY;

REVOKE ALL ON ops.guardrail_policy_heads FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT, UPDATE ON ops.guardrail_policy_heads TO ai_policy_executor;

DROP POLICY IF EXISTS guardrail_policy_heads_tenant ON ops.guardrail_policy_heads;
CREATE POLICY guardrail_policy_heads_tenant ON ops.guardrail_policy_heads TO ai_policy_executor USING (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
) WITH CHECK (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);


CREATE TABLE IF NOT EXISTS ops.guardrail_violations (
  tenant_id uuid NOT NULL,
  violation_id uuid NOT NULL,
  user_id uuid NOT NULL,
  run_id uuid,
  direction text NOT NULL CHECK(direction IN ('input', 'output')),
  rules text[] NOT NULL,
  content_hash text NOT NULL,
  policy_revision int NOT NULL,
  trace_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, violation_id),
  FOREIGN KEY (tenant_id) REFERENCES security.tenants(tenant_id)
);

ALTER TABLE ops.guardrail_violations OWNER TO ai_owner;
ALTER TABLE ops.guardrail_violations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.guardrail_violations FORCE ROW LEVEL SECURITY;

REVOKE ALL ON ops.guardrail_violations FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT ON ops.guardrail_violations TO ai_policy_executor;

DROP POLICY IF EXISTS guardrail_violations_tenant ON ops.guardrail_violations;
CREATE POLICY guardrail_violations_tenant ON ops.guardrail_violations TO ai_policy_executor USING (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
) WITH CHECK (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);

DROP POLICY IF EXISTS audit_guardrail_policy_events ON ops.audit_events;
CREATE POLICY audit_guardrail_policy_events ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK (
  session_user = 'ai_web' AND scope_kind = 'tenant' AND actor_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  AND action = 'guardrail.policy_update'
);


-- Function: Read guardrail policy for a tenant
CREATE OR REPLACE FUNCTION security.guardrail_policy_read(
  p_session uuid,
  p_tenant uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  v_role text;
  v_head record;
  v_ver record;
BEGIN
  PERFORM security.run_authorize(p_session, p_tenant, false);
  SELECT effective_role INTO v_role FROM security.current_membership(p_session, p_tenant);
  IF v_role != 'PADMIN' THEN
    RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';
  END IF;

  SELECT current_revision INTO v_head FROM ops.guardrail_policy_heads WHERE tenant_id = p_tenant;
  IF NOT FOUND THEN
    -- Return default policy v1
    RETURN jsonb_build_object(
      'revision', 1,
      'engine_revision', 'guardrail-v1',
      'input_enabled', true,
      'output_enabled', true,
      'pii_severity', 'block',
      'injection_severity', 'block',
      'forbidden_severity', 'block',
      'output_pii_action', 'mask'
    );
  END IF;

  SELECT policy, engine_revision INTO v_ver
  FROM ops.guardrail_policy_versions
  WHERE tenant_id = p_tenant AND revision = v_head.current_revision;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'revision', v_head.current_revision,
      'engine_revision', 'guardrail-v1',
      'input_enabled', true,
      'output_enabled', true,
      'pii_severity', 'block',
      'injection_severity', 'block',
      'forbidden_severity', 'block',
      'output_pii_action', 'mask'
    );
  END IF;

  RETURN v_ver.policy || jsonb_build_object(
    'revision', v_head.current_revision,
    'engine_revision', v_ver.engine_revision
  );
END;
$body$;

ALTER FUNCTION security.guardrail_policy_read(uuid, uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.guardrail_policy_read(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.guardrail_policy_read(uuid, uuid) TO ai_web;


-- Function: Update guardrail policy (CAS with expected_revision)
CREATE OR REPLACE FUNCTION security.guardrail_policy_update(
  p_session uuid,
  p_trace uuid,
  p_tenant uuid,
  p_expected_revision int,
  p_policy jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  v_u uuid := NULLIF(current_setting('app.user_id', true), '')::uuid;
  v_role text;
  v_head record;
  v_next_rev int;
  v_new_policy jsonb;
BEGIN
  PERFORM security.run_authorize(p_session, p_tenant, true);
  SELECT effective_role INTO v_role FROM security.current_membership(p_session, p_tenant);
  IF v_role != 'PADMIN' THEN
    RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';
  END IF;

  SELECT current_revision INTO v_head FROM ops.guardrail_policy_heads WHERE tenant_id = p_tenant FOR UPDATE;
  IF NOT FOUND THEN
    IF p_expected_revision != 1 THEN
      RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
    END IF;
    v_next_rev := 2;
    INSERT INTO ops.guardrail_policy_heads(tenant_id, current_revision, updated_at)
    VALUES (p_tenant, v_next_rev, clock_timestamp());
  ELSE
    IF v_head.current_revision != p_expected_revision THEN
      RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
    END IF;
    v_next_rev := v_head.current_revision + 1;
    UPDATE ops.guardrail_policy_heads
    SET current_revision = v_next_rev, updated_at = clock_timestamp()
    WHERE tenant_id = p_tenant;
  END IF;

  v_new_policy := p_policy || jsonb_build_object('revision', v_next_rev, 'engine_revision', 'guardrail-v1');

  INSERT INTO ops.guardrail_policy_versions(
    tenant_id, revision, engine_revision, policy, actor_id, created_at
  ) VALUES (
    p_tenant, v_next_rev, 'guardrail-v1', v_new_policy, v_u, clock_timestamp()
  );

  INSERT INTO ops.audit_events (
    event_id, scope_kind, tenant_id, actor_id, action, opaque_target_id, result, revisions
  ) VALUES (
    gen_random_uuid(), 'tenant', p_tenant, v_u, 'guardrail.policy_update', gen_random_uuid(), 'success',
    jsonb_build_object('expected_revision', p_expected_revision, 'new_revision', v_next_rev)
  );

  RETURN v_new_policy;
END;
$body$;

ALTER FUNCTION security.guardrail_policy_update(uuid, uuid, uuid, int, jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.guardrail_policy_update(uuid, uuid, uuid, int, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.guardrail_policy_update(uuid, uuid, uuid, int, jsonb) TO ai_web;


-- Function: Append violation (append-only, no raw text stored)
CREATE OR REPLACE FUNCTION security.guardrail_violation_append(
  p_session uuid,
  p_trace uuid,
  p_tenant uuid,
  p_user uuid,
  p_run uuid,
  p_direction text,
  p_rules text[],
  p_hash text,
  p_policy_revision int
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  v_violation_id uuid := gen_random_uuid();
BEGIN
  PERFORM security.run_authorize(p_session, p_tenant, false);

  IF p_direction NOT IN ('input', 'output') THEN
    RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
  END IF;

  INSERT INTO ops.guardrail_violations(
    tenant_id, violation_id, user_id, run_id, direction, rules, content_hash, policy_revision, trace_id, created_at
  ) VALUES (
    p_tenant, v_violation_id, p_user, p_run, p_direction, p_rules, p_hash, p_policy_revision, p_trace, clock_timestamp()
  );

  RETURN v_violation_id;
END;
$body$;

ALTER FUNCTION security.guardrail_violation_append(uuid, uuid, uuid, uuid, uuid, text, text[], text, int) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.guardrail_violation_append(uuid, uuid, uuid, uuid, uuid, text, text[], text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.guardrail_violation_append(uuid, uuid, uuid, uuid, uuid, text, text[], text, int) TO ai_web;


-- Function: List violations for a tenant (PADMIN only, keyset paging)
CREATE OR REPLACE FUNCTION security.guardrail_violations_list(
  p_session uuid,
  p_tenant uuid,
  p_limit int DEFAULT 50,
  p_cursor timestamptz DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  v_role text;
  v_items jsonb;
  v_total bigint;
BEGIN
  PERFORM security.run_authorize(p_session, p_tenant, false);
  SELECT effective_role INTO v_role FROM security.current_membership(p_session, p_tenant);
  IF v_role != 'PADMIN' THEN
    RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';
  END IF;

  SELECT count(*) INTO v_total FROM ops.guardrail_violations WHERE tenant_id = p_tenant;

  SELECT coalesce(jsonb_agg(
    jsonb_build_object(
      'violation_id', v.violation_id,
      'tenant_id', v.tenant_id,
      'user_id', v.user_id,
      'run_id', v.run_id,
      'direction', v.direction,
      'rule_ids', v.rules,
      'content_hash', v.content_hash,
      'policy_revision', v.policy_revision,
      'created_at', v.created_at
    ) ORDER BY v.created_at DESC
  ), '[]'::jsonb) INTO v_items
  FROM (
    SELECT * FROM ops.guardrail_violations
    WHERE tenant_id = p_tenant
      AND (p_cursor IS NULL OR created_at < p_cursor)
    ORDER BY created_at DESC
    LIMIT least(greatest(coalesce(p_limit, 50), 1), 100)
  ) v;

  RETURN jsonb_build_object(
    'items', v_items,
    'total_count', v_total
  );
END;
$body$;

ALTER FUNCTION security.guardrail_violations_list(uuid, uuid, int, timestamptz) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.guardrail_violations_list(uuid, uuid, int, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.guardrail_violations_list(uuid, uuid, int, timestamptz) TO ai_web;
