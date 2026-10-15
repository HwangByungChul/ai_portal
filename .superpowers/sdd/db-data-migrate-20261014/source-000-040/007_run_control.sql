-- B03 owner conversation/run intake only; no provider permit, worker or ledger mutation.
CREATE FUNCTION security.run_authorize(p_session uuid,p_tenant uuid,p_lock boolean)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 SELECT user_id INTO v_user FROM security.sessions WHERE session_id=p_session;
 IF NOT FOUND THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 BEGIN
  IF NULLIF(current_setting('app.session_id',true),'')::uuid IS DISTINCT FROM p_session
  OR NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM v_user
  OR NULLIF(current_setting('app.tenant_id',true),'')::uuid IS DISTINCT FROM p_tenant
  OR p_tenant IS NULL OR p_lock IS NULL THEN RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
 EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END;
 IF p_lock THEN
  PERFORM user_id FROM security.accounts WHERE user_id=v_user FOR SHARE;
  PERFORM tenant_id FROM security.tenants WHERE tenant_id=p_tenant FOR SHARE;
  PERFORM user_id FROM security.platform_access WHERE user_id=v_user FOR SHARE;
  PERFORM session_id FROM security.sessions WHERE session_id=p_session FOR UPDATE;
  PERFORM user_id FROM security.memberships WHERE tenant_id=p_tenant AND user_id=v_user FOR SHARE;
  PERFORM user_id FROM security.managed_tenants WHERE tenant_id=p_tenant AND user_id=v_user FOR SHARE;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM security.current_membership(p_session,p_tenant))
 OR NOT security.can_read_own_conversation(p_tenant,v_user) THEN
  RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 PERFORM set_config('app.run_scope','owner',true);
 RETURN v_user;
END; $body$;

CREATE FUNCTION security.run_row_allowed(row_tenant uuid,row_owner uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_scope text;v_user uuid;v_tenant uuid;
BEGIN
 IF session_user<>'ai_web' THEN RETURN false; END IF;
 BEGIN
  v_scope:=NULLIF(current_setting('app.run_scope',true),'');
  v_user:=NULLIF(current_setting('app.user_id',true),'')::uuid;
  v_tenant:=NULLIF(current_setting('app.tenant_id',true),'')::uuid;
 EXCEPTION WHEN invalid_text_representation THEN RETURN false; END;
 IF NOT security.can_read_own_conversation(v_tenant,v_user) THEN RETURN false; END IF;
 -- Internal admit-only COUNT scope, never a content-returning scope.
 IF v_scope='capacity' THEN RETURN true; END IF;
 RETURN v_scope='owner' AND row_tenant=v_tenant AND (row_owner IS NULL OR row_owner=v_user);
END; $body$;
ALTER FUNCTION security.run_authorize(uuid,uuid,boolean) OWNER TO ai_policy_executor;
ALTER FUNCTION security.run_row_allowed(uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.run_authorize(uuid,uuid,boolean),security.run_row_allowed(uuid,uuid)
 FROM PUBLIC,ai_web,ai_index,ai_meter;

GRANT SELECT,INSERT ON portal.conversations TO ai_policy_executor;
GRANT UPDATE(updated_at) ON portal.conversations TO ai_policy_executor;
CREATE POLICY conversation_run_owner ON portal.conversations TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id))
 WITH CHECK(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id));
GRANT SELECT,INSERT ON portal.runs TO ai_policy_executor;
GRANT UPDATE(state,stage,revision,ended_at,cancel_requested_at) ON portal.runs TO ai_policy_executor;
CREATE POLICY run_control_read ON portal.runs FOR SELECT TO ai_policy_executor
 USING(security.run_row_allowed(tenant_id,owner_user_id));
CREATE POLICY run_control_insert ON portal.runs FOR INSERT TO ai_policy_executor
 WITH CHECK(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id));
CREATE POLICY run_control_update ON portal.runs FOR UPDATE TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id))
 WITH CHECK(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id));
GRANT SELECT,INSERT ON portal.messages TO ai_policy_executor;
CREATE POLICY message_run_owner_read ON portal.messages FOR SELECT TO ai_policy_executor
 USING((current_setting('app.run_scope',true)='sequence' AND security.can_read_own_conversation(tenant_id,owner_user_id))
 OR (current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id)
 AND NOT payload_purged AND (role='user' OR EXISTS(SELECT 1 FROM portal.runs r
 WHERE r.tenant_id=messages.tenant_id AND r.run_id=messages.run_id AND r.state='completed' AND r.answer_kind='answer'))));
