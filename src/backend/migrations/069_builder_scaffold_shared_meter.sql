-- Link a private Builder proposal directly to the shared call/usage ledger.
-- No synthetic conversation or prompt row is created.
ALTER TABLE ops.call_attempts ALTER COLUMN run_id DROP NOT NULL;
ALTER TABLE ops.call_attempts ADD COLUMN proposal_id uuid;

DO $body$
DECLARE c record;
BEGIN
 FOR c IN SELECT conname FROM pg_constraint
  WHERE conrelid='ops.call_attempts'::regclass AND contype='c'
   AND pg_get_constraintdef(oid) ILIKE '%operation%'
 LOOP
  EXECUTE format('ALTER TABLE ops.call_attempts DROP CONSTRAINT %I',c.conname);
 END LOOP;
END;$body$;
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_attempts_operation_check
 CHECK(operation IN ('generate_general','builder_scaffold'));
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_attempts_proposal_binding
 CHECK((run_id IS NOT NULL AND proposal_id IS NULL AND operation='generate_general')
    OR (run_id IS NULL AND proposal_id IS NOT NULL AND operation='builder_scaffold'));
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_attempts_proposal_fk
 FOREIGN KEY(tenant_id,proposal_id) REFERENCES portal.builder_scaffold_proposals(tenant_id,proposal_id);
CREATE UNIQUE INDEX call_attempts_builder_scaffold_once
 ON ops.call_attempts(tenant_id,proposal_id) WHERE proposal_id IS NOT NULL;

ALTER TABLE portal.builder_scaffold_proposals ADD COLUMN meter_call_id uuid;
ALTER TABLE portal.builder_scaffold_proposals ADD COLUMN trace_id uuid;
ALTER TABLE portal.builder_scaffold_proposals ADD COLUMN execution_worker_hash bytea
 CHECK(execution_worker_hash IS NULL OR octet_length(execution_worker_hash)=32);
ALTER TABLE portal.builder_scaffold_proposals ADD CONSTRAINT builder_scaffold_meter_call_fk
 FOREIGN KEY(tenant_id,meter_call_id) REFERENCES ops.call_attempts(tenant_id,call_id);
ALTER TABLE portal.builder_scaffold_proposals ADD CONSTRAINT builder_scaffold_meter_call_unique
 UNIQUE(tenant_id,meter_call_id);
ALTER TABLE portal.builder_scaffold_proposals DROP CONSTRAINT builder_scaffold_proposals_state_check;
ALTER TABLE portal.builder_scaffold_proposals ADD CONSTRAINT builder_scaffold_proposals_state_check
 CHECK(state IN ('admitted','generating','ready','failed','discarded'));
GRANT SELECT ON portal.builder_scaffold_proposals TO ai_policy_executor;

-- Retire the metadata-only entry point from 068. New admissions are traced and audited.
REVOKE EXECUTE ON FUNCTION security.builder_scaffold_admit(uuid,uuid,uuid,text,jsonb,text,text,date) FROM ai_web;
CREATE FUNCTION security.builder_scaffold_admit(
 p_session uuid,p_tenant uuid,p_trace uuid,p_client_request uuid,p_target text,p_payload jsonb,
 p_model_id text,p_policy_revision text,p_budget_period date
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;result jsonb;proposal uuid;replayed boolean;
BEGIN
 IF p_trace IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 result:=security.builder_scaffold_admit(p_session,p_tenant,p_client_request,p_target,p_payload,
  p_model_id,p_policy_revision,p_budget_period);
 proposal:=(result->>'proposal_id')::uuid;replayed:=COALESCE((result->>'replayed')::boolean,false);
 IF NOT replayed THEN
  UPDATE portal.builder_scaffold_proposals SET trace_id=p_trace
   WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=proposal;
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
   VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.scaffold_admitted',proposal,'ok',
    jsonb_build_object('trace_id',p_trace,'policy_revision',p_policy_revision,'model_id',p_model_id));
 END IF;
 RETURN result;
END;$body$;
ALTER FUNCTION security.builder_scaffold_admit(uuid,uuid,uuid,uuid,text,jsonb,text,text,date) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_admit(uuid,uuid,uuid,uuid,text,jsonb,text,text,date) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_admit(uuid,uuid,uuid,uuid,text,jsonb,text,text,date) TO ai_web;

