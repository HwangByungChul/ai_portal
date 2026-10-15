-- DP11: private saved-version trials. No public draft activation or historical backfill.
ALTER TABLE portal.runs DROP CONSTRAINT runs_task_kind;
ALTER TABLE portal.runs ADD CONSTRAINT runs_task_kind CHECK(task_kind IN ('chat','document_summary','builder_trial'));
ALTER TABLE portal.runs DROP CONSTRAINT runs_summary_agent;
ALTER TABLE portal.runs ADD CONSTRAINT runs_summary_agent CHECK(task_kind<>'document_summary' OR agent_key='rules_rag');
CREATE TABLE portal.builder_trials(
 tenant_id uuid NOT NULL,run_id uuid NOT NULL,owner_user_id uuid NOT NULL,
 asset_id uuid NOT NULL,version_id uuid NOT NULL,purpose text NOT NULL CHECK(purpose IN ('generate','search')),
 profile_hash text NOT NULL,composition_hash text NOT NULL,model_ref text NOT NULL,
 messages jsonb NOT NULL CHECK(jsonb_typeof(messages)='array'),sources jsonb NOT NULL CHECK(jsonb_typeof(sources)='array'),
 result jsonb CHECK(result IS NULL OR octet_length(result::text)<=65536),
 PRIMARY KEY(tenant_id,run_id),FOREIGN KEY(tenant_id,run_id) REFERENCES portal.runs(tenant_id,run_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.asset_versions(tenant_id,version_id));
ALTER TABLE portal.builder_trials OWNER TO ai_owner;
ALTER TABLE portal.builder_trials ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_trials FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.builder_trials FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.builder_trials TO ai_policy_executor;
GRANT UPDATE(result) ON portal.builder_trials TO ai_policy_executor;
CREATE POLICY builder_trial_owner ON portal.builder_trials TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE FUNCTION portal.builder_trial_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
 IF (to_jsonb(NEW)-'result') IS DISTINCT FROM (to_jsonb(OLD)-'result') OR OLD.result IS NOT NULL
 THEN RAISE EXCEPTION 'TRIAL_IMMUTABLE' USING ERRCODE='23514';END IF;RETURN NEW;
END;$body$;
ALTER FUNCTION portal.builder_trial_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.builder_trial_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER builder_trial_immutable BEFORE UPDATE ON portal.builder_trials FOR EACH ROW EXECUTE FUNCTION portal.builder_trial_immutable();

CREATE FUNCTION security.builder_trial_compose(p_profile jsonb,p_values jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE names text[];parts text[];tokens text[];field text;role text;template text;content text;messages jsonb:='[]';i integer;
BEGIN
 IF jsonb_typeof(p_values) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(p_values))>20
 OR EXISTS(SELECT 1 FROM jsonb_each(p_values) x WHERE jsonb_typeof(x.value)<>'string' OR btrim(x.value#>>'{}')='' OR char_length(x.value#>>'{}')>2000)
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT array_agg(DISTINCT t[1] ORDER BY t[1]) INTO names FROM regexp_matches((p_profile->>'system_prompt')||(p_profile->>'developer_prompt')||(p_profile->>'user_template'),'\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}','g') t;
 IF COALESCE(names,ARRAY[]::text[]) IS DISTINCT FROM ARRAY(SELECT jsonb_object_keys(p_values) ORDER BY 1)
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 FOREACH field IN ARRAY ARRAY['system_prompt','developer_prompt','user_template'] LOOP
  template:=p_profile->>field;IF template='' THEN CONTINUE;END IF;
  parts:=regexp_split_to_array(template,'\{\{[A-Za-z][A-Za-z0-9_]{0,39}\}\}');
  SELECT array_agg(t[1]) INTO tokens FROM regexp_matches(template,'\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}','g') t;
  content:=parts[1];FOR i IN 1..COALESCE(cardinality(tokens),0) LOOP content:=content||(p_values->>tokens[i])||parts[i+1];END LOOP;
  role:=CASE field WHEN 'system_prompt' THEN 'system' WHEN 'developer_prompt' THEN 'developer' ELSE 'user' END;
  messages:=messages||jsonb_build_array(jsonb_build_object('role',role,'content',content));
 END LOOP;
 IF char_length((SELECT string_agg(x->>'content','') FROM jsonb_array_elements(messages) x))>8000
 OR octet_length((SELECT string_agg(x->>'content','') FROM jsonb_array_elements(messages) x))>24000
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 RETURN messages;
END;$body$;

CREATE FUNCTION security.builder_trial_guard(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE q portal.builder_trials%ROWTYPE;v jsonb;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 SELECT * INTO q FROM portal.builder_trials WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 v:=security.builder_version(p_session,p_tenant,q.asset_id,q.version_id);
 PERFORM security.builder_profile_validate(v->'config',v->'profile');
 IF v->>'profile_hash'<>q.profile_hash THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 IF jsonb_array_length(q.sources)>0 THEN PERFORM security.rag_sources_guard(p_session,p_tenant,(SELECT execution_mode FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run),q.sources);END IF;
 RETURN to_jsonb(q);
END;$body$;
CREATE OR REPLACE FUNCTION portal.run_asset_binding() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
DECLARE cfg jsonb;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (NEW.asset_id,NEW.asset_revision,NEW.asset_version_id,NEW.asset_config_hash)
   IS DISTINCT FROM (OLD.asset_id,OLD.asset_revision,OLD.asset_version_id,OLD.asset_config_hash) THEN
   RAISE EXCEPTION 'RUN_ASSET_BINDING_IMMUTABLE' USING ERRCODE='23514';END IF;
  RETURN NEW;
 END IF;
 IF NEW.task_kind='builder_trial' THEN
  IF current_setting('app.builder_admission',true) IS DISTINCT FROM NEW.run_id::text OR NEW.asset_id IS NULL
  OR NOT EXISTS(SELECT 1 FROM portal.asset_versions v WHERE (v.tenant_id,v.asset_id,v.version_id,v.revision,v.config_hash)=(NEW.tenant_id,NEW.asset_id,NEW.asset_version_id,NEW.asset_revision,NEW.asset_config_hash))
  THEN RAISE EXCEPTION 'TRIAL_BINDING_INVALID' USING ERRCODE='23514';END IF;RETURN NEW;
 END IF;
 IF NEW.agent_key NOT IN ('general','rules_rag') OR NEW.config_snapshot->>'agent_key' IS DISTINCT FROM NEW.agent_key
 OR jsonb_typeof(NEW.config_snapshot->'config_version') IS DISTINCT FROM 'number'
 OR NEW.config_snapshot->>'config_version' !~ '^[1-9][0-9]*$' THEN
  RAISE EXCEPTION 'RUN_ASSET_BINDING_INVALID' USING ERRCODE='23514';END IF;
 cfg:=jsonb_build_object(
  'name',COALESCE(NEW.config_snapshot->>'name',CASE WHEN NEW.agent_key='general' THEN '일반 대화' ELSE '규정 검색' END),
  'description',COALESCE(NEW.config_snapshot->>'description',''),
  'instructions',COALESCE(NEW.config_snapshot->>'instructions','질문에 답해 주세요.'),
  'execution_kind',NEW.agent_key);
 NEW.asset_id:=md5(NEW.tenant_id::text||':portal-agent:'||NEW.agent_key)::uuid;
 NEW.asset_revision:=(NEW.config_snapshot->>'config_version')::bigint;
 NEW.asset_config_hash:=encode(sha256(convert_to(cfg::text,'UTF8')),'hex');
 NEW.asset_version_id:=md5(NEW.asset_id::text||':revision:'||NEW.asset_revision::text||':'||NEW.asset_config_hash)::uuid;
 RETURN NEW;
END;$body$;
CREATE FUNCTION security.builder_trial_admit(p_session uuid,p_tenant uuid,p_asset uuid,p_version_id uuid,p_send uuid,p_values jsonb,p_purpose text,p_period date,p_mode text,p_tokens integer,p_digest bytea,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_ready jsonb;v_run uuid;v_conversation uuid;v_sequence bigint;v_snapshot jsonb;
 v_count_user integer;v_count_tenant integer;v_count_project integer;v_start timestamptz;v_count integer;v_now timestamptz;p_agent text;p_conversation uuid:=NULL;p_hash bytea;p_prompt text;p_version bigint;p_selected uuid[]:=ARRAY[]::uuid[];v_profile jsonb;v_messages jsonb;v_sources jsonb;v_detail jsonb;v_old portal.runs%ROWTYPE;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 v_detail:=security.builder_version(p_session,p_tenant,p_asset,p_version_id);v_profile:=v_detail->'profile';
 PERFORM security.builder_profile_validate(v_detail->'config',v_profile);
 IF p_send IS NULL OR p_purpose IS NULL OR p_purpose NOT IN ('generate','search')
 OR (p_purpose='search' AND v_detail->'config'->>'execution_kind'<>'rules_rag')
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 p_agent:=v_detail->'config'->>'execution_kind';v_messages:=security.builder_trial_compose(v_profile,p_values);p_prompt:=v_messages->-1->>'content';
 p_hash:=sha256(convert_to(jsonb_build_object('asset_id',p_asset,'version_id',p_version_id,'purpose',p_purpose,'values',p_values,'mode',p_mode)::text,'UTF8'));
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':trial:'||current_setting('app.user_id')||p_send::text,0));
 PERFORM security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO v_old FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=p_send;
 IF FOUND THEN
  IF v_old.task_kind<>'builder_trial' OR v_old.request_hash<>p_hash THEN RAISE EXCEPTION 'SEND_ID_CONFLICT' USING ERRCODE='B0301';END IF;
  PERFORM security.builder_trial_guard(p_session,p_tenant,v_old.run_id);
  RETURN security.run_view(p_tenant,v_old.run_id)||jsonb_build_object('replayed',true);
 END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('source_tenant_id',i.tenant_id,'document_id',i.document_id,'version_id',i.version_id,'index_id',i.index_id)),'[]') INTO v_sources
 FROM jsonb_array_elements(v_profile->'document_refs') ref JOIN rag.index_builds i ON i.document_id=(ref->>'document_id')::uuid AND i.version_id=(ref->>'version_id')::uuid
 WHERE i.execution_mode=p_mode AND security.document_can_read(i.tenant_id,i.document_id,i.version_id,i.index_id);
 IF jsonb_array_length(v_sources)<>jsonb_array_length(v_profile->'document_refs') THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='D0404';END IF;
 PERFORM set_config('app.rag_refs',(v_profile->'document_refs')::text,true);
 v_ready:=security.run_prepare(p_session,p_tenant,p_agent,p_conversation,p_send,p_hash,p_period,p_mode);
 p_version:=(v_ready->>'config_version')::bigint;
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
 PERFORM set_config('app.builder_admission',v_run::text,true);
 INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,request_hash,agent_key,config_snapshot,origin_session_id,execution_mode,task_kind,asset_id,asset_revision,asset_version_id,asset_config_hash)
 VALUES(p_tenant,v_run,v_conversation,v_user,p_send,p_hash,p_agent,v_snapshot,p_session,p_mode,'builder_trial',p_asset,(v_detail->>'revision')::bigint,p_version_id,v_detail->>'config_hash');
 INSERT INTO portal.builder_trials VALUES(p_tenant,v_run,v_user,p_asset,p_version_id,p_purpose,v_detail->>'profile_hash',encode(sha256(convert_to(v_messages::text,'UTF8')),'hex'),v_profile->>'model_ref',v_messages,v_sources,NULL);
 INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind)
 VALUES(p_tenant,gen_random_uuid(),v_conversation,v_user,p_agent,v_sequence,'user',p_prompt,v_run,'user');
 UPDATE portal.conversations SET updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND conversation_id=v_conversation;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,'builder.trial_admitted',v_run,'ok',jsonb_build_object('revision',1,'execution_mode',p_mode,'config_version',p_version));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN security.run_view(p_tenant,v_run)||jsonb_build_object('replayed',false);
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
 IF v_run.task_kind='builder_trial' THEN PERFORM security.builder_trial_guard(p_session,p_tenant,p_run);END IF;
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
 IF v_run.task_kind='builder_trial' THEN
 SELECT messages INTO v_messages FROM portal.builder_trials WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN jsonb_build_object('tenant_id',p_tenant,'run_id',p_run,'owner_user_id',v_user,'origin_session_id',p_session,'epoch',v_run.execution_epoch,'config_revision',v_agent.config_version,'mode',p_mode,'agent_key',v_run.agent_key,'document_refs',v_run.config_snapshot->'document_refs','task_kind','builder_trial','messages',v_messages,'trial_binding',jsonb_build_object('asset_id',v_run.asset_id,'revision',v_run.asset_revision,'version_id',v_run.asset_version_id,'config_hash',v_run.asset_config_hash));END IF;
 RETURN jsonb_build_object('tenant_id',p_tenant,'run_id',p_run,'owner_user_id',v_user,'origin_session_id',p_session,
 'epoch',v_run.execution_epoch,'config_revision',v_agent.config_version,'mode',p_mode,'agent_key',v_run.agent_key,'document_refs',v_run.config_snapshot->'document_refs',
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
 IF v_run.task_kind='builder_trial' THEN PERFORM security.builder_trial_guard(p_session,p_tenant,p_run);END IF;
 PERFORM security.execution_scope(p_tenant);
END; $body$;

CREATE FUNCTION security.builder_trial_read(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE q jsonb;v jsonb;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);q:=security.builder_trial_guard(p_session,p_tenant,p_run);v:=security.run_view(p_tenant,p_run);
 RETURN (v-'result')||jsonb_build_object('purpose',q->'purpose','model_ref',q->'model_ref','profile_hash',q->'profile_hash','composition_hash',q->'composition_hash',
 'asset_binding',jsonb_build_object('source','builder_trial','asset_id',q->'asset_id','version_id',q->'version_id','config_hash',(v->'asset_binding'->'config_hash'),'revision',v->'asset_binding'->'revision'),
 'content_status',CASE WHEN v->>'state'='completed' AND q->'result'<>'null'::jsonb THEN 'final' WHEN (v->>'is_terminal')::boolean THEN 'unavailable' ELSE 'pending' END,
 'result',q->'result');
END;$body$;

CREATE FUNCTION security.builder_trial_finish(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_result jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;q portal.builder_trials%ROWTYPE;
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 SELECT * INTO q FROM portal.builder_trials WHERE tenant_id=p_tenant AND run_id=p_run;
 IF r.task_kind<>'builder_trial' OR p_result->>'answer_kind' IS NULL OR p_result->>'answer_kind' NOT IN ('answer','insufficient_evidence') OR p_result->>'kind' IS DISTINCT FROM (CASE WHEN q.purpose='search' THEN 'retrieval' ELSE 'generation' END)
 OR (r.agent_key='general' AND NOT EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run AND operation='generate_general' AND state='settled'))
 OR jsonb_typeof(p_result) IS DISTINCT FROM 'object' OR octet_length(p_result::text)>65536
 OR EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run AND (state<>'settled' OR cost_overrun))
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 PERFORM security.builder_trial_guard(p_session,p_tenant,p_run);
 UPDATE portal.builder_trials SET result=p_result WHERE tenant_id=p_tenant AND run_id=p_run AND result IS NULL;
 IF NOT FOUND THEN RETURN false;END IF;
 UPDATE portal.runs SET state='completed',stage='terminal',ended_at=clock_timestamp(),revision=revision+1,answer_kind=p_result->>'answer_kind',source_count=CASE WHEN agent_key='rules_rag' AND p_result->>'answer_kind'='answer' THEN jsonb_array_length(q.sources) ELSE 0 END,provenance_sealed=(agent_key='rules_rag') WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN true;
