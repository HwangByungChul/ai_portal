-- B04 fixed worker/permit/meter functions. Never grant raw writes to LOGIN roles.
GRANT USAGE ON SCHEMA security TO ai_meter;
-- PostgreSQL counted regex repetition is capped at 255; preserve the allowed 1..256 ASCII range.
DO $fix$ DECLARE v record; BEGIN
 FOR v IN SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint
 WHERE conrelid='ops.call_attempts'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%{1,256}%' LOOP
  EXECUTE format('ALTER TABLE ops.call_attempts DROP CONSTRAINT %I',v.conname);
  EXECUTE format('ALTER TABLE ops.call_attempts ADD CONSTRAINT %I %s',v.conname,replace(v.definition,'{1,256}','{1,255}[!-~]?'));
 END LOOP;
END; $fix$;
ALTER TABLE portal.runs ADD COLUMN worker_claim_hash bytea CHECK(octet_length(worker_claim_hash)=32);
ALTER TABLE portal.runs ADD COLUMN execution_budget_id uuid REFERENCES ops.project_budget(budget_id);
GRANT UPDATE(worker_claim_hash,execution_budget_id,execution_epoch,heartbeat_at,lease_expires_at,started_at,safe_error_code,answer_kind)
 ON portal.runs TO ai_policy_executor;
GRANT SELECT,INSERT ON ops.call_attempts,ops.usage_events TO ai_policy_executor;
GRANT UPDATE(state,dispatch_claim_hash,dispatched_at,provider_end_status,provider_request_id,slot_held,cost_overrun,usage_snapshot)
 ON ops.call_attempts TO ai_policy_executor;
GRANT SELECT ON ops.project_budget TO ai_policy_executor;
GRANT UPDATE(reserved_krw,accounted_krw,active_slot,stop_latch,revision) ON ops.project_budget TO ai_policy_executor;
GRANT UPDATE(reserved_krw,accounted_krw,active_slot,revision) ON ops.tenant_budgets TO ai_policy_executor;
GRANT EXECUTE ON FUNCTION ops.valid_token_counts(jsonb) TO ai_policy_executor;

