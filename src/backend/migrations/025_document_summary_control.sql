-- DP-07: add two owner/current-source RLS tables and server-only run task kind.
-- Replacements: run binding, run_prepare, execution_claim/guard/finish,
-- rag_call_reserve/rag_finish, can_read_rag_answer_payload, feedback target.
-- Existing relation provenance and central dispatch/meter/accounting are unchanged.
ALTER TABLE portal.runs ADD COLUMN task_kind text NOT NULL DEFAULT 'chat'
 CONSTRAINT runs_task_kind CHECK(task_kind IN ('chat','document_summary'));
ALTER TABLE portal.runs ADD CONSTRAINT runs_summary_agent CHECK(task_kind='chat' OR agent_key='rules_rag');
CREATE TABLE portal.summary_requests(
 tenant_id uuid NOT NULL,run_id uuid NOT NULL,owner_user_id uuid NOT NULL,
 source_tenant_id uuid NOT NULL,document_id uuid NOT NULL,version_id uuid NOT NULL,index_id uuid NOT NULL,
 source_sha256 bytea NOT NULL CHECK(octet_length(source_sha256)=32),bullet_count integer NOT NULL CHECK(bullet_count IN (3,5)),
 request_hash bytea NOT NULL CHECK(octet_length(request_hash)=32),parent_run_id uuid,
 policy_revision text NOT NULL CHECK(policy_revision='summary-v1'),parser_revision text NOT NULL CHECK(parser_revision='source-map-v1'),
 candidates jsonb NOT NULL CHECK(jsonb_typeof(candidates)='array' AND jsonb_array_length(candidates)<=128),
 result text CHECK(result IS NULL OR octet_length(result)<=65536),
 PRIMARY KEY(tenant_id,run_id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES portal.runs(tenant_id,run_id),
 FOREIGN KEY(tenant_id,parent_run_id) REFERENCES portal.summary_requests(tenant_id,run_id),
 FOREIGN KEY(source_tenant_id,document_id,version_id,index_id) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id));
CREATE TABLE portal.summary_evidence(
 tenant_id uuid NOT NULL,run_id uuid NOT NULL,ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 4),
 source_tenant_id uuid NOT NULL,document_id uuid NOT NULL,version_id uuid NOT NULL,index_id uuid NOT NULL,evidence_id uuid NOT NULL,
 source_sha256 bytea NOT NULL CHECK(octet_length(source_sha256)=32),
 quote_snapshot text NOT NULL CHECK(btrim(quote_snapshot)<>''),quote_sha256 bytea GENERATED ALWAYS AS(security.quote_digest(quote_snapshot)) STORED,
 location_snapshot jsonb NOT NULL CHECK(jsonb_typeof(location_snapshot)='object'),candidate_id text NOT NULL,
 PRIMARY KEY(tenant_id,run_id,ordinal),UNIQUE(tenant_id,run_id,candidate_id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES portal.summary_requests(tenant_id,run_id),
 FOREIGN KEY(source_tenant_id,document_id,version_id,index_id,evidence_id) REFERENCES rag.evidence(tenant_id,document_id,version_id,index_id,evidence_id));
ALTER TABLE portal.summary_requests OWNER TO ai_owner;
ALTER TABLE portal.summary_evidence OWNER TO ai_owner;
ALTER TABLE portal.summary_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.summary_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.summary_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.summary_evidence FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.summary_requests,portal.summary_evidence FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
GRANT SELECT ON portal.summary_requests,portal.summary_evidence TO ai_web,ai_policy_executor;
GRANT INSERT ON portal.summary_requests,portal.summary_evidence TO ai_policy_executor;
GRANT UPDATE(result) ON portal.summary_requests TO ai_policy_executor;
CREATE POLICY summary_request_owner ON portal.summary_requests TO ai_web,ai_policy_executor
 USING(session_user='ai_web' AND security.can_read_own_conversation(tenant_id,owner_user_id)
 AND EXISTS(SELECT 1 FROM portal.runs r WHERE (r.tenant_id,r.run_id)=(summary_requests.tenant_id,summary_requests.run_id) AND r.task_kind='document_summary')
 AND security.document_can_read(source_tenant_id,document_id,version_id,index_id));
CREATE POLICY summary_evidence_owner ON portal.summary_evidence FOR SELECT TO ai_web,ai_policy_executor
 USING(session_user='ai_web' AND EXISTS(SELECT 1 FROM portal.summary_requests q WHERE (q.tenant_id,q.run_id)=(summary_evidence.tenant_id,summary_evidence.run_id)));
