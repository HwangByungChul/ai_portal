-- C04 RAG contracts preserve general runs and extend the same central ledger.
DO $fix$ DECLARE c record;BEGIN
 FOR c IN SELECT conrelid::regclass AS tbl,conname FROM pg_constraint WHERE contype='c' AND ((conrelid='portal.runs'::regclass AND (pg_get_constraintdef(oid) LIKE '%agent_key%' OR pg_get_constraintdef(oid) LIKE '%source_count%' OR pg_get_constraintdef(oid) LIKE '%provenance_sealed%' OR pg_get_constraintdef(oid) LIKE '%answer_kind%')) OR (conrelid='portal.messages'::regclass AND (pg_get_constraintdef(oid) LIKE '%agent_key%' OR pg_get_constraintdef(oid) LIKE '%payload_kind%'))) LOOP
 EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',c.tbl,c.conname);END LOOP;
END;$fix$;
ALTER TABLE portal.runs ADD CONSTRAINT runs_agent_typed CHECK(agent_key IN ('general','rules_rag'));
ALTER TABLE portal.runs ADD CONSTRAINT runs_answer_typed CHECK(answer_kind IS NULL OR (state='completed' AND answer_kind IN ('answer','insufficient_evidence')));
ALTER TABLE portal.runs ADD CONSTRAINT runs_completed_typed CHECK(state<>'completed' OR answer_kind IS NOT NULL);
ALTER TABLE portal.runs ADD CONSTRAINT runs_source_typed CHECK((agent_key='general' AND source_count=0 AND NOT provenance_sealed) OR (agent_key='rules_rag' AND source_count BETWEEN 0 AND 20 AND (state<>'completed' OR provenance_sealed) AND (answer_kind IS DISTINCT FROM 'answer' OR source_count>0)));
ALTER TABLE portal.messages ADD CONSTRAINT messages_agent_typed CHECK(agent_key IN ('general','rules_rag'));
ALTER TABLE portal.messages ADD CONSTRAINT messages_payload_typed CHECK((role='user' AND payload_kind='user') OR (role='assistant' AND ((agent_key='general' AND payload_kind='general_assistant') OR (agent_key='rules_rag' AND payload_kind='rag_assistant'))));
ALTER TABLE ops.call_attempts ADD COLUMN input_sources jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(input_sources)='array' AND jsonb_array_length(input_sources)<=128);
ALTER TABLE ops.call_attempts DROP CONSTRAINT call_parent_kind;
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_parent_kind CHECK(
 (run_id IS NOT NULL AND job_id IS NULL AND index_id IS NULL AND batch_ordinal IS NULL AND ((operation='generate_general' AND agent_key='general' AND step_key='generation' AND input_sources='[]'::jsonb) OR (agent_key='rules_rag' AND ((operation='embed_query' AND step_key='query_embedding') OR (operation='generate_rag' AND step_key='generation'))))) OR
 (run_id IS NULL AND job_id IS NOT NULL AND index_id IS NOT NULL AND batch_ordinal IS NOT NULL AND operation='embed_document' AND agent_key='rules_rag' AND step_key='batch-'||batch_ordinal::text AND input_sources='[]'::jsonb));
DROP INDEX IF EXISTS ops.calls_run_generation;
-- The previous run step index must admit exactly one query and one generation.
DO $idx$ DECLARE q record;BEGIN
 FOR q IN SELECT indexname FROM pg_indexes WHERE schemaname='ops' AND tablename='call_attempts' AND indexdef LIKE '%UNIQUE%' AND indexdef LIKE '%run_id%' AND indexdef NOT LIKE '%step_key%' AND indexname NOT LIKE '%pkey%' LOOP EXECUTE format('DROP INDEX ops.%I',q.indexname);END LOOP;
END;$idx$;
CREATE UNIQUE INDEX calls_run_step ON ops.call_attempts(tenant_id,run_id,step_key) WHERE run_id IS NOT NULL AND state<>'released_no_dispatch';
ALTER TABLE ops.call_attempts DROP CONSTRAINT call_usage_typed;
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_usage_typed CHECK(usage_snapshot IS NULL OR
 (jsonb_typeof(usage_snapshot)='object' AND usage_snapshot - ARRAY['input_tokens','output_tokens','total_tokens','observed_model','observed_tier','provider_request_id']::text[]='{}'::jsonb
 AND ops.valid_token_counts(usage_snapshot - ARRAY['observed_model','observed_tier','provider_request_id']::text[])
 AND usage_snapshot->>'observed_tier'='default'
 AND ((operation IN ('generate_general','generate_rag') AND usage_snapshot->>'observed_model' IN ('gpt-4o-mini','gpt-4o-mini-2024-07-18')) OR (operation IN ('embed_document','embed_query') AND usage_snapshot->>'observed_model'='text-embedding-3-small' AND usage_snapshot->>'output_tokens'='0'))
 AND (usage_snapshot->'provider_request_id'='null'::jsonb OR (jsonb_typeof(usage_snapshot->'provider_request_id')='string' AND usage_snapshot->>'provider_request_id' ~ '^[!-~]{1,255}[!-~]?$'))));


