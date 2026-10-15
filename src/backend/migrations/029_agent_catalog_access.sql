-- DP10-01: personal favorites and explicit Agent access; no historical backfill.
CREATE TABLE portal.agent_access (
 tenant_id uuid NOT NULL,agent_key text NOT NULL,mode text NOT NULL CHECK(mode IN ('all','restricted')),
 member_ids uuid[] NOT NULL DEFAULT '{}',revision bigint NOT NULL CHECK(revision>0),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,agent_key),FOREIGN KEY(tenant_id,agent_key) REFERENCES portal.agent_configs(tenant_id,agent_key),
 CHECK(cardinality(member_ids)<=200 AND array_position(member_ids,NULL) IS NULL AND (mode<>'all' OR cardinality(member_ids)=0))
);
CREATE TABLE portal.agent_favorites (
 tenant_id uuid NOT NULL,user_id uuid NOT NULL,agent_key text NOT NULL,active boolean NOT NULL,revision bigint NOT NULL CHECK(revision>0),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,user_id,agent_key),FOREIGN KEY(tenant_id,agent_key) REFERENCES portal.agent_configs(tenant_id,agent_key),
 FOREIGN KEY(tenant_id,user_id) REFERENCES security.memberships(tenant_id,user_id)
);
CREATE TABLE portal.catalog_mutations (
 tenant_id uuid NOT NULL,user_id uuid NOT NULL,client_request_id uuid NOT NULL,action text NOT NULL CHECK(action IN ('favorite','access_set')),
 target_id uuid NOT NULL,body jsonb NOT NULL,response jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,user_id,client_request_id),FOREIGN KEY(tenant_id,user_id) REFERENCES security.memberships(tenant_id,user_id)
);
ALTER TABLE portal.agent_access OWNER TO ai_owner;
ALTER TABLE portal.agent_favorites OWNER TO ai_owner;
ALTER TABLE portal.catalog_mutations OWNER TO ai_owner;
ALTER TABLE portal.agent_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.agent_access FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.agent_favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.agent_favorites FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.catalog_mutations ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.catalog_mutations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.agent_access,portal.agent_favorites,portal.catalog_mutations FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT,UPDATE ON portal.agent_access,portal.agent_favorites TO ai_policy_executor;
GRANT SELECT,INSERT ON portal.catalog_mutations TO ai_policy_executor;
CREATE POLICY agent_access_read ON portal.agent_access FOR SELECT TO ai_policy_executor USING(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,NULLIF(current_setting('app.user_id',true),'')::uuid));
CREATE POLICY agent_access_insert ON portal.agent_access FOR INSERT TO ai_policy_executor WITH CHECK(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY agent_access_update ON portal.agent_access FOR UPDATE TO ai_policy_executor USING(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id)) WITH CHECK(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY agent_favorite_own ON portal.agent_favorites TO ai_policy_executor USING(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,user_id)) WITH CHECK(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,user_id));
CREATE POLICY catalog_mutation_own ON portal.catalog_mutations TO ai_policy_executor USING(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,user_id)) WITH CHECK(
 tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,user_id));
CREATE POLICY audit_catalog ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(
 session_user='ai_web' AND scope_kind='tenant' AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid
 AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND action IN ('catalog.favorite','catalog.access')
 AND security.can_read_own_conversation(tenant_id,actor_id) AND (action='catalog.favorite' OR security.can_manage_current_tenant(tenant_id)));

CREATE FUNCTION security.agent_access_allowed(p_tenant uuid,p_agent text) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE a portal.agent_access%ROWTYPE;u uuid:=NULLIF(current_setting('app.user_id',true),'')::uuid;
BEGIN
 IF NOT security.can_read_own_conversation(p_tenant,u) THEN RETURN false;END IF;
 SELECT * INTO a FROM portal.agent_access WHERE tenant_id=p_tenant AND agent_key=p_agent;
 RETURN NOT FOUND OR a.mode='all' OR u=ANY(a.member_ids);