CREATE POLICY message_run_owner_insert ON portal.messages FOR INSERT TO ai_policy_executor
 WITH CHECK(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id)
 AND role='user' AND payload_kind='user' AND NOT payload_purged);
CREATE POLICY agent_run_read ON portal.agent_configs FOR SELECT TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,NULL));
CREATE POLICY agent_run_lock ON portal.agent_configs FOR UPDATE TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,NULL)) WITH CHECK(false);
CREATE POLICY budget_run_read ON ops.tenant_budgets FOR SELECT TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,NULL));
CREATE POLICY budget_run_lock ON ops.tenant_budgets FOR UPDATE TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,NULL)) WITH CHECK(false);
GRANT SELECT(run_id) ON ops.call_attempts TO ai_policy_executor;
CREATE POLICY call_run_read ON ops.call_attempts FOR SELECT TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,initiator_user_id));
CREATE POLICY usage_run_read ON ops.usage_events FOR SELECT TO ai_policy_executor
 USING(EXISTS(SELECT 1 FROM ops.call_attempts c WHERE c.tenant_id=usage_events.tenant_id AND c.call_id=usage_events.call_id));
CREATE POLICY audit_run_insert ON ops.audit_events FOR INSERT TO ai_policy_executor
 WITH CHECK(scope_kind='tenant' AND current_setting('app.run_scope',true)='owner'
 AND security.run_row_allowed(tenant_id,actor_id) AND action IN ('run_admitted','run_cancelled','run_cancel_requested','conversation_created'));

