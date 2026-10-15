
DECLARE
 u uuid := NULLIF(current_setting('app.user_id', true), '')::uuid;
 pub portal.asset_publications%ROWTYPE;
 previous portal.catalog_mutations%ROWTYPE;
 expected bigint;
 actual bigint;
 active_val boolean;
 res jsonb;
BEGIN
 PERFORM security.run_authorize(p_session, p_tenant, true);
 IF p_client_request_id IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF jsonb_typeof(p_body) <> 'object' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF (p_body ? 'expected_revision') AND jsonb_typeof(p_body->'expected_revision') = 'number' THEN
  expected := (p_body->>'expected_revision')::bigint;
 ELSE
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
 END IF;
 IF (p_body ? 'active') AND jsonb_typeof(p_body->'active') = 'boolean' THEN
  active_val := (p_body->>'active')::boolean;
 ELSE
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
 END IF;

 -- Must be an existing published asset visible to the user
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id = p_tenant AND asset_id = p_asset AND status = 'published';
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF pub.audience <> 'all' AND NOT (u = ANY(pub.member_ids)) THEN
  RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';
 END IF;

 -- Idempotent retry check
 SELECT * INTO previous FROM portal.catalog_mutations WHERE tenant_id = p_tenant AND user_id = u AND client_request_id = p_client_request_id;
 IF FOUND THEN
  IF previous.action <> 'dynamic_favorite' OR previous.target_id <> p_asset OR previous.body <> p_body THEN
   RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
  END IF;
  RETURN previous.response || jsonb_build_object('replayed', true);
 END IF;

 -- CAS revision check
 SELECT revision INTO actual FROM portal.dynamic_agent_favorites WHERE tenant_id = p_tenant AND user_id = u AND asset_id = p_asset;
 IF COALESCE(actual, 0) <> expected THEN
  RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
 END IF;

 INSERT INTO portal.dynamic_agent_favorites(tenant_id, user_id, asset_id, active, revision)
 VALUES(p_tenant, u, p_asset, active_val, expected + 1)
 ON CONFLICT (tenant_id, user_id, asset_id)
 DO UPDATE SET active = EXCLUDED.active, revision = EXCLUDED.revision, updated_at = clock_timestamp();

 res := jsonb_build_object('asset_id', p_asset, 'active', active_val, 'revision', expected + 1, 'replayed', false);

 INSERT INTO ops.audit_events(event_id, scope_kind, tenant_id, actor_id, action, opaque_target_id, result, revisions)
 VALUES(p_trace, 'tenant', p_tenant, u, 'catalog.dynamic_favorite', p_asset, 'ok', jsonb_build_object('revision', expected + 1));

 INSERT INTO portal.catalog_mutations(tenant_id, user_id, client_request_id, action, target_id, body, response)
 VALUES(p_tenant, u, p_client_request_id, 'dynamic_favorite', p_asset, p_body, res);

 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN res;
END;