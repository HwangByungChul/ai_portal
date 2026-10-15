-- B02 fixed operations. Preserve 000~005 and existing ledger/content rows.
CREATE FUNCTION security.operations_authorize(p_session uuid,p_tenant uuid,p_scope text,p_lock boolean)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_manage boolean;v_role text;v_global boolean;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_scope IS NULL OR p_scope NOT IN ('agents','agent_admin','agent_settings','agent_availability',
 'usage_me','usage_admin','budget_admin','local_budget','allocated_budget','platform_summary','global_availability')
 OR p_lock IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT s.user_id INTO v_user FROM security.sessions s WHERE s.session_id=p_session;
 IF NOT FOUND THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 BEGIN
  IF NULLIF(current_setting('app.session_id',true),'')::uuid IS DISTINCT FROM p_session
  OR NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM v_user
  OR NULLIF(current_setting('app.tenant_id',true),'')::uuid IS DISTINCT FROM p_tenant THEN
   RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403';
  END IF;
 EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END;
 IF p_lock THEN
  -- Same identity lock order as A04; UPDATE session lock avoids touch upgrade deadlocks.
  PERFORM a.user_id FROM security.accounts a WHERE a.user_id=v_user FOR SHARE;
  PERFORM t.tenant_id FROM security.tenants t WHERE t.tenant_id=p_tenant FOR SHARE;
  PERFORM p.user_id FROM security.platform_access p WHERE p.user_id=v_user FOR SHARE;
  PERFORM s.session_id FROM security.sessions s WHERE s.session_id=p_session FOR UPDATE;
  PERFORM m.user_id FROM security.memberships m WHERE m.tenant_id=p_tenant AND m.user_id=v_user FOR SHARE;
  PERFORM mt.user_id FROM security.managed_tenants mt WHERE mt.tenant_id=p_tenant AND mt.user_id=v_user FOR SHARE;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id
  WHERE s.session_id=p_session AND a.user_id=v_user AND a.active AND s.auth_revision=a.auth_revision
  AND s.revoked_at IS NULL AND clock_timestamp()<s.expires_at
  AND clock_timestamp()<s.last_activity_at+interval '30 minutes') THEN
  RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 IF p_scope IN ('platform_summary','global_availability') THEN
  IF p_tenant IS NOT NULL THEN RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
  SELECT COALESCE(p.active AND p.is_padmin AND
   CASE WHEN p_scope='platform_summary' THEN 'global_usage_read' ELSE 'global_stop_write' END=ANY(p.permissions),false)
   INTO v_global FROM security.platform_access p WHERE p.user_id=v_user;
  IF NOT COALESCE(v_global,false) THEN RAISE EXCEPTION 'CAPABILITY_DENIED' USING ERRCODE='A0403'; END IF;
 ELSE
  IF p_tenant IS NULL THEN RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
  SELECT m.can_manage,m.effective_role INTO v_manage,v_role FROM security.current_membership(p_session,p_tenant) m;
  IF NOT FOUND THEN RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
  IF p_scope NOT IN ('agents','usage_me') AND NOT v_manage THEN
   RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403'; END IF;
  IF p_scope='allocated_budget' AND v_role<>'PADMIN' THEN
   RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403'; END IF;
 END IF;
 PERFORM set_config('app.operations_scope',p_scope,true);
 RETURN v_user;
END; $body$;