CREATE POLICY summary_evidence_seal ON portal.summary_evidence FOR INSERT TO ai_policy_executor
 WITH CHECK(session_user='ai_web' AND current_setting('app.summary_finalize',true)=run_id::text
 AND EXISTS(SELECT 1 FROM portal.summary_requests q WHERE (q.tenant_id,q.run_id)=(summary_evidence.tenant_id,summary_evidence.run_id)));
CREATE FUNCTION portal.summary_binding_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
 IF TG_TABLE_NAME='summary_evidence' OR (to_jsonb(NEW)-'result') IS DISTINCT FROM (to_jsonb(OLD)-'result') OR OLD.result IS NOT NULL
 THEN RAISE EXCEPTION 'SUMMARY_BINDING_IMMUTABLE' USING ERRCODE='23514';END IF;
 RETURN NEW;
END;$body$;
ALTER FUNCTION portal.summary_binding_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.summary_binding_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER summary_binding_immutable BEFORE UPDATE ON portal.summary_requests FOR EACH ROW EXECUTE FUNCTION portal.summary_binding_immutable();
CREATE TRIGGER summary_binding_immutable BEFORE UPDATE ON portal.summary_evidence FOR EACH ROW EXECUTE FUNCTION portal.summary_binding_immutable();
CREATE OR REPLACE FUNCTION portal.run_binding_immutable() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog AS $body$
BEGIN
 IF (NEW.tenant_id,NEW.run_id,NEW.conversation_id,NEW.owner_user_id,NEW.client_send_id,NEW.request_hash,
     NEW.agent_key,NEW.config_snapshot,NEW.origin_session_id,NEW.execution_mode,NEW.created_at,NEW.task_kind)
 IS DISTINCT FROM (OLD.tenant_id,OLD.run_id,OLD.conversation_id,OLD.owner_user_id,OLD.client_send_id,OLD.request_hash,
     OLD.agent_key,OLD.config_snapshot,OLD.origin_session_id,OLD.execution_mode,OLD.created_at,OLD.task_kind)
 THEN RAISE EXCEPTION 'RUN_BINDING_IMMUTABLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
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
 IF NOT COALESCE(v_agent.enabled,false) THEN RAISE EXCEPTION 'AGENT_DISABLED' USING ERRCODE='B0402'; END IF;
 IF p_config AND v_agent.config_version IS DISTINCT FROM (v_run.config_snapshot->>'config_version')::bigint
 THEN RAISE EXCEPTION 'CONFIG_CHANGED' USING ERRCODE='B0403'; END IF;
 IF v_run.task_kind='document_summary' THEN PERFORM security.summary_source_guard(p_session,p_tenant,p_run);END IF;
 PERFORM security.execution_scope(p_tenant);
