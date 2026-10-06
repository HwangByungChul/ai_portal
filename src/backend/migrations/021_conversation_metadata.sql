-- DP03: owner metadata and soft deletion. Existing payload/ledger records stay intact.
ALTER TABLE portal.conversations ADD COLUMN title text NOT NULL DEFAULT '제목 없는 대화',
 ADD COLUMN pinned boolean NOT NULL DEFAULT false,
 ADD COLUMN metadata_revision bigint NOT NULL DEFAULT 0,
 ADD COLUMN deleted_at timestamptz,
 ADD CONSTRAINT conversation_title_valid CHECK(title=btrim(title) AND char_length(title) BETWEEN 1 AND 120 AND strpos(title,chr(10))=0 AND strpos(title,chr(13))=0),
 ADD CONSTRAINT conversation_metadata_revision_valid CHECK(metadata_revision>=0);
GRANT UPDATE(title,pinned,metadata_revision,deleted_at) ON portal.conversations TO ai_policy_executor;
CREATE INDEX conversation_history_position ON portal.conversations(tenant_id,owner_user_id,pinned DESC,created_at DESC,conversation_id DESC) WHERE deleted_at IS NULL;
CREATE POLICY audit_conversation_metadata ON ops.audit_events FOR INSERT TO ai_policy_executor
 WITH CHECK(scope_kind='tenant' AND current_setting('app.run_scope',true)='owner'
 AND security.run_row_allowed(tenant_id,actor_id) AND action IN ('conversation_updated','conversation_deleted'));
CREATE POLICY conversation_current_metadata ON portal.conversations FOR SELECT TO ai_policy_executor USING(session_user='ai_web' AND security.can_read_own_conversation(tenant_id,owner_user_id));
CREATE POLICY conversation_active_owner ON portal.conversations AS RESTRICTIVE FOR SELECT TO ai_web USING(deleted_at IS NULL);
CREATE POLICY run_active_conversation ON portal.runs AS RESTRICTIVE FOR SELECT TO ai_web
 USING(EXISTS(SELECT 1 FROM portal.conversations c WHERE c.tenant_id=runs.tenant_id AND c.conversation_id=runs.conversation_id AND c.deleted_at IS NULL));
CREATE POLICY message_active_conversation ON portal.messages AS RESTRICTIVE FOR SELECT TO ai_web
 USING(EXISTS(SELECT 1 FROM portal.conversations c WHERE c.tenant_id=messages.tenant_id AND c.conversation_id=messages.conversation_id AND c.deleted_at IS NULL));