CREATE OR REPLACE FUNCTION security.conversation_create(p_session uuid,p_tenant uuid,p_agent text,p_client uuid,p_request uuid)
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
  PERFORM conversation_id FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=p_conversation FOR UPDATE;
 END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('message_id',q.message_id,'role',q.role,'content',q.body) ORDER BY q.sequence_no),'[]'::jsonb)
 INTO v_history FROM (SELECT m.message_id,m.role,m.body,m.sequence_no FROM portal.messages m
 WHERE m.tenant_id=p_tenant AND m.conversation_id=p_conversation ORDER BY m.sequence_no DESC LIMIT 6) q;
 RETURN jsonb_build_object('instructions',COALESCE(NULLIF(v_agent.settings->>'instructions',''),'사용자 질문에 간결하고 정확하게 답변하세요.'),
  'config_version',v_agent.config_version,'history',v_history);
END; $body$;

CREATE OR REPLACE FUNCTION security.run_admit(p_session uuid,p_tenant uuid,p_agent text,p_conversation uuid,p_send uuid,p_hash bytea,
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
  'instructions',v_ready->>'instructions','selected_history_ids',to_jsonb(p_selected),'estimated_input_tokens',p_tokens,'document_refs',CASE WHEN p_agent='rules_rag' THEN coalesce(nullif(current_setting('app.rag_refs',true),'')::jsonb,'[]'::jsonb) ELSE '[]'::jsonb END) INTO v_snapshot
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
 PERFORM security.execution_scope(p_tenant);
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

CREATE OR REPLACE FUNCTION security.call_reserve(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_period date,p_input bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
 v_call uuid;v_price jsonb:='{"embedding_model":"text-embedding-3-small","embedding_usd_per_million":"0.02","generation_model":"gpt-4o-mini","input_usd_per_million":"0.15","krw_per_usd":"2000","output_usd_per_million":"0.60","protection_factor":"1.2","quantum_krw":"0.01","version":"price-20261004-v1"}';
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 IF p_input IS NULL OR octet_length(p_input)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF v_run.agent_key<>'general' THEN RAISE EXCEPTION 'OPERATION_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_project FROM ops.project_budget WHERE budget_id=v_run.execution_budget_id AND period=p_period AND mode=v_run.execution_mode FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF v_run.state<>'running' OR v_run.worker_claim_hash IS DISTINCT FROM p_worker OR v_run.execution_epoch<>p_epoch
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 SELECT call_id INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run;
 IF FOUND THEN RETURN jsonb_build_object('call_id',v_call,'created',false); END IF;
 IF v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (v_run.execution_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09'))
 THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF v_project.accounted_krw+v_project.reserved_krw+3.64>v_project.operational_cap_krw
 OR v_tenant.accounted_krw+v_tenant.reserved_krw+3.64>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw)
 THEN RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0430'; END IF;
 IF v_project.active_slot>=2 OR v_tenant.active_slot>=1 THEN RAISE EXCEPTION 'CAPACITY_BUSY' USING ERRCODE='B0431'; END IF;
 v_call:=gen_random_uuid();
 INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,initiator_user_id,operation,budget_id,mode,agent_key,
 config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,execution_epoch,reserved_krw,price_snapshot)
 VALUES(p_tenant,v_call,p_run,v_run.owner_user_id,'generate_general',v_project.budget_id,v_run.execution_mode,'general',
 (v_run.config_snapshot->>'config_version')::bigint,'generation',p_input,v_run.revision,clock_timestamp()+interval '10 seconds',p_epoch,3.64,v_price);
 INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot)
 VALUES(p_tenant,gen_random_uuid(),v_call,'reserve',3.64,0,v_price);
 UPDATE ops.project_budget SET reserved_krw=reserved_krw+3.64,active_slot=active_slot+1,revision=revision+1 WHERE budget_id=v_project.budget_id;
 UPDATE ops.tenant_budgets SET reserved_krw=reserved_krw+3.64,active_slot=active_slot+1,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 RETURN jsonb_build_object('call_id',v_call,'created',true);
END; $body$;