END; $body$;
CREATE OR REPLACE FUNCTION security.rag_call_reserve(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_period date,p_input bytea,p_operation text,p_sources jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
 v_reservation numeric:=CASE WHEN p_operation='embed_query' THEN 0.20 ELSE 3.64 END;v_step text:=CASE WHEN p_operation='embed_query' THEN 'query_embedding' ELSE 'generation' END;v_call uuid;v_price jsonb:='{"embedding_model":"text-embedding-3-small","embedding_usd_per_million":"0.02","generation_model":"gpt-4o-mini","input_usd_per_million":"0.15","krw_per_usd":"2000","output_usd_per_million":"0.60","protection_factor":"1.2","quantum_krw":"0.01","version":"price-20261004-v1"}';
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 IF p_operation IS NULL OR p_operation NOT IN ('embed_query','generate_rag') THEN RAISE EXCEPTION 'OPERATION_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.rag_sources_guard(p_session,p_tenant,(SELECT execution_mode FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run),p_sources);
 IF p_input IS NULL OR octet_length(p_input)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF v_run.task_kind='document_summary' THEN RAISE EXCEPTION 'SUMMARY_CAPABILITY_REQUIRED' USING ERRCODE='A0422';END IF;
 IF v_run.agent_key<>'rules_rag' THEN RAISE EXCEPTION 'OPERATION_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO v_project FROM ops.project_budget WHERE budget_id=v_run.execution_budget_id AND period=p_period AND mode=v_run.execution_mode FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF v_run.state<>'running' OR v_run.worker_claim_hash IS DISTINCT FROM p_worker OR v_run.execution_epoch<>p_epoch
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 SELECT call_id INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run AND operation=p_operation;
 IF FOUND THEN RETURN jsonb_build_object('call_id',v_call,'created',false); END IF;
 IF v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (v_run.execution_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09'))
 THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF v_project.accounted_krw+v_project.reserved_krw+v_reservation>v_project.operational_cap_krw
 OR v_tenant.accounted_krw+v_tenant.reserved_krw+v_reservation>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw)
 THEN RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0430'; END IF;
 IF v_project.active_slot>=2 OR v_tenant.active_slot>=1 THEN RAISE EXCEPTION 'CAPACITY_BUSY' USING ERRCODE='B0431'; END IF;
 v_call:=gen_random_uuid();
 INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,initiator_user_id,operation,budget_id,mode,agent_key,
 config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,execution_epoch,reserved_krw,price_snapshot,input_sources)
 VALUES(p_tenant,v_call,p_run,v_run.owner_user_id,p_operation,v_project.budget_id,v_run.execution_mode,'rules_rag',
 (v_run.config_snapshot->>'config_version')::bigint,v_step,p_input,v_run.revision,clock_timestamp()+interval '10 seconds',p_epoch,v_reservation,v_price,p_sources);
 INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot)
 VALUES(p_tenant,gen_random_uuid(),v_call,'reserve',v_reservation,0,v_price);
 UPDATE ops.project_budget SET reserved_krw=reserved_krw+v_reservation,active_slot=active_slot+1,revision=revision+1 WHERE budget_id=v_project.budget_id;
 UPDATE ops.tenant_budgets SET reserved_krw=reserved_krw+v_reservation,active_slot=active_slot+1,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 RETURN jsonb_build_object('call_id',v_call,'created',true);
END; $body$;
CREATE OR REPLACE FUNCTION security.summary_call_reserve(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_period date,p_input bytea,p_operation text,p_sources jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
 v_reservation numeric:=CASE WHEN p_operation='embed_query' THEN 0.20 ELSE 3.64 END;v_step text:=CASE WHEN p_operation='embed_query' THEN 'query_embedding' ELSE 'generation' END;v_call uuid;v_price jsonb:='{"embedding_model":"text-embedding-3-small","embedding_usd_per_million":"0.02","generation_model":"gpt-4o-mini","input_usd_per_million":"0.15","krw_per_usd":"2000","output_usd_per_million":"0.60","protection_factor":"1.2","quantum_krw":"0.01","version":"price-20261004-v1"}';
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 IF p_operation IS NULL OR p_operation NOT IN ('embed_query','generate_rag') THEN RAISE EXCEPTION 'OPERATION_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.rag_sources_guard(p_session,p_tenant,(SELECT execution_mode FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run),p_sources);
 IF p_input IS NULL OR octet_length(p_input)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF v_run.task_kind<>'document_summary' OR p_operation<>'generate_rag' OR p_sources IS DISTINCT FROM security.summary_source_guard(p_session,p_tenant,p_run) THEN RAISE EXCEPTION 'OPERATION_REJECTED' USING ERRCODE='A0422';END IF;
 IF v_run.agent_key<>'rules_rag' THEN RAISE EXCEPTION 'OPERATION_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO v_project FROM ops.project_budget WHERE budget_id=v_run.execution_budget_id AND period=p_period AND mode=v_run.execution_mode FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF v_run.state<>'running' OR v_run.worker_claim_hash IS DISTINCT FROM p_worker OR v_run.execution_epoch<>p_epoch
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 SELECT call_id INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run AND operation=p_operation;
 IF FOUND THEN RETURN jsonb_build_object('call_id',v_call,'created',false); END IF;
 IF v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (v_run.execution_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09'))
 THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF v_project.accounted_krw+v_project.reserved_krw+v_reservation>v_project.operational_cap_krw
 OR v_tenant.accounted_krw+v_tenant.reserved_krw+v_reservation>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw)
 THEN RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0430'; END IF;
 IF v_project.active_slot>=2 OR v_tenant.active_slot>=1 THEN RAISE EXCEPTION 'CAPACITY_BUSY' USING ERRCODE='B0431'; END IF;
 v_call:=gen_random_uuid();
 INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,initiator_user_id,operation,budget_id,mode,agent_key,
 config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,execution_epoch,reserved_krw,price_snapshot,input_sources)
 VALUES(p_tenant,v_call,p_run,v_run.owner_user_id,p_operation,v_project.budget_id,v_run.execution_mode,'rules_rag',
 (v_run.config_snapshot->>'config_version')::bigint,v_step,p_input,v_run.revision,clock_timestamp()+interval '10 seconds',p_epoch,v_reservation,v_price,p_sources);
 INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot)
 VALUES(p_tenant,gen_random_uuid(),v_call,'reserve',v_reservation,0,v_price);
 UPDATE ops.project_budget SET reserved_krw=reserved_krw+v_reservation,active_slot=active_slot+1,revision=revision+1 WHERE budget_id=v_project.budget_id;
 UPDATE ops.tenant_budgets SET reserved_krw=reserved_krw+v_reservation,active_slot=active_slot+1,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 RETURN jsonb_build_object('call_id',v_call,'created',true);