CREATE FUNCTION security.conversation_list(p_session uuid,p_tenant uuid,p_query text,p_pinned boolean,p_cursor jsonb,p_limit integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_items jsonb;v_pin boolean;v_time timestamptz;v_id uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_query IS NULL OR char_length(p_query)>120 OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_cursor IS NOT NULL THEN
  IF jsonb_typeof(p_cursor)<>'object' OR p_cursor-ARRAY['pinned','created_at','id']::text[]<>'{}'::jsonb
  OR NOT p_cursor ?& ARRAY['pinned','created_at','id']::text[] OR jsonb_typeof(p_cursor->'pinned')<>'boolean' THEN
   RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  BEGIN v_pin:=(p_cursor->>'pinned')::boolean;v_time:=(p_cursor->>'created_at')::timestamptz;v_id:=(p_cursor->>'id')::uuid;
  EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END;
  IF v_time IS NULL OR v_id IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 END IF;
 SELECT coalesce(jsonb_agg(q.value ORDER BY q.pinned DESC,q.created_at DESC,q.id DESC),'[]'::jsonb) INTO v_items FROM (
  SELECT c.pinned,c.created_at,c.conversation_id AS id,jsonb_build_object('conversation_id',c.conversation_id,'tenant_id',c.tenant_id,
   'agent_key',c.agent_key,'created_at',c.created_at,'updated_at',c.updated_at,'title',c.title,'pinned',c.pinned,'metadata_revision',c.metadata_revision,
   'recent_state',(SELECT r.state FROM portal.runs r WHERE r.tenant_id=c.tenant_id AND r.conversation_id=c.conversation_id ORDER BY r.created_at DESC,r.run_id DESC LIMIT 1)) AS value
  FROM portal.conversations c WHERE c.tenant_id=p_tenant AND c.deleted_at IS NULL
   AND (p_query='' OR strpos(lower(c.title),lower(p_query))>0) AND (p_pinned IS NULL OR c.pinned=p_pinned)
   AND (p_cursor IS NULL OR (c.pinned,c.created_at,c.conversation_id)<(v_pin,v_time,v_id))
  ORDER BY c.pinned DESC,c.created_at DESC,c.conversation_id DESC LIMIT p_limit+1) q;
 RETURN jsonb_build_object('items',v_items);
END; $body$;

CREATE FUNCTION security.conversation_mutate(p_session uuid,p_tenant uuid,p_id uuid,p_delta jsonb,p_revision bigint,p_delete boolean,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_row portal.conversations%ROWTYPE;v_title text;v_pinned boolean;v_replay boolean:=false;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_id IS NULL OR p_revision IS NULL OR p_revision<0 OR p_delete IS NULL OR p_request IS NULL OR p_delta IS NULL
 OR jsonb_typeof(p_delta)<>'object' OR p_delta-ARRAY['title','pinned']::text[]<>'{}'::jsonb
 OR (p_delete AND p_delta<>'{}'::jsonb) OR (NOT p_delete AND p_delta='{}'::jsonb) THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF (p_delta ? 'title' AND (jsonb_typeof(p_delta->'title')<>'string' OR char_length(btrim(p_delta->>'title')) NOT BETWEEN 1 AND 120
 OR strpos(p_delta->>'title',chr(10))>0 OR strpos(p_delta->>'title',chr(13))>0))
 OR (p_delta ? 'pinned' AND jsonb_typeof(p_delta->'pinned')<>'boolean') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_row FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF v_row.deleted_at IS NOT NULL AND NOT p_delete THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 v_title:=CASE WHEN p_delta ? 'title' THEN btrim(p_delta->>'title') ELSE v_row.title END;
 v_pinned:=CASE WHEN p_delta ? 'pinned' THEN (p_delta->>'pinned')::boolean ELSE v_row.pinned END;
 IF v_row.metadata_revision<>p_revision THEN
  IF v_row.metadata_revision-1=p_revision AND ((p_delete AND v_row.deleted_at IS NOT NULL)
   OR (NOT p_delete AND v_title=v_row.title AND v_pinned=v_row.pinned)) THEN v_replay:=true;
  ELSE RAISE EXCEPTION 'METADATA_CONFLICT' USING ERRCODE='B0311'; END IF;
 ELSE
  v_replay:=(p_delete AND v_row.deleted_at IS NOT NULL) OR (NOT p_delete AND v_title=v_row.title AND v_pinned=v_row.pinned);
 END IF;
 IF NOT v_replay THEN
  IF p_delete AND EXISTS(SELECT 1 FROM portal.runs WHERE tenant_id=p_tenant AND conversation_id=p_id AND state NOT IN ('completed','failed','cancelled','blocked','interrupted')) THEN
   RAISE EXCEPTION 'CONVERSATION_BUSY' USING ERRCODE='B0312'; END IF;
  UPDATE portal.conversations SET title=v_title,pinned=v_pinned,metadata_revision=metadata_revision+1,
   deleted_at=CASE WHEN p_delete THEN clock_timestamp() ELSE NULL END
   WHERE tenant_id=p_tenant AND conversation_id=p_id RETURNING * INTO v_row;
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
   VALUES(p_request,'tenant',p_tenant,v_user,CASE WHEN p_delete THEN 'conversation_deleted' ELSE 'conversation_updated' END,p_id,'ok',jsonb_build_object('metadata_revision',v_row.metadata_revision));
 END IF;
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 IF p_delete THEN RETURN jsonb_build_object('conversation_id',p_id,'deleted',true,'metadata_revision',v_row.metadata_revision,'replayed',v_replay); END IF;
 RETURN jsonb_build_object('conversation_id',p_id,'title',v_row.title,'pinned',v_row.pinned,'metadata_revision',v_row.metadata_revision,'replayed',v_replay);
END; $body$;
ALTER FUNCTION security.conversation_list(uuid,uuid,text,boolean,jsonb,integer) OWNER TO ai_policy_executor;
ALTER FUNCTION security.conversation_mutate(uuid,uuid,uuid,jsonb,bigint,boolean,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.conversation_list(uuid,uuid,text,boolean,jsonb,integer),security.conversation_mutate(uuid,uuid,uuid,jsonb,bigint,boolean,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.conversation_list(uuid,uuid,text,boolean,jsonb,integer),security.conversation_mutate(uuid,uuid,uuid,jsonb,bigint,boolean,uuid) TO ai_web;

CREATE OR REPLACE FUNCTION security.conversation_create(p_session uuid,p_tenant uuid,p_agent text,p_client uuid,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_row portal.conversations%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_agent IS NULL OR p_agent NOT IN ('general','rules_rag') OR p_request IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
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

CREATE OR REPLACE FUNCTION security.run_prepare(p_session uuid,p_tenant uuid,p_agent text,p_conversation uuid,p_send uuid,p_hash bytea,p_period date,p_mode text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_existing portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
 v_conversation portal.conversations%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_budget ops.tenant_budgets%ROWTYPE;v_history jsonb;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_send IS NULL OR p_hash IS NULL OR octet_length(p_hash)<>32 OR p_agent IS NULL OR p_agent NOT IN ('general','rules_rag')
 OR p_period IS NULL OR extract(day FROM p_period)<>1 OR p_mode IS NULL OR p_mode NOT IN ('mock','real') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
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

CREATE OR REPLACE FUNCTION security.run_view(p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_result jsonb;v_usage text;v_terminal boolean;
BEGIN
 IF current_setting('app.run_scope',true) IS DISTINCT FROM 'owner' THEN
  RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF NOT EXISTS(SELECT 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id AND deleted_at IS NULL) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
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

CREATE OR REPLACE FUNCTION security.run_read(p_session uuid,p_tenant uuid,p_kind text,p_target uuid,p_cursor jsonb,p_limit integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_items jsonb;v_id uuid;v_cursor_time timestamptz;v_cursor_id uuid;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,false);
 IF p_kind IS NULL OR p_kind NOT IN ('conversations','messages','run','by_send') OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_kind='conversations' THEN RETURN security.conversation_list(p_session,p_tenant,'',NULL,p_cursor,p_limit); END IF;
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
  RETURN security.conversation_list(p_session,p_tenant,'',NULL,p_cursor,p_limit);
 ELSE
  PERFORM 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_target AND deleted_at IS NULL;
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

CREATE OR REPLACE FUNCTION security.can_read_rag_answer_payload(p_tenant uuid,p_run uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' THEN RETURN false;END IF;
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND OR NOT security.can_read_own_conversation(p_tenant,r.owner_user_id) THEN RETURN false;END IF;
 IF NOT EXISTS(SELECT 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id AND deleted_at IS NULL) THEN RETURN false; END IF;
 IF r.agent_key='general' THEN RETURN true;END IF;
 IF r.state<>'completed' OR NOT r.provenance_sealed OR NOT EXISTS(SELECT 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' AND enabled) THEN RETURN false;END IF;
 IF (SELECT count(*) FROM portal.answer_evidence WHERE tenant_id=p_tenant AND run_id=p_run)<>r.source_count THEN RETURN false;END IF;
 RETURN NOT EXISTS(SELECT 1 FROM portal.answer_evidence e WHERE e.tenant_id=p_tenant AND e.run_id=p_run AND (e.payload_purged OR NOT security.document_can_read(e.source_tenant_id,e.document_id,e.version_id,e.index_id) OR NOT EXISTS(SELECT 1 FROM rag.document_versions v WHERE (v.tenant_id,v.document_id,v.version_id,v.source_sha256)=(e.source_tenant_id,e.document_id,e.version_id,e.source_sha256) AND NOT v.payload_purged)));
END;$body$;