CREATE FUNCTION security.operations_row_allowed(row_tenant uuid,row_owner uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_scope text;v_user uuid;v_session uuid;v_tenant uuid;
BEGIN
 IF session_user<>'ai_web' THEN RETURN false; END IF;
 BEGIN
  v_scope:=NULLIF(current_setting('app.operations_scope',true),'');
  v_user:=NULLIF(current_setting('app.user_id',true),'')::uuid;
  v_session:=NULLIF(current_setting('app.session_id',true),'')::uuid;
  v_tenant:=NULLIF(current_setting('app.tenant_id',true),'')::uuid;
 EXCEPTION WHEN invalid_text_representation THEN RETURN false; END;
 IF v_user IS NULL OR v_session IS NULL THEN RETURN false; END IF;
 IF v_scope='platform_summary' THEN
  RETURN v_tenant IS NULL AND EXISTS(SELECT 1 FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id
   JOIN security.platform_access p ON p.user_id=a.user_id WHERE s.session_id=v_session AND a.user_id=v_user
   AND a.active AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL AND clock_timestamp()<s.expires_at
   AND clock_timestamp()<s.last_activity_at+interval '30 minutes' AND p.active AND p.is_padmin
   AND 'global_usage_read'=ANY(p.permissions));
 END IF;
 IF v_scope='allocated_budget' THEN
  -- Cross-tenant non-content budget SELECT is only used for the allocation sum under project lock.
  RETURN row_owner IS NULL AND EXISTS(SELECT 1 FROM security.current_membership(v_session,v_tenant) m
   WHERE m.can_manage AND m.effective_role='PADMIN') AND security.can_read_agent(v_tenant);
 END IF;
 IF row_tenant IS DISTINCT FROM v_tenant THEN RETURN false; END IF;
 IF v_scope IN ('agents','usage_me') THEN
  RETURN (row_owner IS NULL OR row_owner=v_user) AND security.can_read_own_conversation(row_tenant,v_user);
 END IF;
 IF v_scope IN ('agent_admin','agent_settings','agent_availability','usage_admin','budget_admin','local_budget') THEN
  RETURN security.can_manage_current_tenant(row_tenant);
 END IF;
 RETURN false;
END; $body$;
ALTER FUNCTION security.operations_authorize(uuid,uuid,text,boolean) OWNER TO ai_policy_executor;
ALTER FUNCTION security.operations_row_allowed(uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.operations_authorize(uuid,uuid,text,boolean),security.operations_row_allowed(uuid,uuid)
 FROM PUBLIC,ai_web,ai_index,ai_meter;

-- Only safe agent columns remain directly readable by web. Instructions use an authorized fixed function.
REVOKE SELECT ON portal.agent_configs FROM ai_web;
GRANT SELECT(tenant_id,agent_key,config_version,enabled,updated_by,updated_at) ON portal.agent_configs TO ai_web;
GRANT USAGE ON SCHEMA portal TO ai_policy_executor;
GRANT SELECT ON portal.agent_configs TO ai_policy_executor;
GRANT UPDATE(settings,enabled,config_version,updated_by,updated_at) ON portal.agent_configs TO ai_policy_executor;
CREATE POLICY agent_operations_read ON portal.agent_configs FOR SELECT TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true) IN ('agents','agent_admin','agent_settings','agent_availability')
 AND security.operations_row_allowed(tenant_id,NULL));
CREATE POLICY agent_operations_write ON portal.agent_configs FOR UPDATE TO ai_policy_executor
 USING(current_setting('app.operations_scope',true) IN ('agent_settings','agent_availability')
 AND security.operations_row_allowed(tenant_id,NULL))
 WITH CHECK(current_setting('app.operations_scope',true) IN ('agent_settings','agent_availability')
 AND security.operations_row_allowed(tenant_id,NULL));
GRANT SELECT ON ops.tenant_budgets TO ai_policy_executor;
GRANT UPDATE(allocated_cap_krw,local_cap_krw,revision) ON ops.tenant_budgets TO ai_policy_executor;
CREATE POLICY tenant_budget_operations_read ON ops.tenant_budgets FOR SELECT TO ai_policy_executor
 USING(security.operations_row_allowed(tenant_id,NULL));
CREATE POLICY tenant_budget_operations_write ON ops.tenant_budgets FOR UPDATE TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true) IN ('local_budget','allocated_budget')
 AND security.operations_row_allowed(tenant_id,NULL))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true) IN ('local_budget','allocated_budget')
 AND security.operations_row_allowed(tenant_id,NULL));
GRANT SELECT(budget_id,approved_cap_krw,operational_cap_krw,reserved_krw,accounted_krw,active_slot) ON ops.project_budget TO ai_policy_executor;
GRANT UPDATE(stopped,revision) ON ops.project_budget TO ai_policy_executor;
GRANT SELECT(tenant_id,call_id,initiator_user_id,operation,budget_id,mode,state,reserved_krw,created_at) ON ops.call_attempts TO ai_policy_executor;
CREATE POLICY call_operations_read ON ops.call_attempts FOR SELECT TO ai_policy_executor
 USING(security.operations_row_allowed(tenant_id,initiator_user_id));
GRANT SELECT(tenant_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,token_counts) ON ops.usage_events TO ai_policy_executor;
CREATE POLICY usage_operations_read ON ops.usage_events FOR SELECT TO ai_policy_executor
 USING(EXISTS(SELECT 1 FROM ops.call_attempts c WHERE c.tenant_id=usage_events.tenant_id AND c.call_id=usage_events.call_id));