END; $body$;
CREATE OR REPLACE FUNCTION security.rag_finish(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_body text,p_kind text,p_evidence jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;seq bigint;e jsonb;n integer:=0;source uuid;doc uuid;ver uuid;idx uuid;ev uuid;rel uuid;proof record;
BEGIN
 IF p_body IS NULL OR btrim(p_body)='' OR octet_length(p_body)>65536 OR p_kind IS NULL OR p_kind NOT IN ('answer','insufficient_evidence') OR p_evidence IS NULL OR jsonb_typeof(p_evidence)<>'array' OR jsonb_array_length(p_evidence)>20 OR (p_kind='answer') IS DISTINCT FROM (jsonb_array_length(p_evidence)>0) THEN RAISE EXCEPTION 'ANSWER_EVIDENCE_INVALID' USING ERRCODE='A0422';END IF;
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF r.task_kind<>'chat' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF r.agent_key<>'rules_rag' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 FOR e IN SELECT value FROM jsonb_array_elements(p_evidence) LOOP
  source:=(e->>'source_tenant_id')::uuid;doc:=(e->>'document_id')::uuid;ver:=(e->>'version_id')::uuid;idx:=(e->>'index_id')::uuid;ev:=(e->>'evidence_id')::uuid;rel:=(e->>'relation_id')::uuid;
  PERFORM security.rag_sources_guard(p_session,p_tenant,r.execution_mode,jsonb_build_array(jsonb_build_object('source_tenant_id',source,'document_id',doc,'version_id',ver,'index_id',idx)));
  SELECT source_sha256,quote_sha256,start_offset,end_offset,line_start,line_end INTO proof FROM rag.evidence WHERE (tenant_id,document_id,version_id,index_id,evidence_id)=(source,doc,ver,idx,ev) AND NOT payload_purged;
  IF NOT FOUND OR proof.quote_sha256 IS DISTINCT FROM security.quote_digest(e->>'quote') OR encode(proof.source_sha256,'hex') IS DISTINCT FROM e->>'source_sha256' OR e->'location' IS DISTINCT FROM jsonb_build_object('start_offset',proof.start_offset,'end_offset',proof.end_offset,'line_start',proof.line_start,'line_end',proof.line_end) OR NOT EXISTS(SELECT 1 FROM rag.relation_evidence WHERE tenant_id=source AND index_id=idx AND evidence_id=ev AND relation_id=rel) THEN RAISE EXCEPTION 'ANSWER_EVIDENCE_INVALID' USING ERRCODE='A0422';END IF;
 END LOOP;
 IF p_kind='answer' AND NOT EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run AND operation='generate_rag' AND (state='settled' OR (state='usage_unknown' AND provider_end_status='observed')) AND NOT slot_held AND NOT cost_overrun) THEN RAISE EXCEPTION 'CALL_UNSETTLED' USING ERRCODE='B0401';END IF;
 IF NOT security.execution_heartbeat(p_session,p_tenant,p_run,p_epoch,p_worker) THEN RETURN false;END IF;
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 PERFORM conversation_id FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id FOR UPDATE;
 PERFORM set_config('app.rag_finalize',p_run::text,true);
 FOR e IN SELECT value FROM jsonb_array_elements(p_evidence) LOOP
  INSERT INTO portal.answer_evidence(tenant_id,run_id,ordinal,source_tenant_id,document_id,version_id,index_id,evidence_id,source_sha256,location_snapshot,quote_snapshot,relation_id) VALUES(p_tenant,p_run,n,(e->>'source_tenant_id')::uuid,(e->>'document_id')::uuid,(e->>'version_id')::uuid,(e->>'index_id')::uuid,(e->>'evidence_id')::uuid,decode(e->>'source_sha256','hex'),e->'location',e->>'quote',(e->>'relation_id')::uuid);n:=n+1;
 END LOOP;
 PERFORM set_config('app.run_scope','sequence',true);
 SELECT coalesce(max(sequence_no),0)+1 INTO seq FROM portal.messages WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id;
 PERFORM set_config('app.run_scope','owner',true);
 INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind) VALUES(p_tenant,gen_random_uuid(),r.conversation_id,r.owner_user_id,'rules_rag',seq,'assistant',p_body,p_run,'rag_assistant');
 UPDATE portal.runs SET state='completed',stage='terminal',revision=revision+1,answer_kind=p_kind,source_count=n,provenance_sealed=true,ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_run;
 UPDATE portal.conversations SET updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id;
 RETURN true;