CREATE OR REPLACE FUNCTION security.call_meter(p_tenant uuid,p_call uuid,p_epoch bigint,p_claim bytea,p_receipt jsonb,p_end text,p_invalid boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_call ops.call_attempts%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
 v_valid boolean;v_cost numeric;v_conflict boolean:=false;v_overrun boolean:=false;v_release_slot boolean:=false;
BEGIN
 IF session_user<>'ai_meter' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_end IS NULL OR p_end NOT IN ('unknown','observed') OR p_invalid IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call;
 IF v_call.call_id IS NULL OR p_claim IS NULL OR octet_length(p_claim)<>32
 OR v_call.execution_epoch IS DISTINCT FROM p_epoch OR v_call.dispatch_claim_hash IS DISTINCT FROM p_claim
 OR v_call.state NOT IN ('dispatched','usage_unknown','settled') THEN RAISE EXCEPTION 'CLAIM_REJECTED' USING ERRCODE='B0410'; END IF;
 SELECT * INTO v_project FROM ops.project_budget WHERE budget_id=v_call.budget_id FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_call.budget_id FOR UPDATE;
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call FOR UPDATE;
 v_valid:=p_receipt IS NOT NULL AND jsonb_typeof(p_receipt)='object'
 AND p_receipt-ARRAY['input_tokens','output_tokens','total_tokens','observed_model','observed_tier','provider_request_id']::text[]='{}'::jsonb
 AND ops.valid_token_counts(p_receipt-ARRAY['observed_model','observed_tier','provider_request_id']::text[])
 AND ((v_call.operation IN ('generate_general','generate_rag') AND p_receipt->>'observed_model' IN ('gpt-4o-mini','gpt-4o-mini-2024-07-18')) OR (v_call.operation IN ('embed_document','embed_query') AND p_receipt->>'observed_model'='text-embedding-3-small' AND p_receipt->>'output_tokens'='0')) AND p_receipt->>'observed_tier'='default'
 AND (p_receipt->'provider_request_id'='null'::jsonb OR (jsonb_typeof(p_receipt->'provider_request_id')='string'
 AND p_receipt->>'provider_request_id' ~ '^[!-~]{1,255}[!-~]?$'));
 IF p_receipt IS NOT NULL AND NOT COALESCE(v_valid,false) THEN p_invalid:=true; END IF;
 IF v_call.state='settled' THEN
  v_conflict:=p_receipt IS NOT NULL AND v_call.usage_snapshot IS DISTINCT FROM p_receipt;
 ELSE
  IF COALESCE(v_valid,false) AND NOT p_invalid THEN
   v_cost:=ceil(((p_receipt->>'input_tokens')::numeric*CASE WHEN v_call.operation IN ('embed_document','embed_query') THEN 0.02 ELSE 0.15 END+(p_receipt->>'output_tokens')::numeric*0.60)*2000*1.2/1000000*100)/100;
   v_overrun:=v_cost>v_call.reserved_krw OR v_project.accounted_krw+v_project.reserved_krw-v_call.reserved_krw+v_cost>v_project.operational_cap_krw
    OR v_tenant.accounted_krw+v_tenant.reserved_krw-v_call.reserved_krw+v_cost>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw);
   UPDATE ops.project_budget SET reserved_krw=reserved_krw-v_call.reserved_krw,accounted_krw=accounted_krw+v_cost,revision=revision+1 WHERE budget_id=v_call.budget_id;
   UPDATE ops.tenant_budgets SET reserved_krw=reserved_krw-v_call.reserved_krw,accounted_krw=accounted_krw+v_cost,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=v_call.budget_id;
   INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,token_counts,price_snapshot)
   VALUES(p_tenant,gen_random_uuid(),p_call,'settle',-v_call.reserved_krw,v_cost,
    p_receipt-ARRAY['observed_model','observed_tier','provider_request_id']::text[],v_call.price_snapshot);
   UPDATE ops.call_attempts SET state='settled',usage_snapshot=p_receipt,provider_request_id=p_receipt->>'provider_request_id',cost_overrun=v_overrun WHERE tenant_id=p_tenant AND call_id=p_call;
  ELSE
   INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot)
   VALUES(p_tenant,gen_random_uuid(),p_call,'mark_unknown',0,0,v_call.price_snapshot) ON CONFLICT(tenant_id,call_id,event_kind) DO NOTHING;
   UPDATE ops.call_attempts SET state='usage_unknown' WHERE tenant_id=p_tenant AND call_id=p_call;
  END IF;
 END IF;
 -- A conflicting receipt cannot itself establish trustworthy remote termination.
 v_release_slot:=p_end='observed' AND v_call.slot_held AND NOT v_conflict;
 IF v_release_slot THEN
  UPDATE ops.project_budget SET active_slot=active_slot-1,revision=revision+1 WHERE budget_id=v_call.budget_id;
  UPDATE ops.tenant_budgets SET active_slot=active_slot-1,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=v_call.budget_id;
 END IF;
 UPDATE ops.call_attempts SET provider_end_status=CASE WHEN provider_end_status='observed' OR (p_end='observed' AND NOT v_conflict) THEN 'observed' ELSE 'unknown' END,
 slot_held=slot_held AND NOT v_release_slot WHERE tenant_id=p_tenant AND call_id=p_call;
 IF p_invalid OR v_conflict OR v_overrun THEN
  UPDATE ops.project_budget SET stop_latch=true,revision=revision+1 WHERE budget_id=v_call.budget_id;
 END IF;
 RETURN jsonb_build_object('state',(SELECT state FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call),
 'conflict',v_conflict,'invalid',p_invalid,'overrun',v_overrun);