-- A single confirmed reservation is inserted into ops.call_attempts and ops.usage_events.
-- This mirrors the existing fixed-price reservation contract; final settlement always uses call_meter.
CREATE FUNCTION security.builder_scaffold_reserve(
 p_session uuid,p_tenant uuid,p_proposal uuid,p_period date,p_mode text,p_worker bytea,p_input bytea
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;role_name text;q portal.builder_scaffold_proposals%ROWTYPE;
 v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;v_call ops.call_attempts%ROWTYPE;
 v_id uuid;v_price jsonb:='{"embedding_model":"text-embedding-3-small","embedding_usd_per_million":"0.02","generation_model":"gpt-4o-mini","input_usd_per_million":"0.15","krw_per_usd":"2000","output_usd_per_million":"0.60","protection_factor":"1.2","quantum_krw":"0.01","version":"price-20261004-v1"}';
 v_policy jsonb;v_revision bigint;
BEGIN
 IF p_proposal IS NULL OR p_period IS NULL OR extract(day FROM p_period)<>1 OR p_mode NOT IN ('mock','real') OR p_mode IS NULL
 OR p_worker IS NULL OR octet_length(p_worker)<>32 OR p_input IS NULL OR octet_length(p_input)<>32 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 SELECT effective_role INTO role_name FROM security.current_membership(p_session,p_tenant);
 IF role_name NOT IN ('TADMIN','PADMIN') THEN RAISE EXCEPTION 'CAPABILITY_DENIED' USING ERRCODE='A0403'; END IF;
 IF EXISTS(SELECT 1 FROM ops.project_budget WHERE period=p_period AND mode=p_mode) THEN
  PERFORM security.execution_scope(p_tenant);
  SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode FOR UPDATE;
  SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id FOR UPDATE;
 END IF;
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 IF v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
 OR (p_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
  OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09')) THEN
  RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 SELECT * INTO q FROM portal.builder_scaffold_proposals
  WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF q.state<>'admitted' OR q.model_id<>'gpt-4o-mini' OR q.budget_period<>p_period THEN
  RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
 v_policy:=security.guardrail_runtime_policy(p_session,p_tenant);
 IF v_policy->>'revision' IS DISTINCT FROM q.policy_revision THEN RAISE EXCEPTION 'POLICY_CHANGED' USING ERRCODE='A0409'; END IF;
 IF v_project.accounted_krw+v_project.reserved_krw+3.64>v_project.operational_cap_krw
  OR v_tenant.accounted_krw+v_tenant.reserved_krw+3.64>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw) THEN
  RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0430'; END IF;
 IF v_project.active_slot>=2 OR v_tenant.active_slot>=1 THEN RAISE EXCEPTION 'CAPACITY_BUSY' USING ERRCODE='B0431'; END IF;
 SELECT * INTO v_call FROM ops.call_attempts WHERE tenant_id=p_tenant AND proposal_id=p_proposal;
 IF FOUND THEN RETURN jsonb_build_object('call_id',v_call.call_id,'created',false); END IF;
 v_id:=gen_random_uuid();v_revision:=q.revision+1;
 INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,proposal_id,initiator_user_id,operation,budget_id,mode,agent_key,
  config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,execution_epoch,reserved_krw,price_snapshot)
 VALUES(p_tenant,v_id,NULL,p_proposal,u,'builder_scaffold',v_project.budget_id,p_mode,'general',1,'generation',p_input,
  v_revision,clock_timestamp()+interval '10 seconds',1,3.64,v_price);
 INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot)
 VALUES(p_tenant,gen_random_uuid(),v_id,'reserve',3.64,0,v_price);
 UPDATE ops.project_budget SET reserved_krw=reserved_krw+3.64,active_slot=active_slot+1,revision=revision+1 WHERE budget_id=v_project.budget_id;
 UPDATE ops.tenant_budgets SET reserved_krw=reserved_krw+3.64,active_slot=active_slot+1,revision=revision+1
  WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 UPDATE portal.builder_scaffold_proposals SET state='generating',meter_call_id=v_id,
  execution_worker_hash=p_worker,revision=v_revision,updated_at=clock_timestamp()
  WHERE tenant_id=p_tenant AND proposal_id=p_proposal;
 RETURN jsonb_build_object('call_id',v_id,'created',true);