END;$body$;
CREATE OR REPLACE FUNCTION security.execution_finish(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_body text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_sequence bigint;
BEGIN
 IF p_body IS NULL OR btrim(p_body)='' OR octet_length(p_body)>65536
 THEN RAISE EXCEPTION 'RESULT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.run_authorize(p_session,p_tenant,true);
 IF EXISTS(SELECT 1 FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run AND task_kind<>'chat') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF v_run.state='completed' THEN
  RETURN v_run.origin_session_id=p_session AND v_run.execution_epoch=p_epoch AND p_worker IS NOT NULL
  AND v_run.worker_claim_hash=p_worker AND EXISTS(SELECT 1 FROM portal.messages m WHERE m.tenant_id=p_tenant
   AND m.run_id=p_run AND m.role='assistant' AND NOT m.payload_purged AND m.body=p_body);
 END IF;
 IF NOT security.execution_heartbeat(p_session,p_tenant,p_run,p_epoch,p_worker) THEN RETURN false; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF v_run.state<>'running' THEN RETURN false; END IF;
 PERFORM conversation_id FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id FOR UPDATE;
 PERFORM set_config('app.run_scope','sequence',true);
 SELECT COALESCE(max(sequence_no),0)+1 INTO v_sequence FROM portal.messages WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id;
 PERFORM set_config('app.run_scope','owner',true);
 INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind)
 VALUES(p_tenant,gen_random_uuid(),v_run.conversation_id,v_run.owner_user_id,'general',v_sequence,'assistant',p_body,p_run,'general_assistant');
 UPDATE portal.runs SET state='completed',stage='terminal',revision=revision+1,answer_kind='answer',ended_at=clock_timestamp()
 WHERE tenant_id=p_tenant AND run_id=p_run;
 UPDATE portal.conversations SET updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id;
 RETURN true;