END;$body$;
CREATE FUNCTION security.agent_access_guard(p_tenant uuid,p_agent text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 PERFORM 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF NOT security.agent_access_allowed(p_tenant,p_agent) THEN RAISE EXCEPTION 'AGENT_ACCESS_DENIED' USING ERRCODE='B0340';END IF;
END;$body$;
CREATE FUNCTION security.catalog_read(p_session uuid,p_tenant uuid,p_action text,p_asset uuid,p_body jsonb,p_period date,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;key text;items jsonb;entry jsonb;ready jsonb;n integer;cursor_id uuid;q text;category text;mine boolean;
BEGIN
 IF p_action NOT IN ('list','detail','access_get','members') OR p_action IS NULL OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='members' THEN
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',false);key:=p_body->>'agent_key';
  IF p_body-ARRAY['agent_key','cursor','limit']::text[]<>'{}' OR key IS NULL OR key NOT IN ('general','rules_rag')
   OR jsonb_typeof(p_body->'limit') IS DISTINCT FROM 'number' OR p_body->>'limit' !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  n:=(p_body->>'limit')::integer;cursor_id:=(p_body->>'cursor')::uuid;
  IF n NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  IF cursor_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts a ON a.user_id=m.user_id WHERE m.tenant_id=p_tenant AND m.user_id=cursor_id AND m.active AND a.active) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.user_id),'[]'::jsonb) INTO items FROM (
   SELECT m.user_id,a.display_name,m.role,m.active,m.revision FROM security.memberships m JOIN security.accounts a ON a.user_id=m.user_id
   WHERE m.tenant_id=p_tenant AND m.active AND a.active AND (cursor_id IS NULL OR m.user_id>cursor_id) ORDER BY m.user_id LIMIT n+1) x;
  RETURN jsonb_build_object('items',CASE WHEN jsonb_array_length(items)>n THEN items-n ELSE items END,'next_cursor',CASE WHEN jsonb_array_length(items)>n THEN items->(n-1)->>'user_id' ELSE NULL END);
 END IF;
 IF p_action='access_get' THEN
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',false);key:=p_body->>'agent_key';
  IF p_body-ARRAY['agent_key']::text[]<>'{}' OR key IS NULL OR key NOT IN ('general','rules_rag') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT jsonb_build_object('agent_key',key,'mode',mode,'member_ids',member_ids,'revision',revision) INTO entry FROM portal.agent_access WHERE tenant_id=p_tenant AND agent_key=key;
  RETURN COALESCE(entry,jsonb_build_object('agent_key',key,'mode','all','member_ids','[]'::jsonb,'revision',0));
 END IF;
 u:=security.run_authorize(p_session,p_tenant,false);
 IF p_action='detail' AND (p_asset IS NULL OR p_body<>'{}') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='list' THEN
  IF p_body-ARRAY['q','category','mine','limit','cursor']::text[]<>'{}' OR jsonb_typeof(p_body->'q') IS DISTINCT FROM 'string'
   OR jsonb_typeof(p_body->'category') IS DISTINCT FROM 'string' OR jsonb_typeof(p_body->'mine') IS DISTINCT FROM 'boolean'
   OR jsonb_typeof(p_body->'limit') IS DISTINCT FROM 'number' OR p_body->>'limit' !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 END IF;
 q:=COALESCE(p_body->>'q','');category:=COALESCE(p_body->>'category','all');mine:=COALESCE((p_body->>'mine')::boolean,false);n:=COALESCE((p_body->>'limit')::integer,20);cursor_id:=(p_body->>'cursor')::uuid;
 IF char_length(q)>80 OR category NOT IN ('all','general','knowledge') OR n NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 ready:=security.operations_read(p_session,p_tenant,'agents',p_period,p_mode,NULL,NULL,20);
 SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.asset_id),'[]'::jsonb) INTO items FROM (
  SELECT md5(a.tenant_id::text||':portal-agent:'||a.agent_key)::uuid AS asset_id,a.agent_key,
   a.config_version AS revision,r.value->>'name' AS name,r.value->>'description' AS description,
   CASE WHEN a.agent_key='general' THEN 'general' ELSE 'knowledge' END AS category,
   (r.value->>'available')::boolean AS available,r.value->>'safe_block_reason' AS safe_block_reason,
   COALESCE(f.active,false) AS favorite,COALESCE(f.revision,0) AS favorite_revision
  FROM portal.agent_configs a JOIN jsonb_array_elements(ready->'items') r(value) ON r.value->>'agent_key'=a.agent_key
  LEFT JOIN portal.agent_favorites f ON f.tenant_id=a.tenant_id AND f.agent_key=a.agent_key AND f.user_id=u
  WHERE a.tenant_id=p_tenant AND security.agent_access_allowed(p_tenant,a.agent_key)
   AND (category='all' OR (category='general' AND a.agent_key='general') OR (category='knowledge' AND a.agent_key='rules_rag'))
   AND (NOT mine OR COALESCE(f.active,false)) AND position(lower(q) in lower(COALESCE(r.value->>'name','')||' '||COALESCE(r.value->>'description','')))>0
 ) x;
 IF p_action='detail' THEN
  SELECT value INTO entry FROM jsonb_array_elements(items) WHERE (value->>'asset_id')::uuid=p_asset;
  IF entry IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;RETURN entry;
 END IF;
 IF cursor_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(items) WHERE (value->>'asset_id')::uuid=cursor_id) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 SELECT COALESCE(jsonb_agg(value ORDER BY (value->>'asset_id')::uuid),'[]'::jsonb) INTO items FROM (
  SELECT value FROM jsonb_array_elements(items) WHERE cursor_id IS NULL OR (value->>'asset_id')::uuid>cursor_id ORDER BY (value->>'asset_id')::uuid LIMIT n+1) s;
 RETURN jsonb_build_object('items',CASE WHEN jsonb_array_length(items)>n THEN items-n ELSE items END,'next_cursor',CASE WHEN jsonb_array_length(items)>n THEN items->(n-1)->>'asset_id' ELSE NULL END);
