-- Migration 040: Dynamic Agent Favorites for My Agent
CREATE TABLE IF NOT EXISTS portal.dynamic_agent_favorites (
 tenant_id uuid NOT NULL,
 user_id uuid NOT NULL,
 asset_id uuid NOT NULL,
 active boolean NOT NULL,
 revision bigint NOT NULL CHECK(revision > 0),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id, user_id, asset_id),
 FOREIGN KEY(tenant_id, asset_id) REFERENCES portal.assets(tenant_id, asset_id),
 FOREIGN KEY(tenant_id, user_id) REFERENCES security.memberships(tenant_id, user_id)
);

ALTER TABLE portal.dynamic_agent_favorites OWNER TO ai_owner;
ALTER TABLE portal.dynamic_agent_favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.dynamic_agent_favorites FORCE ROW LEVEL SECURITY;

REVOKE ALL ON portal.dynamic_agent_favorites FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT, UPDATE ON portal.dynamic_agent_favorites TO ai_policy_executor;

DROP POLICY IF EXISTS dynamic_agent_favorite_own ON portal.dynamic_agent_favorites;
CREATE POLICY dynamic_agent_favorite_own ON portal.dynamic_agent_favorites TO ai_policy_executor USING (
 tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
 AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
 AND security.can_read_own_conversation(tenant_id, user_id)
) WITH CHECK (
 tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
 AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
 AND security.can_read_own_conversation(tenant_id, user_id)
);

DROP POLICY IF EXISTS audit_dynamic_favorite ON ops.audit_events;
CREATE POLICY audit_dynamic_favorite ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK (
 session_user = 'ai_web' AND scope_kind = 'tenant' AND actor_id = NULLIF(current_setting('app.user_id', true), '')::uuid
 AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND action = 'catalog.dynamic_favorite'
 AND security.can_read_own_conversation(tenant_id, actor_id)
);


CREATE OR REPLACE FUNCTION security.dynamic_favorite_mutate(
 p_session uuid,
 p_trace uuid,
 p_tenant uuid,
 p_asset uuid,
 p_client_request_id uuid,
 p_body jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
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
  IF previous.action <> 'favorite' OR previous.target_id <> p_asset OR previous.body <> p_body THEN
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
 VALUES(p_tenant, u, p_client_request_id, 'favorite', p_asset, p_body, res);

 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN res;
END;$body$;

ALTER FUNCTION security.dynamic_favorite_mutate(uuid, uuid, uuid, uuid, uuid, jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.dynamic_favorite_mutate(uuid, uuid, uuid, uuid, uuid, jsonb) FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT EXECUTE ON FUNCTION security.dynamic_favorite_mutate(uuid, uuid, uuid, uuid, uuid, jsonb) TO ai_web;

CREATE OR REPLACE FUNCTION security.published_agent_read(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE
 pub jsonb;items jsonb:='[]';entry jsonb;row record;cursor_id uuid;anchor timestamptz;next_id uuid;variables jsonb;
 u uuid:=NULLIF(current_setting('app.user_id',true),'')::uuid;
 f_active boolean; f_rev bigint; mine_filter boolean;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_action IS NULL OR p_action NOT IN ('list','detail','history','run') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR coalesce(p_mode,'') NOT IN ('mock','real') OR p_body-ARRAY['cursor','mine']<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='run' THEN
  IF p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM security.published_run_guard(p_session,p_tenant,p_id);RETURN security.run_view(p_tenant,p_id);
 END IF;
 IF p_action='history' THEN
  IF p_body->>'cursor' IS NOT NULL THEN
   SELECT r.created_at INTO anchor FROM portal.runs r JOIN portal.published_agent_runs q USING(tenant_id,run_id) WHERE r.tenant_id=p_tenant AND q.asset_id=p_id AND r.run_id=(p_body->>'cursor')::uuid;
   IF anchor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.run_id DESC),'[]') INTO items FROM
  (SELECT r.run_id,r.state,r.revision,r.asset_revision,r.asset_version_id,r.execution_mode,r.created_at FROM portal.runs r JOIN portal.published_agent_runs q USING(tenant_id,run_id)
   WHERE r.tenant_id=p_tenant AND q.asset_id=p_id AND (anchor IS NULL OR (r.created_at,r.run_id)<(anchor,(p_body->>'cursor')::uuid)) ORDER BY r.created_at DESC,r.run_id DESC LIMIT 21) x;
  IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'run_id')::uuid;END IF;
  RETURN jsonb_build_object('items',items,'next_cursor',next_id);
 END IF;
 cursor_id:=(p_body->>'cursor')::uuid;
 mine_filter:=COALESCE((p_body->>'mine')::boolean,false);
 IF p_action='detail' THEN
  IF p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  pub:=security.published_asset_guard(p_session,p_tenant,p_id,p_mode);
 ELSE
  IF cursor_id IS NOT NULL THEN
   PERFORM security.published_asset_guard(p_session,p_tenant,cursor_id,p_mode);
  END IF;
 END IF;
 FOR row IN SELECT asset_id FROM portal.asset_publications WHERE tenant_id=p_tenant AND status='published' AND execution_mode=p_mode
 AND (p_action='detail' AND asset_id=p_id OR p_action='list' AND (cursor_id IS NULL OR asset_id>cursor_id)) ORDER BY asset_id LOOP
  BEGIN pub:=security.published_asset_guard(p_session,p_tenant,row.asset_id,p_mode);
  EXCEPTION WHEN SQLSTATE 'A0404' OR SQLSTATE 'D0404' OR SQLSTATE 'B0340' THEN CONTINUE;END;
  SELECT active,revision INTO f_active,f_rev FROM portal.dynamic_agent_favorites WHERE tenant_id=p_tenant AND user_id=u AND asset_id=row.asset_id;
  IF mine_filter AND NOT COALESCE(f_active,false) THEN CONTINUE; END IF;
  SELECT coalesce(jsonb_agg(name ORDER BY name),'[]') INTO variables FROM
  (SELECT DISTINCT x[1] AS name FROM regexp_matches((pub->'profile'->>'system_prompt')||(pub->'profile'->>'developer_prompt')||(pub->'profile'->>'user_template'),'\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}','g') x) names;
  entry:=jsonb_build_object('asset_id',pub->'asset_id','version_id',pub->'version_id','revision',pub->'asset_revision','publication_revision',pub->'publication_revision',
  'name',pub->'config'->>'name','description',pub->'config'->>'description','agent_key',pub->'config'->>'execution_kind','execution_mode',pub->>'execution_mode','variables',variables,
  'available',true,'safe_block_reason',NULL,'favorite',COALESCE(f_active,false),'favorite_revision',COALESCE(f_rev,0));
  IF p_action='detail' THEN RETURN entry;END IF;
  items:=items||jsonb_build_array(entry);EXIT WHEN jsonb_array_length(items)=21;
 END LOOP;
 IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'asset_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
END;$body$;
ALTER FUNCTION security.published_agent_read(uuid,uuid,text,uuid,jsonb,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.published_agent_read(uuid,uuid,text,uuid,jsonb,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.published_agent_read(uuid,uuid,text,uuid,jsonb,text) TO ai_web;