END; $body$;
CREATE OR REPLACE FUNCTION security.can_read_rag_answer_payload(p_tenant uuid,p_run uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' THEN RETURN false;END IF;
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND OR NOT security.can_read_own_conversation(p_tenant,r.owner_user_id) THEN RETURN false;END IF;
 IF NOT EXISTS(SELECT 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id AND deleted_at IS NULL) THEN RETURN false; END IF;
 IF r.task_kind<>'chat' THEN RETURN false;END IF;
 IF r.agent_key='general' THEN RETURN true;END IF;
 IF r.state<>'completed' OR NOT r.provenance_sealed OR NOT EXISTS(SELECT 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' AND enabled) THEN RETURN false;END IF;
 IF (SELECT count(*) FROM portal.answer_evidence WHERE tenant_id=p_tenant AND run_id=p_run)<>r.source_count THEN RETURN false;END IF;
 RETURN NOT EXISTS(SELECT 1 FROM portal.answer_evidence e WHERE e.tenant_id=p_tenant AND e.run_id=p_run AND (e.payload_purged OR NOT security.document_can_read(e.source_tenant_id,e.document_id,e.version_id,e.index_id) OR NOT EXISTS(SELECT 1 FROM rag.document_versions v WHERE (v.tenant_id,v.document_id,v.version_id,v.source_sha256)=(e.source_tenant_id,e.document_id,e.version_id,e.source_sha256) AND NOT v.payload_purged)));
END;$body$;
CREATE FUNCTION security.summary_admit(p_session uuid,p_tenant uuid,p_send uuid,p_hash bytea,p_period date,p_mode text,
 p_digest bytea,p_request uuid,p_source uuid,p_document uuid,p_source_version uuid,p_index uuid,p_sha bytea,p_bullets integer,p_tokens integer,p_candidates jsonb,p_parent uuid,p_expected bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_ready jsonb;v_run uuid;v_conversation uuid;v_sequence bigint;v_snapshot jsonb;
 v_count_user integer;v_count_tenant integer;v_count_project integer;v_start timestamptz;v_count integer;v_now timestamptz;p_agent text:='rules_rag';p_conversation uuid:=NULL;p_prompt text:='문서 요약';p_version bigint;p_selected uuid[]:='{}';v_parent portal.runs%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
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

CREATE FUNCTION security.summary_source_guard(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE q portal.summary_requests%ROWTYPE;r portal.runs%ROWTYPE;src jsonb;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 SELECT * INTO q FROM portal.summary_requests WHERE tenant_id=p_tenant AND run_id=p_run;
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF q.run_id IS NULL OR r.run_id IS NULL OR r.task_kind<>'document_summary' OR NOT EXISTS(SELECT 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id AND deleted_at IS NULL) OR NOT security.can_read_own_conversation(p_tenant,q.owner_user_id)
 OR NOT EXISTS(SELECT 1 FROM rag.document_versions WHERE (tenant_id,document_id,version_id,source_sha256)=(q.source_tenant_id,q.document_id,q.version_id,q.source_sha256) AND NOT payload_purged)
 THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404';END IF;
 src:=jsonb_build_array(jsonb_build_object('source_tenant_id',q.source_tenant_id,'document_id',q.document_id,'version_id',q.version_id,'index_id',q.index_id));
 PERFORM security.rag_sources_guard(p_session,p_tenant,r.execution_mode,src);
 RETURN src;
END;$body$;
CREATE FUNCTION security.summary_request(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE q portal.summary_requests%ROWTYPE;
BEGIN
 PERFORM security.summary_source_guard(p_session,p_tenant,p_run);
 SELECT * INTO q FROM portal.summary_requests WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN jsonb_build_object('document_ref',jsonb_build_object('document_id',q.document_id,'version_id',q.version_id),'bullet_count',q.bullet_count,'parent_run_id',q.parent_run_id,'candidates',q.candidates);
END;$body$;
CREATE FUNCTION security.summary_read(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE q portal.summary_requests%ROWTYPE;r portal.runs%ROWTYPE;v jsonb;
BEGIN
 PERFORM security.summary_source_guard(p_session,p_tenant,p_run);
 SELECT * INTO q FROM portal.summary_requests WHERE tenant_id=p_tenant AND run_id=p_run;
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 v:=security.run_view(p_tenant,p_run);
 IF r.state='completed' AND r.provenance_sealed AND q.result IS NOT NULL
 AND EXISTS(SELECT 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' AND enabled)
 AND (SELECT count(*) FROM portal.summary_evidence WHERE tenant_id=p_tenant AND run_id=p_run)=r.source_count THEN
  v:=v||jsonb_build_object('content_status','final','result',jsonb_build_object('text',q.result));
 END IF;
 RETURN v||jsonb_build_object('task_kind','document_summary','bullet_count',q.bullet_count,'parent_run_id',q.parent_run_id,'evidence','[]'::jsonb);
END;$body$;
CREATE FUNCTION security.summary_finish(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_body text,p_kind text,p_evidence jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;q portal.summary_requests%ROWTYPE;e jsonb;proof record;n integer:=0;rendered text:='';last_offset bigint:=-1;
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 PERFORM security.summary_source_guard(p_session,p_tenant,p_run);
 SELECT * INTO q FROM portal.summary_requests WHERE tenant_id=p_tenant AND run_id=p_run;
 IF p_kind IS NULL OR p_kind NOT IN ('answer','insufficient_evidence') OR p_evidence IS NULL OR jsonb_typeof(p_evidence)<>'array' OR jsonb_array_length(p_evidence)>q.bullet_count OR (p_kind='answer') IS DISTINCT FROM (jsonb_array_length(p_evidence)>0) THEN RAISE EXCEPTION 'SUMMARY_OUTPUT_INVALID' USING ERRCODE='A0422';END IF;
 FOR e IN SELECT value FROM jsonb_array_elements(p_evidence) LOOP
  IF jsonb_typeof(e)<>'object' OR e-ARRAY['source_tenant_id','document_id','version_id','index_id','candidate_id','evidence_id','source_sha256','quote','location']::text[]<>'{}'::jsonb
  OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(q.candidates) c WHERE c=e-'quote')
  OR (e->>'source_tenant_id',e->>'document_id',e->>'version_id',e->>'index_id',e->>'source_sha256') IS DISTINCT FROM (q.source_tenant_id::text,q.document_id::text,q.version_id::text,q.index_id::text,encode(q.source_sha256,'hex')) THEN RAISE EXCEPTION 'SUMMARY_OUTPUT_INVALID' USING ERRCODE='A0422';END IF;
  SELECT source_sha256,quote_sha256,start_offset,end_offset,line_start,line_end INTO proof FROM rag.evidence WHERE (tenant_id,document_id,version_id,index_id,evidence_id)=(q.source_tenant_id,q.document_id,q.version_id,q.index_id,(e->>'evidence_id')::uuid) AND NOT payload_purged;
  IF NOT FOUND OR proof.quote_sha256 IS DISTINCT FROM security.quote_digest(e->>'quote') OR proof.source_sha256 IS DISTINCT FROM q.source_sha256 OR proof.start_offset<=last_offset OR e->'location' IS DISTINCT FROM jsonb_build_object('start_offset',proof.start_offset,'end_offset',proof.end_offset,'line_start',proof.line_start,'line_end',proof.line_end) THEN RAISE EXCEPTION 'SUMMARY_OUTPUT_INVALID' USING ERRCODE='A0422';END IF;
  last_offset:=proof.start_offset;n:=n+1;rendered:=rendered||CASE WHEN n>1 THEN E'\n' ELSE '' END||n::text||'. '||(e->>'quote');
 END LOOP;
 IF n=0 THEN rendered:='허용된 원문에서 요약할 충분한 근거가 없습니다.';END IF;
 IF p_body IS DISTINCT FROM rendered OR octet_length(p_body)>65536 THEN RAISE EXCEPTION 'SUMMARY_OUTPUT_INVALID' USING ERRCODE='A0422';END IF;
 IF n>0 AND NOT EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run AND operation='generate_rag' AND (state='settled' OR (state='usage_unknown' AND provider_end_status='observed')) AND NOT slot_held AND NOT cost_overrun) THEN RAISE EXCEPTION 'CALL_UNSETTLED' USING ERRCODE='B0401';END IF;
 IF NOT security.execution_heartbeat(p_session,p_tenant,p_run,p_epoch,p_worker) THEN RETURN false;END IF;
 PERFORM security.summary_source_guard(p_session,p_tenant,p_run);
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 PERFORM set_config('app.summary_finalize',p_run::text,true);n:=0;
 FOR e IN SELECT value FROM jsonb_array_elements(p_evidence) LOOP
  INSERT INTO portal.summary_evidence(tenant_id,run_id,ordinal,source_tenant_id,document_id,version_id,index_id,evidence_id,source_sha256,location_snapshot,quote_snapshot,candidate_id)
  VALUES(p_tenant,p_run,n,q.source_tenant_id,q.document_id,q.version_id,q.index_id,(e->>'evidence_id')::uuid,q.source_sha256,e->'location',e->>'quote',e->>'candidate_id');n:=n+1;
 END LOOP;
 UPDATE portal.summary_requests SET result=p_body WHERE tenant_id=p_tenant AND run_id=p_run;
 UPDATE portal.runs SET state='completed',stage='terminal',revision=revision+1,answer_kind=p_kind,source_count=n,provenance_sealed=true,ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_run;
 UPDATE portal.conversations SET updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id;
 RETURN true;
END;$body$;
ALTER FUNCTION security.summary_claim(uuid,uuid,uuid,text,date,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_claim(uuid,uuid,uuid,text,date,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_claim(uuid,uuid,uuid,text,date,bytea) TO ai_web;
ALTER FUNCTION security.summary_call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea,text,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea,text,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea,text,jsonb) TO ai_web;
ALTER FUNCTION security.summary_admit(uuid,uuid,uuid,bytea,date,text,bytea,uuid,uuid,uuid,uuid,uuid,bytea,integer,integer,jsonb,uuid,bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_admit(uuid,uuid,uuid,bytea,date,text,bytea,uuid,uuid,uuid,uuid,uuid,bytea,integer,integer,jsonb,uuid,bigint) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_admit(uuid,uuid,uuid,bytea,date,text,bytea,uuid,uuid,uuid,uuid,uuid,bytea,integer,integer,jsonb,uuid,bigint) TO ai_web;
ALTER FUNCTION security.summary_source_guard(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_source_guard(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_source_guard(uuid,uuid,uuid) TO ai_web;
ALTER FUNCTION security.summary_request(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_request(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_request(uuid,uuid,uuid) TO ai_web;
ALTER FUNCTION security.summary_read(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_read(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_read(uuid,uuid,uuid) TO ai_web;
ALTER FUNCTION security.summary_finish(uuid,uuid,uuid,bigint,bytea,text,text,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_finish(uuid,uuid,uuid,bigint,bytea,text,text,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_finish(uuid,uuid,uuid,bigint,bytea,text,text,jsonb) TO ai_web;

GRANT SELECT(task_kind) ON portal.runs TO ai_web;

CREATE OR REPLACE FUNCTION security.feedback_target(p_session uuid,p_tenant uuid,p_run uuid,p_lock boolean) RETURNS portal.runs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_run portal.runs%ROWTYPE;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,p_lock);
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run AND owner_user_id=v_user;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF p_lock THEN
  PERFORM 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id AND deleted_at IS NULL FOR UPDATE;
 ELSE
  PERFORM 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id AND deleted_at IS NULL;
 END IF;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF v_run.state<>'completed' OR v_run.answer_kind IS DISTINCT FROM 'answer'
 OR NOT security.can_read_rag_answer_payload(p_tenant,p_run)
 OR NOT EXISTS(SELECT 1 FROM portal.messages WHERE tenant_id=p_tenant AND run_id=p_run AND role='assistant' AND NOT payload_purged) THEN
  RAISE EXCEPTION 'FEEDBACK_NOT_READY' USING ERRCODE='B0412'; END IF;
 RETURN v_run;
END; $body$;

CREATE FUNCTION security.summary_replay(p_session uuid,p_tenant uuid,p_send uuid,p_hash bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=p_send;
 IF NOT FOUND THEN RETURN NULL;END IF;
 IF r.task_kind<>'document_summary' OR r.request_hash IS DISTINCT FROM p_hash THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301';END IF;
 PERFORM security.summary_source_guard(p_session,p_tenant,r.run_id);
 RETURN security.run_view(p_tenant,r.run_id)||jsonb_build_object('replayed',true);
END;$body$;
ALTER FUNCTION security.summary_replay(uuid,uuid,uuid,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.summary_replay(uuid,uuid,uuid,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.summary_replay(uuid,uuid,uuid,bytea) TO ai_web;

CREATE OR REPLACE FUNCTION security.execution_fail(p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_code text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_code IS NULL OR p_code NOT IN ('EXECUTION_BLOCKED','CAPACITY_BUSY','QUOTA_EXCEEDED','AGENT_DISABLED','CONFIG_CHANGED','PERMIT_EXPIRED',
 'PROJECT_STOPPED','PROVIDER_TIMEOUT','PROVIDER_ERROR','STREAM_INTERRUPTED','EMPTY_RESPONSE','OUTPUT_TRUNCATED','RESPONSE_BLOCKED','USAGE_INVALID',
 'LEDGER_CONFLICT','LEDGER_UNAVAILABLE','RESULT_SAVE_FAILED','RUN_TIMEOUT','EXECUTION_INTERRUPTED','SEARCH_FAILED','ANSWER_EVIDENCE_INVALID','SEARCH_LIMIT_EXCEEDED','TOKEN_LIMIT_EXCEEDED','FEATURE_NOT_READY','SUMMARY_OUTPUT_INVALID','SUMMARY_LIMIT_EXCEEDED','STORAGE_UNAVAILABLE','DOCUMENT_POLICY_BLOCKED','DOCUMENT_POLICY_UNAVAILABLE')
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF p_worker IS NULL OR v_run.worker_claim_hash IS DISTINCT FROM p_worker OR v_run.execution_epoch IS DISTINCT FROM p_epoch
 OR v_run.state NOT IN ('running','cancel_requested') THEN RETURN false; END IF;
 UPDATE portal.runs SET state=CASE WHEN state='cancel_requested' THEN 'cancelled' ELSE 'failed' END,
 stage='terminal',revision=revision+1,safe_error_code=CASE WHEN state='cancel_requested' THEN NULL ELSE p_code END,ended_at=clock_timestamp()
 WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN true;
END; $body$;