CREATE FUNCTION security.execution_scope(p_tenant uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user NOT IN ('ai_web','ai_meter') THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM set_config('app.execution_scope','metadata',true);
 PERFORM set_config('app.execution_tenant',COALESCE(p_tenant::text,'all'),true);
END; $body$;
CREATE FUNCTION security.execution_row_allowed(p_tenant uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 RETURN session_user IN ('ai_web','ai_meter') AND current_setting('app.execution_scope',true)='metadata'
 AND current_setting('app.execution_tenant',true) IN (p_tenant::text,'all');
END; $body$;
CREATE POLICY run_execution_metadata ON portal.runs TO ai_policy_executor
 USING(security.execution_row_allowed(tenant_id)) WITH CHECK(security.execution_row_allowed(tenant_id));
CREATE POLICY budget_execution_metadata ON ops.tenant_budgets TO ai_policy_executor
 USING(security.execution_row_allowed(tenant_id)) WITH CHECK(security.execution_row_allowed(tenant_id));
CREATE POLICY call_execution_metadata ON ops.call_attempts TO ai_policy_executor
 USING(security.execution_row_allowed(tenant_id)) WITH CHECK(security.execution_row_allowed(tenant_id));
CREATE POLICY usage_execution_metadata ON ops.usage_events TO ai_policy_executor
 USING(security.execution_row_allowed(tenant_id)) WITH CHECK(security.execution_row_allowed(tenant_id));
CREATE POLICY message_execution_assistant ON portal.messages FOR INSERT TO ai_policy_executor
 WITH CHECK(session_user='ai_web' AND current_setting('app.run_scope',true)='owner'
 AND security.run_row_allowed(tenant_id,owner_user_id) AND role='assistant'
 AND payload_kind='general_assistant' AND NOT payload_purged);

-- Internal guard locks current origin authority and Agent before any budget/run lock.
CREATE FUNCTION security.execution_guard(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_config boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='general' FOR SHARE;
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

CREATE FUNCTION security.execution_claim(p_session uuid,p_tenant uuid,p_run uuid,p_mode text,p_period date,p_worker bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_run portal.runs%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
 v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;v_messages jsonb;v_prompt text;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 IF p_worker IS NULL OR octet_length(p_worker)<>32 OR p_mode NOT IN ('mock','real') OR p_mode IS NULL
 OR p_period IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='general' FOR SHARE;
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
 UPDATE portal.runs SET state='running',stage='generation',worker_claim_hash=p_worker,execution_budget_id=v_project.budget_id,revision=revision+1,
 started_at=clock_timestamp(),heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+interval '60 seconds'
 WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN jsonb_build_object('tenant_id',p_tenant,'run_id',p_run,'owner_user_id',v_user,'origin_session_id',p_session,
 'epoch',v_run.execution_epoch,'config_revision',v_agent.config_version,'mode',p_mode,
 'messages',jsonb_build_array(jsonb_build_object('role','system','content',v_run.config_snapshot->>'instructions'))
 ||v_messages||jsonb_build_array(jsonb_build_object('role','user','content',v_prompt)));
END; $body$;

CREATE FUNCTION security.call_reserve(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_period date,p_input bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
 v_call uuid;v_price jsonb:='{"embedding_model":"text-embedding-3-small","embedding_usd_per_million":"0.02","generation_model":"gpt-4o-mini","input_usd_per_million":"0.15","krw_per_usd":"2000","output_usd_per_million":"0.60","protection_factor":"1.2","quantum_krw":"0.01","version":"price-20261004-v1"}';
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 IF p_input IS NULL OR octet_length(p_input)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
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

CREATE FUNCTION security.call_dispatch(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_call uuid,p_claim bytea)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_call ops.call_attempts%ROWTYPE;v_run portal.runs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 IF p_claim IS NULL OR octet_length(p_claim)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND run_id=p_run AND execution_epoch=p_epoch;
 IF NOT FOUND THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
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

-- Internal release requires saved no-dispatch evidence. A lease or timeout is never such evidence.
CREATE FUNCTION security.call_release_internal(p_tenant uuid,p_call uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_call ops.call_attempts%ROWTYPE;
BEGIN
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call FOR UPDATE;
 IF v_call.state IS DISTINCT FROM 'reserved' OR v_call.dispatched_at IS NOT NULL OR v_call.dispatch_claim_hash IS NOT NULL THEN RETURN false; END IF;
 UPDATE ops.project_budget SET reserved_krw=reserved_krw-v_call.reserved_krw,active_slot=active_slot-1,revision=revision+1 WHERE budget_id=v_call.budget_id;
 UPDATE ops.tenant_budgets SET reserved_krw=reserved_krw-v_call.reserved_krw,active_slot=active_slot-1,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=v_call.budget_id;
 INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot)
 VALUES(p_tenant,gen_random_uuid(),p_call,'release',-v_call.reserved_krw,0,v_call.price_snapshot);
 UPDATE ops.call_attempts SET state='released_no_dispatch',slot_held=false WHERE tenant_id=p_tenant AND call_id=p_call;
 RETURN true;
END; $body$;
CREATE FUNCTION security.call_release(p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_call uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_call ops.call_attempts%ROWTYPE;v_run portal.runs%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND run_id=p_run AND execution_epoch=p_epoch;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM budget_id FROM ops.project_budget WHERE budget_id=v_call.budget_id FOR UPDATE;
 PERFORM tenant_id FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_call.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF p_worker IS NULL OR v_run.worker_claim_hash IS DISTINCT FROM p_worker OR v_run.execution_epoch<>p_epoch THEN RETURN false; END IF;
 RETURN security.call_release_internal(p_tenant,p_call);
END; $body$;

-- Meter functions accept only call-bound saved dispatch proof; they expose no prompt or answer.
CREATE FUNCTION security.call_meter(p_tenant uuid,p_call uuid,p_epoch bigint,p_claim bytea,p_receipt jsonb,p_end text,p_invalid boolean)
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
 AND p_receipt->>'observed_model' IN ('gpt-4o-mini','gpt-4o-mini-2024-07-18') AND p_receipt->>'observed_tier'='default'
 AND (p_receipt->'provider_request_id'='null'::jsonb OR (jsonb_typeof(p_receipt->'provider_request_id')='string'
 AND p_receipt->>'provider_request_id' ~ '^[!-~]{1,255}[!-~]?$'));
 IF p_receipt IS NOT NULL AND NOT COALESCE(v_valid,false) THEN p_invalid:=true; END IF;
 IF v_call.state='settled' THEN
  v_conflict:=p_receipt IS NOT NULL AND v_call.usage_snapshot IS DISTINCT FROM p_receipt;
 ELSE
  IF COALESCE(v_valid,false) AND NOT p_invalid THEN
   v_cost:=ceil(((p_receipt->>'input_tokens')::numeric*0.15+(p_receipt->>'output_tokens')::numeric*0.60)*2000*1.2/1000000*100)/100;
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

CREATE FUNCTION security.execution_heartbeat(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,false);
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 SELECT * INTO v_project FROM ops.project_budget WHERE budget_id=v_run.execution_budget_id AND mode=v_run.execution_mode FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF v_run.state<>'running' OR v_run.execution_epoch<>p_epoch OR v_run.worker_claim_hash IS DISTINCT FROM p_worker
 OR v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (v_run.execution_mode='real' AND clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09') THEN RETURN false; END IF;
 UPDATE portal.runs SET heartbeat_at=clock_timestamp(),lease_expires_at=LEAST(clock_timestamp()+interval '60 seconds',started_at+interval '180 seconds')
 WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN true;
EXCEPTION WHEN SQLSTATE 'A0401' OR SQLSTATE 'A0403' OR SQLSTATE 'B0401' OR SQLSTATE 'B0402' THEN RETURN false;
END; $body$;

CREATE FUNCTION security.execution_finish(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_body text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_sequence bigint;
BEGIN
 IF p_body IS NULL OR btrim(p_body)='' OR octet_length(p_body)>65536
 THEN RAISE EXCEPTION 'RESULT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.run_authorize(p_session,p_tenant,true);
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

CREATE FUNCTION security.execution_fail(p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_code text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_code IS NULL OR p_code NOT IN ('EXECUTION_BLOCKED','CAPACITY_BUSY','QUOTA_EXCEEDED','AGENT_DISABLED','CONFIG_CHANGED','PERMIT_EXPIRED',
 'PROJECT_STOPPED','PROVIDER_TIMEOUT','PROVIDER_ERROR','STREAM_INTERRUPTED','EMPTY_RESPONSE','OUTPUT_TRUNCATED','RESPONSE_BLOCKED','USAGE_INVALID',
 'LEDGER_CONFLICT','LEDGER_UNAVAILABLE','RESULT_SAVE_FAILED','RUN_TIMEOUT','EXECUTION_INTERRUPTED')
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

CREATE FUNCTION security.execution_recover(p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run record;v_call record;v_count integer:=0;v_released integer:=0;v_unknown integer:=0;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_mode IS NULL OR p_mode NOT IN ('mock','real') OR NOT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory'
 AND classid=202610 AND objid=4 AND objsubid=2 AND pid=pg_backend_pid() AND granted)
 THEN RAISE EXCEPTION 'RECOVERY_LEADER_REQUIRED' USING ERRCODE='B0411'; END IF;
 PERFORM security.execution_scope(NULL);
 -- Exclusive process leader has stopped old owners; lock budgets first, then metadata-only runs/calls.
 PERFORM budget_id FROM ops.project_budget WHERE mode=p_mode ORDER BY budget_id FOR UPDATE;
 PERFORM tenant_id FROM ops.tenant_budgets WHERE budget_id IN(SELECT budget_id FROM ops.project_budget WHERE mode=p_mode)
 ORDER BY tenant_id,budget_id FOR UPDATE;
 FOR v_run IN SELECT tenant_id,run_id FROM portal.runs WHERE execution_mode=p_mode AND (state IN ('accepted','running','cancel_requested')
 OR EXISTS(SELECT 1 FROM ops.call_attempts c WHERE c.tenant_id=portal.runs.tenant_id AND c.run_id=portal.runs.run_id AND c.state IN ('reserved','dispatched')))
 ORDER BY tenant_id,run_id FOR UPDATE LOOP
  FOR v_call IN SELECT * FROM ops.call_attempts WHERE tenant_id=v_run.tenant_id AND run_id=v_run.run_id ORDER BY call_id FOR UPDATE LOOP
   IF v_call.state='reserved' THEN
    IF security.call_release_internal(v_call.tenant_id,v_call.call_id) THEN v_released:=v_released+1; END IF;
   ELSIF v_call.state='dispatched' THEN
    INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot)
    VALUES(v_call.tenant_id,gen_random_uuid(),v_call.call_id,'mark_unknown',0,0,v_call.price_snapshot) ON CONFLICT(tenant_id,call_id,event_kind) DO NOTHING;
    UPDATE ops.call_attempts SET state='usage_unknown' WHERE tenant_id=v_call.tenant_id AND call_id=v_call.call_id;v_unknown:=v_unknown+1;
   END IF;
  END LOOP;
  UPDATE portal.runs SET state='interrupted',stage='terminal',revision=revision+1,execution_epoch=execution_epoch+1,
   ended_at=clock_timestamp(),safe_error_code='EXECUTION_INTERRUPTED' WHERE tenant_id=v_run.tenant_id AND run_id=v_run.run_id
 AND state IN ('accepted','running','cancel_requested');
  IF FOUND THEN v_count:=v_count+1; END IF;
 END LOOP;
 RETURN jsonb_build_object('interrupted',v_count,'released_unfired',v_released,'unknown_dispatched',v_unknown);
END; $body$;

CREATE FUNCTION security.execution_reject(p_session uuid,p_tenant uuid,p_user uuid,p_run uuid,p_mode text,p_code text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_code IS NULL OR p_code NOT IN ('EXECUTION_BLOCKED','AGENT_DISABLED','CONFIG_CHANGED','PROJECT_STOPPED','LEDGER_UNAVAILABLE')
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM security.execution_scope(p_tenant);
 UPDATE portal.runs SET state='blocked',stage='terminal',ended_at=clock_timestamp(),revision=revision+1,safe_error_code=p_code
 WHERE tenant_id=p_tenant AND run_id=p_run AND origin_session_id=p_session AND owner_user_id=p_user
 AND execution_mode=p_mode AND state='accepted' AND worker_claim_hash IS NULL;
 RETURN FOUND;
END; $body$;
ALTER FUNCTION security.execution_reject(uuid,uuid,uuid,uuid,text,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_reject(uuid,uuid,uuid,uuid,text,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_reject(uuid,uuid,uuid,uuid,text,text) TO ai_web;

-- Stream authorization is fresh for each body batch, has no rate-limit side effect and never touches idle time.
CREATE FUNCTION security.execution_stream_view(p_session uuid,p_tenant uuid,p_run uuid,p_mode text,p_period date)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_view jsonb;v_agent portal.agent_configs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 v_view:=security.run_view(p_tenant,p_run);
 IF v_view->>'execution_mode'<>p_mode THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='general';
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 IF NOT (v_view->>'is_terminal')::boolean AND (NOT EXISTS(SELECT 1 FROM portal.runs r WHERE r.tenant_id=p_tenant AND r.run_id=p_run
 AND EXISTS(SELECT 1 FROM security.current_membership(r.origin_session_id,p_tenant))) OR NOT COALESCE(v_agent.enabled,false) OR v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL
 OR v_project.stopped OR v_project.stop_latch OR v_tenant.stopped) THEN RAISE EXCEPTION 'EXECUTION_BLOCKED' USING ERRCODE='B0405'; END IF;
 RETURN v_view||jsonb_build_object('execution_epoch',(SELECT execution_epoch FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run));
END; $body$;

ALTER FUNCTION security.execution_scope(uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_scope(uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;

ALTER FUNCTION security.execution_row_allowed(uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_row_allowed(uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;

ALTER FUNCTION security.execution_guard(uuid,uuid,uuid,bigint,bytea,boolean) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_guard(uuid,uuid,uuid,bigint,bytea,boolean) FROM PUBLIC,ai_web,ai_index,ai_meter;

ALTER FUNCTION security.execution_claim(uuid,uuid,uuid,text,date,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_claim(uuid,uuid,uuid,text,date,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_claim(uuid,uuid,uuid,text,date,bytea) TO ai_web;

ALTER FUNCTION security.call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.call_reserve(uuid,uuid,uuid,bigint,bytea,date,bytea) TO ai_web;

ALTER FUNCTION security.call_dispatch(uuid,uuid,uuid,bigint,bytea,uuid,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.call_dispatch(uuid,uuid,uuid,bigint,bytea,uuid,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.call_dispatch(uuid,uuid,uuid,bigint,bytea,uuid,bytea) TO ai_web;

ALTER FUNCTION security.call_release_internal(uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.call_release_internal(uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;

ALTER FUNCTION security.call_release(uuid,uuid,bigint,bytea,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.call_release(uuid,uuid,bigint,bytea,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.call_release(uuid,uuid,bigint,bytea,uuid) TO ai_web;

ALTER FUNCTION security.call_meter(uuid,uuid,bigint,bytea,jsonb,text,boolean) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.call_meter(uuid,uuid,bigint,bytea,jsonb,text,boolean) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.call_meter(uuid,uuid,bigint,bytea,jsonb,text,boolean) TO ai_meter;

ALTER FUNCTION security.execution_heartbeat(uuid,uuid,uuid,bigint,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_heartbeat(uuid,uuid,uuid,bigint,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_heartbeat(uuid,uuid,uuid,bigint,bytea) TO ai_web;

ALTER FUNCTION security.execution_finish(uuid,uuid,uuid,bigint,bytea,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_finish(uuid,uuid,uuid,bigint,bytea,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_finish(uuid,uuid,uuid,bigint,bytea,text) TO ai_web;

ALTER FUNCTION security.execution_fail(uuid,uuid,bigint,bytea,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_fail(uuid,uuid,bigint,bytea,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_fail(uuid,uuid,bigint,bytea,text) TO ai_web;

ALTER FUNCTION security.execution_recover(text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_recover(text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_recover(text) TO ai_web;

ALTER FUNCTION security.execution_stream_view(uuid,uuid,uuid,text,date) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_stream_view(uuid,uuid,uuid,text,date) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_stream_view(uuid,uuid,uuid,text,date) TO ai_web;

CREATE FUNCTION security.execution_readiness(p_session uuid,p_tenant uuid,p_period date,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_agent portal.agent_configs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;v_reason text;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='general';
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 v_reason:=CASE WHEN NOT COALESCE(v_agent.enabled,false) THEN 'AGENT_DISABLED'
 WHEN v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN 'BUDGET_NOT_READY'
 WHEN v_project.stopped OR v_project.stop_latch THEN 'PROJECT_STOPPED' WHEN v_tenant.stopped THEN 'TENANT_STOPPED'
 WHEN p_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09') THEN 'PROJECT_STOPPED'
 WHEN v_project.accounted_krw+v_project.reserved_krw+3.64>v_project.operational_cap_krw
 OR v_tenant.accounted_krw+v_tenant.reserved_krw+3.64>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw) THEN 'QUOTA_EXCEEDED'
 WHEN v_project.active_slot>=2 OR v_tenant.active_slot>=1 THEN 'CAPACITY_BUSY' ELSE NULL END;
 RETURN jsonb_build_object('available',v_reason IS NULL,'safe_block_reason',v_reason);
END; $body$;
ALTER FUNCTION security.execution_readiness(uuid,uuid,date,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_readiness(uuid,uuid,date,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_readiness(uuid,uuid,date,text) TO ai_web;