END;$body$;
-- Definer metadata lookup avoids cyclic ai_web runs -> conversations policies.
CREATE FUNCTION security.builder_conversation_visible(p_tenant uuid,p_conversation uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE old_scope text;visible boolean;
BEGIN
 IF p_tenant IS DISTINCT FROM nullif(current_setting('app.tenant_id',true),'')::uuid OR nullif(current_setting('app.session_id',true),'') IS NULL THEN RETURN false;END IF;
 old_scope:=current_setting('app.run_scope',true);
 PERFORM security.run_authorize(nullif(current_setting('app.session_id',true),'')::uuid,p_tenant,false);
 visible:=NOT EXISTS(SELECT 1 FROM portal.runs r WHERE r.tenant_id=p_tenant AND r.conversation_id=p_conversation AND r.task_kind='builder_trial')
 OR (current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(p_tenant));
 PERFORM set_config('app.run_scope',coalesce(old_scope,''),true);RETURN visible;
EXCEPTION WHEN SQLSTATE 'A0401' OR SQLSTATE 'A0403' OR invalid_text_representation THEN RETURN false;
END;$body$;
ALTER FUNCTION security.builder_conversation_visible(uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_conversation_visible(uuid,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_conversation_visible(uuid,uuid) TO ai_web;
-- No trial conversations in user history. Internal owner workers use explicit management scope.
CREATE POLICY conversation_trial_private ON portal.conversations AS RESTRICTIVE FOR SELECT TO ai_web,ai_policy_executor
 USING(security.builder_conversation_visible(tenant_id,conversation_id));
ALTER FUNCTION security.builder_trial_compose(jsonb,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_compose(jsonb,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER FUNCTION security.builder_trial_guard(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_guard(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER FUNCTION security.builder_trial_admit(uuid,uuid,uuid,uuid,uuid,jsonb,text,date,text,integer,bytea,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_admit(uuid,uuid,uuid,uuid,uuid,jsonb,text,date,text,integer,bytea,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_admit(uuid,uuid,uuid,uuid,uuid,jsonb,text,date,text,integer,bytea,uuid) TO ai_web;
ALTER FUNCTION security.builder_trial_read(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_read(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_read(uuid,uuid,uuid) TO ai_web;
ALTER FUNCTION security.builder_trial_finish(uuid,uuid,uuid,bigint,bytea,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_finish(uuid,uuid,uuid,bigint,bytea,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_finish(uuid,uuid,uuid,bigint,bytea,jsonb) TO ai_web;

CREATE POLICY message_trial_private ON portal.messages AS RESTRICTIVE FOR SELECT TO ai_web,ai_policy_executor
 USING(security.builder_conversation_visible(tenant_id,conversation_id));
CREATE FUNCTION security.builder_trial_cancel(p_session uuid,p_tenant uuid,p_run uuid,p_expected bigint,p_trace uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 IF NOT EXISTS(SELECT 1 FROM portal.builder_trials WHERE tenant_id=p_tenant AND run_id=p_run)
 THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 RETURN security.run_cancel(p_session,p_tenant,p_run,p_expected,p_trace);
END;$body$;
ALTER FUNCTION security.builder_trial_cancel(uuid,uuid,uuid,bigint,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_cancel(uuid,uuid,uuid,bigint,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_cancel(uuid,uuid,uuid,bigint,uuid) TO ai_web;