END;$body$;
ALTER FUNCTION security.builder_scaffold_reserve(uuid,uuid,uuid,date,text,bytea,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_reserve(uuid,uuid,uuid,date,text,bytea,bytea) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_reserve(uuid,uuid,uuid,date,text,bytea,bytea) TO ai_web;

CREATE FUNCTION security.builder_scaffold_dispatch(
 p_session uuid,p_tenant uuid,p_proposal uuid,p_call uuid,p_period date,p_mode text,p_worker bytea,p_claim bytea
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;q portal.builder_scaffold_proposals%ROWTYPE;c ops.call_attempts%ROWTYPE;
 v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;policy jsonb;
BEGIN
 IF p_proposal IS NULL OR p_call IS NULL OR p_period IS NULL OR p_mode NOT IN ('mock','real') OR p_mode IS NULL
 OR p_worker IS NULL OR octet_length(p_worker)<>32 OR p_claim IS NULL OR octet_length(p_claim)<>32 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND proposal_id=p_proposal FOR UPDATE;
 IF NOT FOUND OR c.operation<>'builder_scaffold' OR c.initiator_user_id<>u OR c.mode<>p_mode THEN
  RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 SELECT * INTO v_project FROM ops.project_budget WHERE budget_id=c.budget_id AND period=p_period AND mode=p_mode FOR UPDATE;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=c.budget_id FOR UPDATE;
 SELECT * INTO q FROM portal.builder_scaffold_proposals WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal FOR UPDATE;
 IF q.proposal_id IS NULL OR q.state<>'generating' OR q.meter_call_id<>p_call OR q.revision<>c.permit_revision
  OR q.execution_worker_hash IS DISTINCT FROM p_worker THEN
  RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 policy:=security.guardrail_runtime_policy(p_session,p_tenant);
 IF policy->>'revision' IS DISTINCT FROM q.policy_revision THEN RAISE EXCEPTION 'POLICY_CHANGED' USING ERRCODE='A0409'; END IF;
 IF c.state<>'reserved' THEN RETURN false; END IF;
 IF clock_timestamp()>=c.permit_expires_at OR v_project.stopped OR v_project.stop_latch OR v_tenant.stopped
  OR v_project.accounted_krw+v_project.reserved_krw>v_project.operational_cap_krw
  OR v_tenant.accounted_krw+v_tenant.reserved_krw>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw)
  OR (p_mode='real' AND clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09') THEN
  RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 UPDATE ops.call_attempts SET state='dispatched',dispatch_claim_hash=p_claim,dispatched_at=clock_timestamp(),provider_end_status='unknown'
  WHERE tenant_id=p_tenant AND call_id=p_call;
 RETURN true;
END;$body$;
ALTER FUNCTION security.builder_scaffold_dispatch(uuid,uuid,uuid,uuid,date,text,bytea,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_dispatch(uuid,uuid,uuid,uuid,date,text,bytea,bytea) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_dispatch(uuid,uuid,uuid,uuid,date,text,bytea,bytea) TO ai_web;

CREATE FUNCTION security.builder_scaffold_release(p_session uuid,p_tenant uuid,p_proposal uuid,p_call uuid,p_worker bytea)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;q portal.builder_scaffold_proposals%ROWTYPE;c ops.call_attempts%ROWTYPE;released boolean;
BEGIN
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO q FROM portal.builder_scaffold_proposals WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal FOR UPDATE;
 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND proposal_id=p_proposal AND call_id=p_call FOR UPDATE;
 IF q.proposal_id IS NULL OR c.call_id IS NULL OR q.meter_call_id<>p_call
  OR q.execution_worker_hash IS DISTINCT FROM p_worker THEN RETURN false; END IF;
 released:=security.call_release_internal(p_tenant,p_call);
 IF released AND q.state='generating' THEN
  UPDATE portal.builder_scaffold_proposals SET state='failed',request_payload='{}'::jsonb,
   safe_error_code='EXECUTION_BLOCKED',updated_at=clock_timestamp(),revision=revision+1
   WHERE tenant_id=p_tenant AND proposal_id=p_proposal;
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
   VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.scaffold_failed',p_proposal,'blocked',
    jsonb_build_object('error_code','EXECUTION_BLOCKED','call_id',p_call));
 END IF;
 RETURN released;
END;$body$;
ALTER FUNCTION security.builder_scaffold_release(uuid,uuid,uuid,uuid,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_release(uuid,uuid,uuid,uuid,bytea) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_release(uuid,uuid,uuid,uuid,bytea) TO ai_web;

CREATE FUNCTION security.builder_scaffold_fail(p_session uuid,p_tenant uuid,p_proposal uuid,p_revision bigint,p_code text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;q portal.builder_scaffold_proposals%ROWTYPE;c ops.call_attempts%ROWTYPE;
BEGIN
 IF p_code NOT IN ('SCAFFOLD_PROPOSAL_INVALID','GUARDRAIL_OUTPUT_BLOCKED','GUARDRAIL_INPUT_BLOCKED',
  'PROVIDER_ERROR','PROVIDER_CONFIGURATION_REQUIRED','MODEL_NOT_PERMITTED','LEDGER_UNAVAILABLE','LEDGER_CONFLICT',
  'STORAGE_UNAVAILABLE','OUTPUT_INVALID','PAYLOAD_TOO_LARGE','USAGE_INVALID','PROJECT_STOPPED','QUOTA_EXCEEDED','CAPACITY_BUSY','POLICY_CHANGED','EXECUTION_BLOCKED','EXECUTION_INTERRUPTED') OR p_code IS NULL THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 SELECT * INTO q FROM portal.builder_scaffold_proposals WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF q.state='failed' THEN RETURN jsonb_build_object('proposal_id',q.proposal_id,'state',q.state,'revision',q.revision,'error_code',q.safe_error_code,'replayed',true); END IF;
 IF q.revision<>p_revision OR q.state NOT IN ('admitted','generating') THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 IF q.state='generating' THEN
  SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=q.meter_call_id AND proposal_id=q.proposal_id;
  IF c.call_id IS NULL OR c.state NOT IN ('settled','usage_unknown','released_no_dispatch') THEN
   RAISE EXCEPTION 'SETTLEMENT_PENDING' USING ERRCODE='B0411';
  END IF;
 END IF;
 UPDATE portal.builder_scaffold_proposals SET state='failed',request_payload='{}'::jsonb,proposal_payload=NULL,
  safe_error_code=p_code,updated_at=clock_timestamp(),revision=revision+1
  WHERE tenant_id=p_tenant AND proposal_id=p_proposal RETURNING * INTO q;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
  VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.scaffold_failed',p_proposal,'failed',
   jsonb_build_object('error_code',p_code,'call_id',q.meter_call_id));
 RETURN jsonb_build_object('proposal_id',q.proposal_id,'state',q.state,'revision',q.revision,'error_code',q.safe_error_code,'replayed',false);
END;$body$;
ALTER FUNCTION security.builder_scaffold_fail(uuid,uuid,uuid,bigint,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_fail(uuid,uuid,uuid,bigint,text) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_fail(uuid,uuid,uuid,bigint,text) TO ai_web;

DROP FUNCTION security.builder_scaffold_complete(uuid,uuid,uuid,bigint,jsonb);
CREATE FUNCTION security.builder_scaffold_complete(
 p_session uuid,p_tenant uuid,p_proposal uuid,p_revision bigint,p_payload jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;q portal.builder_scaffold_proposals%ROWTYPE;c ops.call_attempts%ROWTYPE;kind text;
BEGIN
 IF p_payload IS NULL OR jsonb_typeof(p_payload)<>'object' OR p_revision IS NULL OR p_revision<1 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO q FROM portal.builder_scaffold_proposals WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF q.revision<>p_revision OR q.state<>'generating' OR q.meter_call_id IS NULL THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=q.meter_call_id AND proposal_id=q.proposal_id;
 IF c.state<>'settled' OR c.provider_end_status<>'observed' OR c.usage_snapshot IS NULL OR c.cost_overrun THEN
  RAISE EXCEPTION 'USAGE_INVALID' USING ERRCODE='B0411'; END IF;
 IF q.target='agent' THEN
  IF p_payload-ARRAY['config','profile','missing_questions','warnings']::text[]<>'{}'::jsonb
   OR NOT p_payload ?& ARRAY['config','profile','missing_questions','warnings'] THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  PERFORM security.builder_profile_validate(p_payload->'config',p_payload->'profile');
 ELSIF p_payload-ARRAY['name','description','nodes','edges','missing_questions','warnings']::text[]<>'{}'::jsonb
   OR NOT p_payload ?& ARRAY['name','description','nodes','edges','missing_questions','warnings'] THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
 END IF;
 UPDATE portal.builder_scaffold_proposals SET state='ready',proposal_payload=p_payload,safe_error_code=NULL,
  updated_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=p_tenant AND proposal_id=p_proposal RETURNING * INTO q;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
  VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.scaffold_ready',p_proposal,'ok',
   jsonb_build_object('call_id',q.meter_call_id,'revision',q.revision));
 RETURN jsonb_build_object('proposal_id',q.proposal_id,'state',q.state,'revision',q.revision,'proposal',q.proposal_payload);
END;$body$;
ALTER FUNCTION security.builder_scaffold_complete(uuid,uuid,uuid,bigint,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_complete(uuid,uuid,uuid,bigint,jsonb) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_complete(uuid,uuid,uuid,bigint,jsonb) TO ai_web;

CREATE OR REPLACE FUNCTION security.builder_scaffold_read(p_session uuid,p_tenant uuid,p_proposal uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;r portal.builder_scaffold_proposals%ROWTYPE;c ops.call_attempts%ROWTYPE;
BEGIN
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO r FROM portal.builder_scaffold_proposals WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF r.meter_call_id IS NOT NULL THEN
  SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=r.meter_call_id;
 END IF;
 RETURN jsonb_build_object('proposal_id',r.proposal_id,'target',r.target,'state',r.state,'revision',r.revision,
  'proposal',r.proposal_payload,'error_code',r.safe_error_code,'model_id',r.model_id,
  'policy_revision',r.policy_revision,'budget_period',r.budget_period,'created_at',r.created_at,
  'usage',CASE WHEN c.call_id IS NULL THEN NULL ELSE jsonb_build_object('call_id',c.call_id,'state',c.state,
   'provider_end_status',c.provider_end_status,'reserved_krw',c.reserved_krw::text,'cost_overrun',c.cost_overrun,
   'usage',c.usage_snapshot-ARRAY['provider_request_id']::text[]) END);
END;$body$;
ALTER FUNCTION security.builder_scaffold_read(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_read(uuid,uuid,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_read(uuid,uuid,uuid) TO ai_web;


DROP FUNCTION security.builder_scaffold_discard(uuid,uuid,uuid,bigint);
CREATE FUNCTION security.builder_scaffold_discard(p_session uuid,p_tenant uuid,p_proposal uuid,p_revision bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $body$
DECLARE u uuid;r portal.builder_scaffold_proposals%ROWTYPE;replayed boolean:=false;
BEGIN
 IF p_proposal IS NULL OR p_revision IS NULL OR p_revision<1 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 SELECT * INTO r FROM portal.builder_scaffold_proposals WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF r.revision<>p_revision THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 IF r.state='discarded' THEN replayed:=true;
 ELSE
  UPDATE portal.builder_scaffold_proposals SET state='discarded',request_payload='{}'::jsonb,proposal_payload=NULL,
   safe_error_code=NULL,execution_worker_hash=NULL,updated_at=clock_timestamp(),revision=revision+1
   WHERE tenant_id=p_tenant AND proposal_id=p_proposal RETURNING * INTO r;
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
   VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.scaffold_discarded',p_proposal,'ok',
    jsonb_build_object('revision',r.revision,'call_id',r.meter_call_id));
 END IF;
 RETURN jsonb_build_object('proposal_id',r.proposal_id,'state',r.state,'revision',r.revision,'replayed',replayed);
END;$body$;
ALTER FUNCTION security.builder_scaffold_discard(uuid,uuid,uuid,bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_discard(uuid,uuid,uuid,bigint) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_discard(uuid,uuid,uuid,bigint) TO ai_web;