END;$body$;
CREATE FUNCTION security.catalog_write(p_session uuid,p_tenant uuid,p_action text,p_asset uuid,p_agent text,p_body jsonb,p_trace uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;key text;target uuid;cid uuid;expected bigint;actual bigint;ids uuid[];mode_value text;active_value boolean;entry jsonb;previous portal.catalog_mutations%ROWTYPE;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('favorite','access_set') OR p_trace IS NULL OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='access_set' THEN u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);key:=p_agent;
 ELSE u:=security.run_authorize(p_session,p_tenant,true);
  SELECT agent_key INTO key FROM portal.agent_configs WHERE tenant_id=p_tenant AND md5(tenant_id::text||':portal-agent:'||agent_key)::uuid=p_asset;
 END IF;
 IF key IS NULL OR key NOT IN ('general','rules_rag') THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 target:=md5(p_tenant::text||':portal-agent:'||key)::uuid;
 IF NOT p_body ?& ARRAY['client_request_id','expected_revision'] OR jsonb_typeof(p_body->'client_request_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number' OR p_body->>'expected_revision' !~ '^(0|[1-9][0-9]*)$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 cid:=(p_body->>'client_request_id')::uuid;expected:=(p_body->>'expected_revision')::bigint;
 IF p_action='favorite' THEN
  IF p_body-ARRAY['client_request_id','expected_revision','active']::text[]<>'{}' OR jsonb_typeof(p_body->'active') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  active_value:=(p_body->>'active')::boolean;
 ELSE
  IF p_body-ARRAY['client_request_id','expected_revision','mode','member_ids']::text[]<>'{}' OR jsonb_typeof(p_body->'mode') IS DISTINCT FROM 'string' OR p_body->>'mode' NOT IN ('all','restricted')
   OR jsonb_typeof(p_body->'member_ids') IS DISTINCT FROM 'array' OR jsonb_array_length(p_body->'member_ids')>200
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_body->'member_ids') WHERE jsonb_typeof(value)<>'string') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT COALESCE(array_agg(value::uuid ORDER BY value::uuid),'{}'::uuid[]) INTO ids FROM jsonb_array_elements_text(p_body->'member_ids');mode_value:=p_body->>'mode';
  IF cardinality(ids)<>(SELECT count(DISTINCT id) FROM unnest(ids) id) OR (mode_value='all' AND cardinality(ids)>0) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':'||u::text||':catalog',0));
 IF p_action='access_set' THEN
  PERFORM security.operations_authorize(p_session,p_tenant,'agent_availability',true);
  PERFORM 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=key FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 ELSE
  PERFORM 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=key FOR SHARE;
  PERFORM security.run_authorize(p_session,p_tenant,true);
 END IF;
 SELECT * INTO previous FROM portal.catalog_mutations WHERE tenant_id=p_tenant AND user_id=u AND client_request_id=cid;
 IF FOUND THEN
  IF previous.action<>p_action OR previous.target_id<>target OR previous.body<>p_body THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  RETURN previous.response||jsonb_build_object('replayed',true);
 END IF;
 IF p_action='favorite' THEN
  IF active_value AND NOT security.agent_access_allowed(p_tenant,key) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  SELECT revision INTO actual FROM portal.agent_favorites WHERE tenant_id=p_tenant AND user_id=u AND agent_key=key;
  IF COALESCE(actual,0)<>expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  INSERT INTO portal.agent_favorites(tenant_id,user_id,agent_key,active,revision) VALUES(p_tenant,u,key,active_value,expected+1)
  ON CONFLICT(tenant_id,user_id,agent_key) DO UPDATE SET active=EXCLUDED.active,revision=EXCLUDED.revision,updated_at=clock_timestamp();
  entry:=jsonb_build_object('asset_id',target,'active',active_value,'revision',expected+1,'replayed',false);
 ELSE
  IF EXISTS(SELECT 1 FROM unnest(ids) i WHERE NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts usr ON usr.user_id=m.user_id WHERE m.tenant_id=p_tenant AND m.user_id=i AND m.active AND usr.active)) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT revision INTO actual FROM portal.agent_access WHERE tenant_id=p_tenant AND agent_key=key;
  IF COALESCE(actual,0)<>expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  INSERT INTO portal.agent_access(tenant_id,agent_key,mode,member_ids,revision) VALUES(p_tenant,key,mode_value,ids,expected+1)
  ON CONFLICT(tenant_id,agent_key) DO UPDATE SET mode=EXCLUDED.mode,member_ids=EXCLUDED.member_ids,revision=EXCLUDED.revision,updated_at=clock_timestamp();
  entry:=jsonb_build_object('agent_key',key,'mode',mode_value,'member_ids',ids,'revision',expected+1,'replayed',false);
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_trace,'tenant',p_tenant,u,CASE WHEN p_action='favorite' THEN 'catalog.favorite' ELSE 'catalog.access' END,target,'ok',jsonb_build_object('revision',expected+1));
 INSERT INTO portal.catalog_mutations(tenant_id,user_id,client_request_id,action,target_id,body,response) VALUES(p_tenant,u,cid,p_action,target,p_body,entry);
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401';END IF;
 RETURN entry;