CREATE FUNCTION security.operations_read_window(p_session uuid,p_tenant uuid,p_scope text,p_digest bytea)
RETURNS TABLE(allowed boolean,retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_start timestamptz;v_now timestamptz;v_count integer;
BEGIN
 IF p_scope NOT IN ('agents','agent_admin','usage_me','usage_admin','budget_admin','platform_summary') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.operations_authorize(p_session,p_tenant,p_scope,false);
 IF p_digest IS NULL OR octet_length(p_digest)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 INSERT INTO security.login_windows(purpose,key_kind,key_digest,window_started_at,count)
 VALUES('http_read','principal',p_digest,clock_timestamp(),0) ON CONFLICT DO NOTHING;
 SELECT w.window_started_at,w.count INTO v_start,v_count FROM security.login_windows w
 WHERE w.purpose='http_read' AND w.key_kind='principal' AND w.key_digest=p_digest FOR UPDATE;
 PERFORM security.operations_authorize(p_session,p_tenant,p_scope,false);
 v_now:=clock_timestamp();
 IF v_now>=v_start+interval '1 minute' THEN
  v_start:=v_now;v_count:=0;
  UPDATE security.login_windows SET window_started_at=v_start,count=0
   WHERE purpose='http_read' AND key_kind='principal' AND key_digest=p_digest;
 END IF;
 IF v_count>=120 THEN
  RETURN QUERY SELECT false,GREATEST(1,ceil(extract(epoch FROM v_start+interval '1 minute'-v_now))::integer);RETURN; END IF;
 UPDATE security.login_windows w SET count=w.count+1 WHERE w.purpose='http_read' AND w.key_kind='principal' AND w.key_digest=p_digest;
 RETURN QUERY SELECT true,0;
END; $body$;

CREATE FUNCTION security.operations_read(p_session uuid,p_tenant uuid,p_kind text,p_period date,p_mode text,
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
   INTO v_items FROM portal.agent_configs a WHERE a.tenant_id=p_tenant;
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

CREATE FUNCTION security.operations_mutate(p_session uuid,p_tenant uuid,p_kind text,p_period date,p_mode text,
 p_agent text,p_delta jsonb,p_expected bigint,p_request uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
 v_agent portal.agent_configs%ROWTYPE;v_amount numeric;v_sum numeric;v_enabled boolean;v_revision bigint;
 v_target uuid;v_action text;v_revisions jsonb;v_result jsonb;v_key text;
BEGIN
 IF p_kind NOT IN ('agent_settings','agent_availability','local_budget','allocated_budget','global_availability') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 v_user:=security.operations_authorize(p_session,p_tenant,p_kind,true);
 IF p_period IS NULL OR extract(day FROM p_period)<>1 OR p_mode IS NULL OR p_mode NOT IN ('mock','real')
 OR p_expected IS NULL OR p_expected<1 OR p_request IS NULL OR p_delta IS NULL OR jsonb_typeof(p_delta)<>'object' THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_kind IN ('agent_settings','agent_availability') THEN
  SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent FOR UPDATE;
  PERFORM security.operations_authorize(p_session,p_tenant,p_kind,false);
  IF v_agent.agent_key IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  IF p_kind='agent_settings' THEN
   IF p_delta='{}'::jsonb OR p_delta-ARRAY['name','description','instructions']::text[]<>'{}'::jsonb THEN
    RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
   FOR v_key IN SELECT jsonb_object_keys(p_delta) LOOP
    IF jsonb_typeof(p_delta->v_key)<>'string' OR char_length(p_delta->>v_key)>(CASE v_key WHEN 'name' THEN 80 WHEN 'description' THEN 500 ELSE 2000 END)
    OR (v_key IN ('name','instructions') AND btrim(p_delta->>v_key)='') THEN
     RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
   END LOOP;
  ELSE
   IF p_delta-ARRAY['enabled']::text[]<>'{}'::jsonb OR NOT p_delta ? 'enabled' OR jsonb_typeof(p_delta->'enabled')<>'boolean' THEN
    RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  END IF;
  IF v_agent.config_version<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  UPDATE portal.agent_configs SET settings=CASE WHEN p_kind='agent_settings' THEN settings||p_delta ELSE settings END,
   enabled=CASE WHEN p_kind='agent_availability' THEN (p_delta->>'enabled')::boolean ELSE enabled END,
   config_version=config_version+1,updated_by=v_user,updated_at=clock_timestamp()
  WHERE tenant_id=p_tenant AND agent_key=p_agent;
  v_target:=NULL;v_revision:=p_expected+1;v_action:='operations_'||p_kind;
  v_result:=security.operations_read(p_session,p_tenant,'agent_admin',p_period,p_mode,p_agent,NULL,20);
 ELSE
  SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'BUDGET_STATE_UNAVAILABLE' USING ERRCODE='P0002'; END IF;
  IF p_kind='global_availability' THEN
   PERFORM security.operations_authorize(p_session,NULL,p_kind,false);
   IF p_delta-ARRAY['enabled']::text[]<>'{}'::jsonb OR NOT p_delta ? 'enabled' OR jsonb_typeof(p_delta->'enabled')<>'boolean' THEN
    RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
   v_enabled:=(p_delta->>'enabled')::boolean;
   IF v_project.revision<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
   IF v_enabled AND v_project.stop_latch THEN RAISE EXCEPTION 'REVIEW_REQUIRED' USING ERRCODE='B0210'; END IF;
   UPDATE ops.project_budget SET stopped=NOT v_enabled,revision=revision+1 WHERE budget_id=v_project.budget_id;
   v_target:=v_project.budget_id;v_revision:=p_expected+1;v_action:='operations_global_availability';
   v_result:=jsonb_build_object('period',p_period,'execution_mode',p_mode,'enabled',v_enabled,'revision',v_revision);
  ELSE
   SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'BUDGET_STATE_UNAVAILABLE' USING ERRCODE='P0002'; END IF;
   PERFORM security.operations_authorize(p_session,p_tenant,p_kind,false);
   v_key:=CASE WHEN p_kind='local_budget' THEN 'local_cap_krw' ELSE 'allocated_cap_krw' END;
   IF p_delta-ARRAY[v_key]::text[]<>'{}'::jsonb OR NOT p_delta ? v_key
    OR jsonb_typeof(p_delta->v_key)<>'string' OR p_delta->>v_key !~ '^(0|[1-9][0-9]{0,8})(\.[0-9]{1,2})?$' THEN
    RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
   v_amount:=(p_delta->>v_key)::numeric;
   IF v_amount>25000 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
   IF v_tenant.revision<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
   IF p_kind='local_budget' THEN
    IF v_amount>v_tenant.allocated_cap_krw THEN RAISE EXCEPTION 'BUDGET_LIMIT_CONFLICT' USING ERRCODE='B0209'; END IF;
    UPDATE ops.tenant_budgets SET local_cap_krw=v_amount,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
   ELSE
    -- Project lock serializes every allocation/local-cap writer and future reservations.
    SELECT COALESCE(sum(allocated_cap_krw),0) INTO v_sum FROM ops.tenant_budgets WHERE budget_id=v_project.budget_id;
    IF v_sum-v_tenant.allocated_cap_krw+v_amount>v_project.operational_cap_krw
     OR v_amount<v_tenant.accounted_krw+v_tenant.reserved_krw THEN
     RAISE EXCEPTION 'BUDGET_LIMIT_CONFLICT' USING ERRCODE='B0209'; END IF;
    UPDATE ops.tenant_budgets SET allocated_cap_krw=v_amount,local_cap_krw=LEAST(local_cap_krw,v_amount),revision=revision+1
     WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
   END IF;
   v_target:=p_tenant;v_revision:=p_expected+1;v_action:='operations_'||p_kind;
   v_result:=security.operations_read(p_session,p_tenant,'budget_admin',p_period,p_mode,NULL,NULL,20);
  END IF;
 END IF;
 v_revisions:=jsonb_build_object('expected_revision',p_expected,'revision',v_revision,'execution_mode',p_mode,'period',p_period);
 IF p_kind IN ('agent_settings','agent_availability') THEN v_revisions:=v_revisions||jsonb_build_object('agent_key',p_agent); END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,CASE WHEN p_tenant IS NULL THEN 'platform' ELSE 'tenant' END,p_tenant,v_user,v_action,v_target,'ok',v_revisions);
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN v_result;
END; $body$;
ALTER FUNCTION security.operations_read_window(uuid,uuid,text,bytea) OWNER TO ai_policy_executor;
ALTER FUNCTION security.operations_read(uuid,uuid,text,date,text,text,uuid,integer) OWNER TO ai_policy_executor;
ALTER FUNCTION security.operations_mutate(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.operations_read_window(uuid,uuid,text,bytea),
 security.operations_read(uuid,uuid,text,date,text,text,uuid,integer),
 security.operations_mutate(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.operations_read_window(uuid,uuid,text,bytea),
 security.operations_read(uuid,uuid,text,date,text,text,uuid,integer),
 security.operations_mutate(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) TO ai_web;