END; $body$;

CREATE OR REPLACE FUNCTION ops.call_binding_immutable() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog AS $body$
BEGIN
 IF (NEW.tenant_id,NEW.call_id,NEW.run_id,NEW.job_id,NEW.index_id,NEW.batch_ordinal,NEW.initiator_user_id,NEW.operation,NEW.budget_id,NEW.mode,
     NEW.agent_key,NEW.config_revision,NEW.step_key,NEW.attempt_no,NEW.input_sources,NEW.input_fingerprint,NEW.permit_revision,
     NEW.permit_expires_at,NEW.execution_epoch,NEW.reserved_krw,NEW.price_snapshot,NEW.created_at)
 IS DISTINCT FROM (OLD.tenant_id,OLD.call_id,OLD.run_id,OLD.job_id,OLD.index_id,OLD.batch_ordinal,OLD.initiator_user_id,OLD.operation,OLD.budget_id,OLD.mode,
     OLD.agent_key,OLD.config_revision,OLD.step_key,OLD.attempt_no,OLD.input_sources,OLD.input_fingerprint,OLD.permit_revision,
     OLD.permit_expires_at,OLD.execution_epoch,OLD.reserved_krw,OLD.price_snapshot,OLD.created_at)
 THEN RAISE EXCEPTION 'CALL_BINDING_IMMUTABLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
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
ALTER FUNCTION security.rag_call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea,text,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.rag_call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea,text,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.rag_call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea,text,jsonb) TO ai_web;


CREATE OR REPLACE FUNCTION security.call_dispatch(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_call uuid,p_claim bytea)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_call ops.call_attempts%ROWTYPE;v_run portal.runs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 IF p_claim IS NULL OR octet_length(p_claim)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND run_id=p_run AND execution_epoch=p_epoch;
 IF NOT FOUND THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 IF v_call.operation IN ('embed_query','generate_rag') THEN PERFORM security.rag_sources_guard(p_session,p_tenant,v_call.mode,v_call.input_sources);END IF;
 SELECT * INTO v_project FROM ops.project_budget WHERE budget_id=v_call.budget_id FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_call.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call FOR UPDATE;
 IF v_call.state<>'reserved' THEN RETURN false; END IF;
 IF v_run.state<>'running' OR v_run.execution_epoch<>p_epoch OR v_run.worker_claim_hash IS DISTINCT FROM p_worker
 OR v_run.revision<>v_call.permit_revision OR clock_timestamp()>=v_call.permit_expires_at
 THEN RAISE EXCEPTION 'PERMIT_EXPIRED' USING ERRCODE='B0407'; END IF;
 IF v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (v_call.mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>v_project.period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09'))
 THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF v_project.accounted_krw+v_project.reserved_krw>v_project.operational_cap_krw
 OR v_tenant.accounted_krw+v_tenant.reserved_krw>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw)
 THEN RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0430'; END IF;
 UPDATE ops.call_attempts SET state='dispatched',dispatch_claim_hash=p_claim,dispatched_at=clock_timestamp(),provider_end_status='unknown'
 WHERE tenant_id=p_tenant AND call_id=p_call;
 RETURN true;
END; $body$;

CREATE OR REPLACE FUNCTION security.execution_fail(p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_code text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_code IS NULL OR p_code NOT IN ('EXECUTION_BLOCKED','CAPACITY_BUSY','QUOTA_EXCEEDED','AGENT_DISABLED','CONFIG_CHANGED','PERMIT_EXPIRED',
 'PROJECT_STOPPED','PROVIDER_TIMEOUT','PROVIDER_ERROR','STREAM_INTERRUPTED','EMPTY_RESPONSE','OUTPUT_TRUNCATED','RESPONSE_BLOCKED','USAGE_INVALID',
 'LEDGER_CONFLICT','LEDGER_UNAVAILABLE','RESULT_SAVE_FAILED','RUN_TIMEOUT','EXECUTION_INTERRUPTED','SEARCH_FAILED','ANSWER_EVIDENCE_INVALID','SEARCH_LIMIT_EXCEEDED','TOKEN_LIMIT_EXCEEDED','FEATURE_NOT_READY')
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