END;$body$;
ALTER FUNCTION security.agent_access_allowed(uuid,text) OWNER TO ai_policy_executor;
ALTER FUNCTION security.agent_access_guard(uuid,text) OWNER TO ai_policy_executor;
ALTER FUNCTION security.catalog_read(uuid,uuid,text,uuid,jsonb,date,text) OWNER TO ai_policy_executor;
ALTER FUNCTION security.catalog_write(uuid,uuid,text,uuid,text,jsonb,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.agent_access_allowed(uuid,text),security.agent_access_guard(uuid,text),security.catalog_read(uuid,uuid,text,uuid,jsonb,date,text),security.catalog_write(uuid,uuid,text,uuid,text,jsonb,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.catalog_read(uuid,uuid,text,uuid,jsonb,date,text),security.catalog_write(uuid,uuid,text,uuid,text,jsonb,uuid) TO ai_web;

CREATE OR REPLACE FUNCTION security.operations_read(p_session uuid,p_tenant uuid,p_kind text,p_period date,p_mode text,
 p_agent text,p_cursor uuid,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
 v_agent portal.agent_configs%ROWTYPE;v_items jsonb;v_next text;v_block text;v_calls bigint;v_unknown bigint;
 v_reserved numeric;v_accounted numeric;v_input numeric;v_output numeric;v_total numeric;v_known bigint;v_allocated numeric;
BEGIN
 IF p_kind NOT IN ('agents','agent_admin','usage_me','usage_admin','budget_admin','platform_summary') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 v_user:=security.operations_authorize(p_session,p_tenant,p_kind,false);
 IF p_period IS NULL OR extract(day FROM p_period)<>1 OR p_mode IS NULL OR p_mode NOT IN ('mock','real')
 OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_kind='agent_admin' THEN
  SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  RETURN jsonb_build_object('agent_key',v_agent.agent_key,'name',COALESCE(v_agent.settings->>'name',CASE WHEN p_agent='general' THEN '일반 대화' ELSE '규정 검색' END),
   'description',COALESCE(v_agent.settings->>'description',''),'instructions',COALESCE(v_agent.settings->>'instructions','질문에 답해 주세요.'),
   'enabled',v_agent.enabled,'config_version',v_agent.config_version);
 END IF;
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode;
 IF NOT FOUND AND p_kind<>'agents' THEN RAISE EXCEPTION 'BUDGET_STATE_UNAVAILABLE' USING ERRCODE='P0002'; END IF;
 IF p_tenant IS NOT NULL THEN
  SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
  IF NOT FOUND AND p_kind<>'agents' THEN RAISE EXCEPTION 'BUDGET_STATE_UNAVAILABLE' USING ERRCODE='P0002'; END IF;
 END IF;
 v_block:=CASE WHEN v_project.budget_id IS NULL OR (p_tenant IS NOT NULL AND v_tenant.budget_id IS NULL) THEN 'BUDGET_NOT_READY'
  WHEN v_project.stopped OR v_project.stop_latch THEN 'PROJECT_STOPPED'
  WHEN p_tenant IS NOT NULL AND v_tenant.stopped THEN 'TENANT_STOPPED'
  WHEN v_project.accounted_krw+v_project.reserved_krw>=v_project.operational_cap_krw
   OR (p_tenant IS NOT NULL AND v_tenant.accounted_krw+v_tenant.reserved_krw>=LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw)) THEN 'QUOTA_EXCEEDED'
  ELSE NULL END;
 IF p_kind='agents' THEN
  SELECT COALESCE(jsonb_agg(jsonb_build_object('agent_key',a.agent_key,
   'name',COALESCE(a.settings->>'name',CASE WHEN a.agent_key='general' THEN '일반 대화' ELSE '규정 검색' END),
   'description',COALESCE(a.settings->>'description',''),'config_version',a.config_version,'available',false,
   'safe_block_reason',CASE WHEN NOT a.enabled THEN 'AGENT_DISABLED' WHEN v_block IS NOT NULL THEN v_block ELSE 'FEATURE_NOT_READY' END) ORDER BY a.agent_key),'[]'::jsonb)
   INTO v_items FROM portal.agent_configs a WHERE a.tenant_id=p_tenant AND security.agent_access_allowed(p_tenant,a.agent_key);
  -- Both pipelines are unconnected at B02; B04 enables only verified general runtime readiness.
  RETURN jsonb_build_object('items',v_items);
 END IF;
 IF p_kind='budget_admin' THEN
  RETURN jsonb_build_object('period',p_period,'execution_mode',p_mode,
   'allocated_cap_krw',v_tenant.allocated_cap_krw::text,'local_cap_krw',v_tenant.local_cap_krw::text,
   'estimated_accounted_krw',v_tenant.accounted_krw::text,'reserved_krw',v_tenant.reserved_krw::text,
   'blocked',v_block IS NOT NULL,'safe_block_reason',v_block,'revision',v_tenant.revision);
 END IF;
 IF p_kind='platform_summary' THEN
  SELECT count(*) INTO v_unknown FROM ops.call_attempts WHERE budget_id=v_project.budget_id AND state='usage_unknown';
  SELECT COALESCE(sum(allocated_cap_krw),0) INTO v_allocated FROM ops.tenant_budgets WHERE budget_id=v_project.budget_id;
  RETURN jsonb_build_object('period',p_period,'execution_mode',p_mode,'approved_cap_krw',v_project.approved_cap_krw::text,
   'operational_cap_krw',v_project.operational_cap_krw::text,'allocated_total_krw',v_allocated::text,
   'estimated_accounted_krw',v_project.accounted_krw::text,'reserved_krw',v_project.reserved_krw::text,
   'unknown_count',v_unknown,'enabled',NOT(v_project.stopped OR v_project.stop_latch),'stop_latch',v_project.stop_latch,'revision',v_project.revision);
 END IF;
 SELECT count(*),count(*) FILTER(WHERE c.state='usage_unknown'),
  COALESCE(sum(c.reserved_krw) FILTER(WHERE c.state IN ('reserved','dispatched','usage_unknown')),0)
 INTO v_calls,v_unknown,v_reserved FROM ops.call_attempts c WHERE c.tenant_id=p_tenant AND c.budget_id=v_project.budget_id
 AND (p_kind='usage_admin' OR c.initiator_user_id=v_user);
 SELECT COALESCE(sum(e.delta_accounted_krw),0),COALESCE(sum((e.token_counts->>'input_tokens')::numeric),0),
  COALESCE(sum((e.token_counts->>'output_tokens')::numeric),0),COALESCE(sum((e.token_counts->>'total_tokens')::numeric),0),
  count(*) FILTER(WHERE e.token_counts IS NOT NULL)
 INTO v_accounted,v_input,v_output,v_total,v_known FROM ops.usage_events e JOIN ops.call_attempts c USING(tenant_id,call_id)
 WHERE e.tenant_id=p_tenant AND c.budget_id=v_project.budget_id AND e.event_kind='settle'
 AND (p_kind='usage_admin' OR c.initiator_user_id=v_user);
 IF p_kind='usage_me' THEN
  SELECT COALESCE(jsonb_agg(x ORDER BY x.operation),'[]'::jsonb) INTO v_items FROM
   (SELECT c.operation,count(*) AS call_count,count(*) FILTER(WHERE c.state='usage_unknown') AS unknown_count
    FROM ops.call_attempts c WHERE c.tenant_id=p_tenant AND c.budget_id=v_project.budget_id AND c.initiator_user_id=v_user GROUP BY c.operation) x;
 ELSE
  SELECT COALESCE(jsonb_agg(x ORDER BY x.call_id),'[]'::jsonb) INTO v_items FROM
   (SELECT c.call_id,c.operation,c.mode AS execution_mode,c.state,c.created_at,
    CASE c.state WHEN 'settled' THEN 'accounted' WHEN 'usage_unknown' THEN 'unknown' WHEN 'dispatched' THEN 'pending' ELSE c.state END AS usage_status,
    CASE WHEN c.state IN ('reserved','dispatched','usage_unknown') THEN c.reserved_krw::text ELSE '0' END AS reserved_krw
    FROM ops.call_attempts c WHERE c.tenant_id=p_tenant AND c.budget_id=v_project.budget_id AND (p_cursor IS NULL OR c.call_id>p_cursor)
    ORDER BY c.call_id LIMIT p_limit+1) x;
  IF jsonb_array_length(v_items)>p_limit THEN
   v_next:=v_items->(p_limit-1)->>'call_id';v_items:=v_items-p_limit;
  END IF;
 END IF;
 RETURN jsonb_build_object('period',p_period,'execution_mode',p_mode,'call_count',v_calls,
  'unknown_count',v_unknown,'estimated_accounted_krw',v_accounted::text,'reserved_krw',v_reserved::text,
  'known_tokens',CASE WHEN v_known=0 AND v_calls>0 THEN NULL ELSE jsonb_build_object('input_tokens',v_input,'output_tokens',v_output,'total_tokens',v_total) END,
  'blocked',v_block IS NOT NULL,'safe_block_reason',v_block,'items',v_items,'next_cursor',v_next);
END; $body$;

CREATE OR REPLACE FUNCTION security.run_prepare(p_session uuid,p_tenant uuid,p_agent text,p_conversation uuid,p_send uuid,p_hash bytea,p_period date,p_mode text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_existing portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
 v_conversation portal.conversations%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_budget ops.tenant_budgets%ROWTYPE;v_history jsonb;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_send IS NULL OR p_hash IS NULL OR octet_length(p_hash)<>32 OR p_agent IS NULL OR p_agent NOT IN ('general','rules_rag')
 OR p_period IS NULL OR extract(day FROM p_period)<>1 OR p_mode IS NULL OR p_mode NOT IN ('mock','real') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.agent_access_guard(p_tenant,p_agent);
 IF EXISTS(SELECT 1 FROM portal.runs WHERE tenant_id=p_tenant AND ((conversation_id=p_conversation) OR client_send_id=p_send) AND task_kind<>'chat') THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301';END IF;
 IF p_conversation IS NOT NULL THEN
  SELECT * INTO v_conversation FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_conversation AND deleted_at IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  IF v_conversation.agent_key<>p_agent THEN RAISE EXCEPTION 'CONVERSATION_AGENT_MISMATCH' USING ERRCODE='B0302'; END IF;
 END IF;
 SELECT * INTO v_existing FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=p_send;
 IF FOUND THEN
  IF v_existing.request_hash<>p_hash THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301'; END IF;
  RETURN jsonb_build_object('replay',security.run_view(p_tenant,v_existing.run_id)||jsonb_build_object('replayed',true));
 END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent FOR SHARE;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF v_agent.agent_key IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF NOT v_agent.enabled THEN RAISE EXCEPTION 'AGENT_STOPPED' USING ERRCODE='B0303'; END IF;

 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'BUDGET_STATE_UNAVAILABLE' USING ERRCODE='P0002'; END IF;
 -- Recheck duplicate after the shared project gate wait, including different valid sessions.
 SELECT * INTO v_existing FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=p_send;
 IF FOUND THEN
  IF v_existing.request_hash<>p_hash THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301'; END IF;
  RETURN jsonb_build_object('replay',security.run_view(p_tenant,v_existing.run_id)||jsonb_build_object('replayed',true));
 END IF;
 SELECT * INTO v_budget FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'BUDGET_STATE_UNAVAILABLE' USING ERRCODE='P0002'; END IF;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF v_project.stop_latch THEN RAISE EXCEPTION 'REVIEW_REQUIRED' USING ERRCODE='B0210'; END IF;
 IF v_project.stopped OR v_budget.stopped THEN RAISE EXCEPTION 'PLATFORM_STOPPED' USING ERRCODE='B0305'; END IF;
 -- Cheap preflight only. B04 must reserve 3.64 atomically again immediately before dispatch.
 IF v_project.reserved_krw+v_project.accounted_krw+(CASE WHEN p_agent='rules_rag' THEN 3.84 ELSE 3.64 END)>v_project.operational_cap_krw
 OR v_budget.reserved_krw+v_budget.accounted_krw+(CASE WHEN p_agent='rules_rag' THEN 3.84 ELSE 3.64 END)>v_budget.local_cap_krw THEN
  RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0306'; END IF;
 IF p_conversation IS NOT NULL THEN
  PERFORM conversation_id FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_conversation AND deleted_at IS NULL FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('message_id',q.message_id,'role',q.role,'content',q.body) ORDER BY q.sequence_no),'[]'::jsonb)
 INTO v_history FROM (SELECT m.message_id,m.role,m.body,m.sequence_no FROM portal.messages m
 WHERE m.tenant_id=p_tenant AND m.conversation_id=p_conversation ORDER BY m.sequence_no DESC LIMIT 6) q;
 RETURN jsonb_build_object('instructions',COALESCE(NULLIF(v_agent.settings->>'instructions',''),'사용자 질문에 간결하고 정확하게 답변하세요.'),
  'config_version',v_agent.config_version,'history',v_history);
END; $body$;

CREATE OR REPLACE FUNCTION security.run_asset_resolve(p_session uuid,p_tenant uuid,p_agent text,p_asset uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE expected uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_agent IS NULL OR p_agent NOT IN ('general','rules_rag') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 PERFORM security.agent_access_guard(p_tenant,p_agent);
 expected:=md5(p_tenant::text||':portal-agent:'||p_agent)::uuid;
 -- Only existing fixed aliases are executable. Draft/random/cross-tenant all return the same error.
 IF p_asset IS NOT NULL AND p_asset<>expected THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 RETURN expected;
END;$body$;

CREATE OR REPLACE FUNCTION security.conversation_create(p_session uuid,p_tenant uuid,p_agent text,p_client uuid,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_row portal.conversations%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_agent IS NULL OR p_agent NOT IN ('general','rules_rag') OR p_request IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.agent_access_guard(p_tenant,p_agent);
 IF p_client IS NOT NULL THEN
  SELECT * INTO v_row FROM portal.conversations WHERE tenant_id=p_tenant AND client_conversation_id=p_client FOR UPDATE;
  IF FOUND THEN
   IF v_row.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'CONVERSATION_DELETED' USING ERRCODE='B0313'; END IF;
   IF v_row.agent_key<>p_agent THEN RAISE EXCEPTION 'CONVERSATION_AGENT_MISMATCH' USING ERRCODE='B0302'; END IF;
   RETURN jsonb_build_object('conversation_id',v_row.conversation_id,'tenant_id',p_tenant,'agent_key',v_row.agent_key,'created_at',v_row.created_at,'replayed',true);
  END IF;
 END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent FOR SHARE;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF NOT FOUND OR v_agent.agent_key IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF NOT v_agent.enabled THEN RAISE EXCEPTION 'AGENT_STOPPED' USING ERRCODE='B0303'; END IF;

 INSERT INTO portal.conversations(tenant_id,conversation_id,owner_user_id,agent_key,client_conversation_id)
 VALUES(p_tenant,gen_random_uuid(),v_user,p_agent,p_client)
 ON CONFLICT(tenant_id,owner_user_id,client_conversation_id) DO NOTHING RETURNING * INTO v_row;
 IF NOT FOUND THEN
  SELECT * INTO v_row FROM portal.conversations WHERE tenant_id=p_tenant AND client_conversation_id=p_client;
  IF v_row.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'CONVERSATION_DELETED' USING ERRCODE='B0313'; END IF;
   IF v_row.agent_key<>p_agent THEN RAISE EXCEPTION 'CONVERSATION_AGENT_MISMATCH' USING ERRCODE='B0302'; END IF;
  RETURN jsonb_build_object('conversation_id',v_row.conversation_id,'tenant_id',p_tenant,'agent_key',v_row.agent_key,'created_at',v_row.created_at,'replayed',true);
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,'conversation_created',v_row.conversation_id,'ok',jsonb_build_object('agent_key',p_agent));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN jsonb_build_object('conversation_id',v_row.conversation_id,'tenant_id',p_tenant,'agent_key',v_row.agent_key,'created_at',v_row.created_at,'replayed',false);
END; $body$;

CREATE OR REPLACE FUNCTION security.execution_claim(p_session uuid,p_tenant uuid,p_run uuid,p_mode text,p_period date,p_worker bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_run portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
 v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;v_messages jsonb;v_prompt text;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_worker IS NULL OR octet_length(p_worker)<>32 OR p_mode NOT IN ('mock','real') OR p_mode IS NULL
 OR p_period IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=(SELECT agent_key FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run) FOR SHARE;
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF v_run.run_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF v_run.state<>'accepted' THEN RETURN NULL; END IF;
 IF v_run.origin_session_id<>p_session OR v_run.execution_mode<>p_mode THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 PERFORM security.agent_access_guard(p_tenant,v_run.agent_key);
 IF NOT COALESCE(v_agent.enabled,false) THEN RAISE EXCEPTION 'AGENT_DISABLED' USING ERRCODE='B0402'; END IF;
 IF v_agent.config_version IS DISTINCT FROM (v_run.config_snapshot->>'config_version')::bigint
 THEN RAISE EXCEPTION 'CONFIG_CHANGED' USING ERRCODE='B0403'; END IF;
 IF v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (p_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09'))
 THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF v_run.task_kind='document_summary' THEN RAISE EXCEPTION 'SUMMARY_CAPABILITY_REQUIRED' USING ERRCODE='A0422';END IF;
 SELECT body INTO v_prompt FROM portal.messages WHERE tenant_id=p_tenant AND run_id=p_run AND role='user' AND NOT payload_purged;
 IF v_prompt IS NULL THEN RAISE EXCEPTION 'INPUT_UNAVAILABLE' USING ERRCODE='B0406'; END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('role',m.role,'content',m.body) ORDER BY m.sequence_no),'[]'::jsonb)
 INTO v_messages FROM portal.messages m WHERE m.tenant_id=p_tenant AND m.conversation_id=v_run.conversation_id
 AND m.message_id IN (SELECT value::uuid FROM jsonb_array_elements_text(v_run.config_snapshot->'selected_history_ids'));
 UPDATE portal.runs SET state='running',stage=CASE WHEN v_run.agent_key='rules_rag' THEN 'retrieval' ELSE 'generation' END,worker_claim_hash=p_worker,execution_budget_id=v_project.budget_id,revision=revision+1,
 started_at=clock_timestamp(),heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+interval '60 seconds'
 WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN jsonb_build_object('tenant_id',p_tenant,'run_id',p_run,'owner_user_id',v_user,'origin_session_id',p_session,
 'epoch',v_run.execution_epoch,'config_revision',v_agent.config_version,'mode',p_mode,'agent_key',v_run.agent_key,'document_refs',v_run.config_snapshot->'document_refs',
 'messages',jsonb_build_array(jsonb_build_object('role','system','content',v_run.config_snapshot->>'instructions'))
 ||v_messages||jsonb_build_array(jsonb_build_object('role','user','content',v_prompt)));
END; $body$;

CREATE OR REPLACE FUNCTION security.summary_claim(p_session uuid,p_tenant uuid,p_run uuid,p_mode text,p_period date,p_worker bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_run portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
 v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;v_messages jsonb;v_prompt text;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_worker IS NULL OR octet_length(p_worker)<>32 OR p_mode NOT IN ('mock','real') OR p_mode IS NULL
 OR p_period IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=(SELECT agent_key FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run) FOR SHARE;
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF v_run.run_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF v_run.state<>'accepted' THEN RETURN NULL; END IF;
 IF v_run.origin_session_id<>p_session OR v_run.execution_mode<>p_mode THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 PERFORM security.agent_access_guard(p_tenant,v_run.agent_key);
 IF NOT COALESCE(v_agent.enabled,false) THEN RAISE EXCEPTION 'AGENT_DISABLED' USING ERRCODE='B0402'; END IF;
 IF v_agent.config_version IS DISTINCT FROM (v_run.config_snapshot->>'config_version')::bigint
 THEN RAISE EXCEPTION 'CONFIG_CHANGED' USING ERRCODE='B0403'; END IF;
 IF v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (p_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09'))
 THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF v_run.task_kind<>'document_summary' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 PERFORM security.summary_source_guard(p_session,p_tenant,p_run);
 SELECT body INTO v_prompt FROM portal.messages WHERE tenant_id=p_tenant AND run_id=p_run AND role='user' AND NOT payload_purged;
 IF v_prompt IS NULL THEN RAISE EXCEPTION 'INPUT_UNAVAILABLE' USING ERRCODE='B0406'; END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('role',m.role,'content',m.body) ORDER BY m.sequence_no),'[]'::jsonb)
 INTO v_messages FROM portal.messages m WHERE m.tenant_id=p_tenant AND m.conversation_id=v_run.conversation_id
 AND m.message_id IN (SELECT value::uuid FROM jsonb_array_elements_text(v_run.config_snapshot->'selected_history_ids'));
 UPDATE portal.runs SET state='running',stage=CASE WHEN v_run.agent_key='rules_rag' THEN 'retrieval' ELSE 'generation' END,worker_claim_hash=p_worker,execution_budget_id=v_project.budget_id,revision=revision+1,
 started_at=clock_timestamp(),heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+interval '60 seconds'
 WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN jsonb_build_object('tenant_id',p_tenant,'run_id',p_run,'owner_user_id',v_user,'origin_session_id',p_session,
 'epoch',v_run.execution_epoch,'config_revision',v_agent.config_version,'mode',p_mode,'task_kind',v_run.task_kind,'agent_key',v_run.agent_key,'document_refs',v_run.config_snapshot->'document_refs',
 'messages',jsonb_build_array(jsonb_build_object('role','system','content',v_run.config_snapshot->>'instructions'))
 ||v_messages||jsonb_build_array(jsonb_build_object('role','user','content',v_prompt)));
END; $body$;

CREATE OR REPLACE FUNCTION security.execution_guard(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_config boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=(SELECT agent_key FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run) FOR SHARE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF v_run.run_id IS NULL OR v_run.origin_session_id IS DISTINCT FROM p_session
 OR v_run.execution_epoch IS DISTINCT FROM p_epoch OR v_run.worker_claim_hash IS DISTINCT FROM p_worker
 OR p_worker IS NULL OR octet_length(p_worker)<>32 OR v_run.state<>'running'
 OR v_run.lease_expires_at<=clock_timestamp() OR v_run.started_at+interval '180 seconds'<=clock_timestamp()
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 PERFORM security.agent_access_guard(p_tenant,v_run.agent_key);
 IF NOT COALESCE(v_agent.enabled,false) THEN RAISE EXCEPTION 'AGENT_DISABLED' USING ERRCODE='B0402'; END IF;
 IF p_config AND v_agent.config_version IS DISTINCT FROM (v_run.config_snapshot->>'config_version')::bigint
 THEN RAISE EXCEPTION 'CONFIG_CHANGED' USING ERRCODE='B0403'; END IF;
 IF v_run.task_kind='document_summary' THEN PERFORM security.summary_source_guard(p_session,p_tenant,p_run);END IF;
 PERFORM security.execution_scope(p_tenant);
END; $body$;

CREATE OR REPLACE FUNCTION security.execution_stream_view(p_session uuid,p_tenant uuid,p_run uuid,p_mode text,p_period date)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_view jsonb;v_agent portal.agent_configs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 v_view:=security.run_view(p_tenant,p_run);
 PERFORM security.agent_access_guard(p_tenant,v_view->>'agent_key');
 IF v_view->>'execution_mode'<>p_mode THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=v_view->>'agent_key';
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 IF NOT (v_view->>'is_terminal')::boolean AND (NOT EXISTS(SELECT 1 FROM portal.runs r WHERE r.tenant_id=p_tenant AND r.run_id=p_run
 AND EXISTS(SELECT 1 FROM security.current_membership(r.origin_session_id,p_tenant))) OR NOT COALESCE(v_agent.enabled,false) OR v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL
 OR v_project.stopped OR v_project.stop_latch OR v_tenant.stopped) THEN RAISE EXCEPTION 'EXECUTION_BLOCKED' USING ERRCODE='B0405'; END IF;
 RETURN v_view||jsonb_build_object('execution_epoch',(SELECT execution_epoch FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run));
END; $body$;

CREATE OR REPLACE FUNCTION security.summary_replay(p_session uuid,p_tenant uuid,p_send uuid,p_hash bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 PERFORM security.agent_access_guard(p_tenant,'rules_rag');
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=p_send;
 IF NOT FOUND THEN RETURN NULL;END IF;
 IF r.task_kind<>'document_summary' OR r.request_hash IS DISTINCT FROM p_hash THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301';END IF;
 PERFORM security.summary_source_guard(p_session,p_tenant,r.run_id);
 RETURN security.run_view(p_tenant,r.run_id)||jsonb_build_object('replayed',true);
END;$body$;

CREATE OR REPLACE FUNCTION security.summary_admit(p_session uuid,p_tenant uuid,p_send uuid,p_hash bytea,p_period date,p_mode text,
 p_digest bytea,p_request uuid,p_source uuid,p_document uuid,p_source_version uuid,p_index uuid,p_sha bytea,p_bullets integer,p_tokens integer,p_candidates jsonb,p_parent uuid,p_expected bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_ready jsonb;v_run uuid;v_conversation uuid;v_sequence bigint;v_snapshot jsonb;
 v_count_user integer;v_count_tenant integer;v_count_project integer;v_start timestamptz;v_count integer;v_now timestamptz;p_agent text:='rules_rag';p_conversation uuid:=NULL;p_prompt text:='문서 요약';p_version bigint;p_selected uuid[]:='{}';v_parent portal.runs%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 PERFORM security.agent_access_guard(p_tenant,'rules_rag');
 PERFORM security.rag_sources_guard(p_session,p_tenant,p_mode,jsonb_build_array(jsonb_build_object('source_tenant_id',p_source,'document_id',p_document,'version_id',p_source_version,'index_id',p_index)));
 IF p_bullets IS NULL OR p_bullets NOT IN (3,5) OR p_candidates IS NULL OR jsonb_typeof(p_candidates)<>'array' OR jsonb_array_length(p_candidates)>128 OR p_sha IS NULL OR octet_length(p_sha)<>32 OR NOT EXISTS(SELECT 1 FROM rag.document_versions WHERE (tenant_id,document_id,version_id,source_sha256)=(p_source,p_document,p_source_version,p_sha) AND NOT payload_purged) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO v_parent FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=p_send;
 IF FOUND THEN
  IF v_parent.request_hash<>p_hash OR v_parent.task_kind<>'document_summary' THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301';END IF;
  PERFORM security.summary_source_guard(p_session,p_tenant,v_parent.run_id);
  RETURN security.run_view(p_tenant,v_parent.run_id)||jsonb_build_object('replayed',true);
 END IF;
 IF p_parent IS NOT NULL THEN
  SELECT * INTO v_parent FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_parent FOR UPDATE;
  IF NOT FOUND OR v_parent.task_kind<>'document_summary' OR v_parent.owner_user_id IS DISTINCT FROM nullif(current_setting('app.user_id',true),'')::uuid THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  PERFORM security.summary_source_guard(p_session,p_tenant,p_parent);
  IF v_parent.state<>'completed' OR v_parent.revision IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='B0311';END IF;
  IF NOT EXISTS(SELECT 1 FROM portal.summary_requests WHERE tenant_id=p_tenant AND run_id=p_parent AND (source_tenant_id,document_id,version_id,index_id,source_sha256,bullet_count)=(p_source,p_document,p_source_version,p_index,p_sha,p_bullets)) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 END IF;
 v_ready:=security.run_prepare(p_session,p_tenant,p_agent,p_conversation,gen_random_uuid(),p_hash,p_period,p_mode);
 -- Project gate is locked by prepare; recheck summary identity after concurrent admission.
 SELECT * INTO v_parent FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=p_send;
 IF FOUND THEN
  IF v_parent.request_hash<>p_hash OR v_parent.task_kind<>'document_summary' THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301';END IF;
  PERFORM security.summary_source_guard(p_session,p_tenant,v_parent.run_id);
  RETURN security.run_view(p_tenant,v_parent.run_id)||jsonb_build_object('replayed',true);
 END IF;
 IF v_ready ? 'replay' THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301';END IF;
 p_version:=(v_ready->>'config_version')::bigint;
 v_user:=NULLIF(current_setting('app.user_id',true),'')::uuid;
 IF p_prompt IS NULL OR btrim(p_prompt)='' OR char_length(p_prompt)>4000 OR octet_length(p_prompt)>16384
 OR p_tokens IS NULL OR p_tokens NOT BETWEEN 1 AND 6000 OR p_version IS NULL OR p_version<>(v_ready->>'config_version')::bigint
 OR p_selected IS NULL OR cardinality(p_selected)>6 OR p_digest IS NULL OR octet_length(p_digest)<>32 OR p_request IS NULL THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF EXISTS(SELECT 1 FROM unnest(p_selected) x WHERE x IS NULL OR NOT EXISTS(
  SELECT 1 FROM jsonb_array_elements(v_ready->'history') h WHERE (h->>'message_id')::uuid=x))
 OR (SELECT count(DISTINCT x) FROM unnest(p_selected) x)<>cardinality(p_selected) THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM set_config('app.run_scope','capacity',true);
 SELECT count(*) FILTER(WHERE owner_user_id=v_user),count(*) FILTER(WHERE tenant_id=p_tenant),count(*)
 INTO v_count_user,v_count_tenant,v_count_project FROM portal.runs
 WHERE state IN ('accepted','running','cancel_requested') AND execution_mode=p_mode;
 PERFORM set_config('app.run_scope','owner',true);
 IF v_count_user>=1 OR v_count_tenant>=2 OR v_count_project>=4 THEN
  RETURN jsonb_build_object('admission_error','EXECUTION_CAPACITY_EXCEEDED','retry_after',2); END IF;
 INSERT INTO security.login_windows VALUES('run_admission','principal',p_digest,clock_timestamp(),0) ON CONFLICT DO NOTHING;
 SELECT window_started_at,count INTO v_start,v_count FROM security.login_windows
 WHERE purpose='run_admission' AND key_kind='principal' AND key_digest=p_digest FOR UPDATE;
 v_now:=clock_timestamp();
 IF v_now>=v_start+interval '1 minute' THEN
  v_start:=v_now;v_count:=0;
  UPDATE security.login_windows SET window_started_at=v_start,count=0 WHERE purpose='run_admission' AND key_kind='principal' AND key_digest=p_digest;
 END IF;
 IF v_count>=10 THEN RETURN jsonb_build_object('admission_error','RATE_LIMITED','retry_after',GREATEST(1,ceil(extract(epoch FROM v_start+interval '1 minute'-v_now))::integer)); END IF;
 UPDATE security.login_windows SET count=count+1 WHERE purpose='run_admission' AND key_kind='principal' AND key_digest=p_digest;
 v_conversation:=p_conversation;
 IF v_conversation IS NULL THEN
  v_conversation:=gen_random_uuid();
  INSERT INTO portal.conversations(tenant_id,conversation_id,owner_user_id,agent_key) VALUES(p_tenant,v_conversation,v_user,p_agent);
 END IF;
 PERFORM set_config('app.run_scope','sequence',true);
 SELECT COALESCE(max(sequence_no),0)+1 INTO v_sequence FROM portal.messages WHERE tenant_id=p_tenant AND conversation_id=v_conversation;
 PERFORM set_config('app.run_scope','owner',true);
 v_run:=gen_random_uuid();
 SELECT settings||jsonb_build_object('config_version',config_version,'agent_key',agent_key,'generation_model','gpt-4o-mini',
  'instructions',v_ready->>'instructions','selected_history_ids',to_jsonb(p_selected),'estimated_input_tokens',p_tokens,'document_refs',CASE WHEN p_agent='rules_rag' THEN coalesce(nullif(current_setting('app.rag_refs',true),'')::jsonb,'[]'::jsonb) ELSE '[]'::jsonb END) INTO v_snapshot
 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent;
 INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,request_hash,agent_key,config_snapshot,origin_session_id,execution_mode,task_kind)
 VALUES(p_tenant,v_run,v_conversation,v_user,p_send,p_hash,p_agent,v_snapshot,p_session,p_mode,'document_summary');
 INSERT INTO portal.summary_requests(tenant_id,run_id,owner_user_id,source_tenant_id,document_id,version_id,index_id,source_sha256,bullet_count,request_hash,parent_run_id,policy_revision,parser_revision,candidates)
 VALUES(p_tenant,v_run,v_user,p_source,p_document,p_source_version,p_index,p_sha,p_bullets,p_hash,p_parent,'summary-v1','source-map-v1',p_candidates);
 INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind)
 VALUES(p_tenant,gen_random_uuid(),v_conversation,v_user,p_agent,v_sequence,'user',p_prompt,v_run,'user');
 UPDATE portal.conversations SET updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND conversation_id=v_conversation;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,'run_admitted',v_run,'ok',jsonb_build_object('revision',1,'execution_mode',p_mode,'config_version',p_version));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN security.run_view(p_tenant,v_run)||jsonb_build_object('replayed',false);
END; $body$;