CREATE FUNCTION security.run_view(p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_result jsonb;v_usage text;v_terminal boolean;
BEGIN
 IF current_setting('app.run_scope',true) IS DISTINCT FROM 'owner' THEN
  RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 v_terminal:=v_run.state IN ('completed','failed','cancelled','blocked','interrupted');
 SELECT CASE WHEN bool_or(c.state='usage_unknown') THEN 'unknown'
  WHEN bool_or(c.state IN ('reserved','dispatched')) THEN 'estimated'
  WHEN bool_or(c.state='settled') THEN 'final' ELSE 'none' END INTO v_usage
 FROM ops.call_attempts c WHERE c.tenant_id=p_tenant AND c.run_id=p_run;
 IF v_run.state='completed' THEN
  SELECT jsonb_build_object('message_id',m.message_id,'text',m.body,'evidence','[]'::jsonb) INTO v_result
  FROM portal.messages m WHERE m.tenant_id=p_tenant AND m.run_id=p_run AND m.role='assistant'
  ORDER BY m.sequence_no DESC LIMIT 1;
 END IF;
 RETURN jsonb_build_object('run_id',v_run.run_id,'tenant_id',v_run.tenant_id,'conversation_id',v_run.conversation_id,
  'agent_key',v_run.agent_key,'config_version',v_run.config_snapshot->'config_version','state',v_run.state,
  'stage',v_run.stage,'revision',v_run.revision,'is_terminal',v_terminal,'answer_kind',v_run.answer_kind,
  'content_status',CASE WHEN v_run.state='completed' AND v_result IS NOT NULL THEN 'final' WHEN v_terminal THEN 'unavailable' ELSE 'pending' END,
  'execution_mode',v_run.execution_mode,'usage_status',v_usage,'error_code',v_run.safe_error_code,
  'created_at',v_run.created_at,'ended_at',v_run.ended_at,'cancel_requested_at',v_run.cancel_requested_at,'result',v_result);
END; $body$;
ALTER FUNCTION security.run_view(uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.run_view(uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;

CREATE FUNCTION security.run_read_window(p_session uuid,p_tenant uuid,p_digest bytea)
RETURNS TABLE(allowed boolean,retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_start timestamptz;v_now timestamptz;v_count integer;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_digest IS NULL OR octet_length(p_digest)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 INSERT INTO security.login_windows VALUES('http_read','principal',p_digest,clock_timestamp(),0) ON CONFLICT DO NOTHING;
 SELECT window_started_at,count INTO v_start,v_count FROM security.login_windows
 WHERE purpose='http_read' AND key_kind='principal' AND key_digest=p_digest FOR UPDATE;
 PERFORM security.run_authorize(p_session,p_tenant,false);v_now:=clock_timestamp();
 IF v_now>=v_start+interval '1 minute' THEN
  v_start:=v_now;v_count:=0;
  UPDATE security.login_windows SET window_started_at=v_start,count=0 WHERE purpose='http_read' AND key_kind='principal' AND key_digest=p_digest;
 END IF;
 IF v_count>=120 THEN RETURN QUERY SELECT false,GREATEST(1,ceil(extract(epoch FROM v_start+interval '1 minute'-v_now))::integer);RETURN; END IF;
 UPDATE security.login_windows SET count=count+1 WHERE purpose='http_read' AND key_kind='principal' AND key_digest=p_digest;
 RETURN QUERY SELECT true,0;
END; $body$;

CREATE FUNCTION security.run_read(p_session uuid,p_tenant uuid,p_kind text,p_target uuid,p_cursor jsonb,p_limit integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_items jsonb;v_id uuid;v_cursor_time timestamptz;v_cursor_id uuid;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,false);
 IF p_kind IS NULL OR p_kind NOT IN ('conversations','messages','run','by_send') OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_cursor IS NOT NULL THEN
  IF jsonb_typeof(p_cursor)<>'object' OR p_cursor-ARRAY['created_at','id']::text[]<>'{}'::jsonb
   OR NOT p_cursor ?& ARRAY['created_at','id']::text[] THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  BEGIN v_cursor_time:=(p_cursor->>'created_at')::timestamptz;v_cursor_id:=(p_cursor->>'id')::uuid;
  EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END;
  IF v_cursor_time IS NULL OR v_cursor_id IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 END IF;
 IF p_kind IN ('run','by_send') THEN
  SELECT run_id INTO v_id FROM portal.runs WHERE tenant_id=p_tenant AND
   CASE WHEN p_kind='run' THEN run_id=p_target ELSE client_send_id=p_target END;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  RETURN security.run_view(p_tenant,v_id);
 ELSIF p_kind='conversations' THEN
  SELECT COALESCE(jsonb_agg(q.value ORDER BY q.created_at,q.id),'[]'::jsonb) INTO v_items FROM (
   SELECT c.created_at,c.conversation_id AS id,jsonb_build_object('conversation_id',c.conversation_id,'tenant_id',c.tenant_id,
    'agent_key',c.agent_key,'created_at',c.created_at,'updated_at',c.updated_at,
    'recent_state',(SELECT r.state FROM portal.runs r WHERE r.tenant_id=c.tenant_id AND r.conversation_id=c.conversation_id ORDER BY r.created_at DESC,r.run_id DESC LIMIT 1)) AS value
   FROM portal.conversations c WHERE c.tenant_id=p_tenant AND
    (p_cursor IS NULL OR (c.created_at,c.conversation_id)>(v_cursor_time,v_cursor_id))
   ORDER BY c.created_at,c.conversation_id LIMIT p_limit+1) q;
 ELSE
  PERFORM 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_target;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  SELECT COALESCE(jsonb_agg(q.value ORDER BY q.created_at,q.id),'[]'::jsonb) INTO v_items FROM (
   SELECT m.created_at,m.message_id AS id,jsonb_build_object('message_id',m.message_id,'run_id',m.run_id,'sequence_no',m.sequence_no,
    'role',m.role,'text',m.body,'created_at',m.created_at,'run_state',r.state,'answer_kind',r.answer_kind) AS value
   FROM portal.messages m JOIN portal.runs r ON r.tenant_id=m.tenant_id AND r.run_id=m.run_id
   WHERE m.tenant_id=p_tenant AND m.conversation_id=p_target AND
    (p_cursor IS NULL OR (m.created_at,m.message_id)>(v_cursor_time,v_cursor_id))
   ORDER BY m.created_at,m.message_id LIMIT p_limit+1) q;
 END IF;
 RETURN jsonb_build_object('items',v_items);
END; $body$;

CREATE FUNCTION security.conversation_create(p_session uuid,p_tenant uuid,p_agent text,p_client uuid,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_row portal.conversations%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_agent IS NULL OR p_agent NOT IN ('general','rules_rag') OR p_request IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_client IS NOT NULL THEN
  SELECT * INTO v_row FROM portal.conversations WHERE tenant_id=p_tenant AND client_conversation_id=p_client FOR UPDATE;
  IF FOUND THEN
   IF v_row.agent_key<>p_agent THEN RAISE EXCEPTION 'CONVERSATION_AGENT_MISMATCH' USING ERRCODE='B0302'; END IF;
   RETURN jsonb_build_object('conversation_id',v_row.conversation_id,'tenant_id',p_tenant,'agent_key',v_row.agent_key,'created_at',v_row.created_at,'replayed',true);
  END IF;
 END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent FOR SHARE;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF NOT FOUND OR v_agent.agent_key IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF NOT v_agent.enabled THEN RAISE EXCEPTION 'AGENT_STOPPED' USING ERRCODE='B0303'; END IF;
 IF p_agent<>'general' THEN RAISE EXCEPTION 'FEATURE_NOT_READY' USING ERRCODE='B0304'; END IF;
 INSERT INTO portal.conversations(tenant_id,conversation_id,owner_user_id,agent_key,client_conversation_id)
 VALUES(p_tenant,gen_random_uuid(),v_user,p_agent,p_client)
 ON CONFLICT(tenant_id,owner_user_id,client_conversation_id) DO NOTHING RETURNING * INTO v_row;
 IF NOT FOUND THEN
  SELECT * INTO v_row FROM portal.conversations WHERE tenant_id=p_tenant AND client_conversation_id=p_client;
  IF v_row.agent_key<>p_agent THEN RAISE EXCEPTION 'CONVERSATION_AGENT_MISMATCH' USING ERRCODE='B0302'; END IF;
  RETURN jsonb_build_object('conversation_id',v_row.conversation_id,'tenant_id',p_tenant,'agent_key',v_row.agent_key,'created_at',v_row.created_at,'replayed',true);
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,'conversation_created',v_row.conversation_id,'ok',jsonb_build_object('agent_key',p_agent));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN jsonb_build_object('conversation_id',v_row.conversation_id,'tenant_id',p_tenant,'agent_key',v_row.agent_key,'created_at',v_row.created_at,'replayed',false);
END; $body$;

CREATE FUNCTION security.run_prepare(p_session uuid,p_tenant uuid,p_agent text,p_conversation uuid,p_send uuid,p_hash bytea,p_period date,p_mode text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_existing portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
 v_conversation portal.conversations%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_budget ops.tenant_budgets%ROWTYPE;v_history jsonb;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_send IS NULL OR p_hash IS NULL OR octet_length(p_hash)<>32 OR p_agent IS NULL OR p_agent NOT IN ('general','rules_rag')
 OR p_period IS NULL OR extract(day FROM p_period)<>1 OR p_mode IS NULL OR p_mode NOT IN ('mock','real') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_conversation IS NOT NULL THEN
  SELECT * INTO v_conversation FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_conversation;
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
 IF p_agent<>'general' THEN RAISE EXCEPTION 'FEATURE_NOT_READY' USING ERRCODE='B0304'; END IF;
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
 IF v_project.reserved_krw+v_project.accounted_krw+3.64>v_project.operational_cap_krw
 OR v_budget.reserved_krw+v_budget.accounted_krw+3.64>v_budget.local_cap_krw THEN
  RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0306'; END IF;
 IF p_conversation IS NOT NULL THEN
  PERFORM conversation_id FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_conversation FOR UPDATE;
 END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('message_id',q.message_id,'role',q.role,'content',q.body) ORDER BY q.sequence_no),'[]'::jsonb)
 INTO v_history FROM (SELECT m.message_id,m.role,m.body,m.sequence_no FROM portal.messages m
 WHERE m.tenant_id=p_tenant AND m.conversation_id=p_conversation ORDER BY m.sequence_no DESC LIMIT 6) q;
 RETURN jsonb_build_object('instructions',COALESCE(NULLIF(v_agent.settings->>'instructions',''),'사용자 질문에 간결하고 정확하게 답변하세요.'),
  'config_version',v_agent.config_version,'history',v_history);
END; $body$;

CREATE FUNCTION security.run_admit(p_session uuid,p_tenant uuid,p_agent text,p_conversation uuid,p_send uuid,p_hash bytea,
 p_prompt text,p_period date,p_mode text,p_version bigint,p_selected uuid[],p_tokens integer,p_digest bytea,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_ready jsonb;v_run uuid;v_conversation uuid;v_sequence bigint;v_snapshot jsonb;
 v_count_user integer;v_count_tenant integer;v_count_project integer;v_start timestamptz;v_count integer;v_now timestamptz;
BEGIN
 v_ready:=security.run_prepare(p_session,p_tenant,p_agent,p_conversation,p_send,p_hash,p_period,p_mode);
 IF v_ready ? 'replay' THEN RETURN v_ready->'replay'; END IF;
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
  'instructions',v_ready->>'instructions','selected_history_ids',to_jsonb(p_selected),'estimated_input_tokens',p_tokens) INTO v_snapshot
 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_agent;
 INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,request_hash,agent_key,config_snapshot,origin_session_id,execution_mode)
 VALUES(p_tenant,v_run,v_conversation,v_user,p_send,p_hash,p_agent,v_snapshot,p_session,p_mode);
 INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind)
 VALUES(p_tenant,gen_random_uuid(),v_conversation,v_user,p_agent,v_sequence,'user',p_prompt,v_run,'user');
 UPDATE portal.conversations SET updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND conversation_id=v_conversation;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,'run_admitted',v_run,'ok',jsonb_build_object('revision',1,'execution_mode',p_mode,'config_version',p_version));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN security.run_view(p_tenant,v_run)||jsonb_build_object('replayed',false);
END; $body$;

CREATE FUNCTION security.run_cancel(p_session uuid,p_tenant uuid,p_run uuid,p_expected bigint,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_row portal.runs%ROWTYPE;v_action text;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO v_row FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF v_row.run_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF p_expected IS NULL OR p_expected<1 OR p_request IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF v_row.state IN ('completed','failed','cancelled','blocked','interrupted','cancel_requested') THEN RETURN security.run_view(p_tenant,p_run); END IF;
 IF v_row.revision<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 IF v_row.state='accepted' THEN
  IF EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run) THEN
   RAISE EXCEPTION 'REVIEW_REQUIRED' USING ERRCODE='B0210'; END IF;
  UPDATE portal.runs SET state='cancelled',stage='terminal',revision=revision+1,
   cancel_requested_at=clock_timestamp(),ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_run;
  v_action:='run_cancelled';
 ELSE
  UPDATE portal.runs SET state='cancel_requested',revision=revision+1,cancel_requested_at=clock_timestamp()
   WHERE tenant_id=p_tenant AND run_id=p_run;
  v_action:='run_cancel_requested';
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,v_action,p_run,'ok',jsonb_build_object('expected_revision',p_expected,'revision',p_expected+1));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN security.run_view(p_tenant,p_run);
END; $body$;

ALTER FUNCTION security.run_read_window(uuid,uuid,bytea) OWNER TO ai_policy_executor;
ALTER FUNCTION security.run_read(uuid,uuid,text,uuid,jsonb,integer) OWNER TO ai_policy_executor;
ALTER FUNCTION security.conversation_create(uuid,uuid,text,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.run_prepare(uuid,uuid,text,uuid,uuid,bytea,date,text) OWNER TO ai_policy_executor;
ALTER FUNCTION security.run_admit(uuid,uuid,text,uuid,uuid,bytea,text,date,text,bigint,uuid[],integer,bytea,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.run_cancel(uuid,uuid,uuid,bigint,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.run_read_window(uuid,uuid,bytea),security.run_read(uuid,uuid,text,uuid,jsonb,integer),
 security.conversation_create(uuid,uuid,text,uuid,uuid),security.run_prepare(uuid,uuid,text,uuid,uuid,bytea,date,text),
 security.run_admit(uuid,uuid,text,uuid,uuid,bytea,text,date,text,bigint,uuid[],integer,bytea,uuid),security.run_cancel(uuid,uuid,uuid,bigint,uuid)
 FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.run_read_window(uuid,uuid,bytea),security.run_read(uuid,uuid,text,uuid,jsonb,integer),
 security.conversation_create(uuid,uuid,text,uuid,uuid),security.run_prepare(uuid,uuid,text,uuid,uuid,bytea,date,text),
 security.run_admit(uuid,uuid,text,uuid,uuid,bytea,text,date,text,bigint,uuid[],integer,bytea,uuid),security.run_cancel(uuid,uuid,uuid,bigint,uuid) TO ai_web;
