-- C03 Job embedding uses the existing central ledger, budget and settlement events.
ALTER TABLE ops.call_attempts ALTER COLUMN run_id DROP NOT NULL;
ALTER TABLE ops.call_attempts ADD COLUMN index_id uuid;
ALTER TABLE ops.call_attempts ADD COLUMN batch_ordinal integer CHECK(batch_ordinal BETWEEN 0 AND 15);
DO $fix$ DECLARE c record;BEGIN
 FOR c IN SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid='ops.call_attempts'::regclass AND contype='c' AND (pg_get_constraintdef(oid) LIKE '%job_id IS NULL%' OR pg_get_constraintdef(oid) LIKE '%operation =%' OR pg_get_constraintdef(oid) LIKE '%agent_key =%' OR pg_get_constraintdef(oid) LIKE '%step_key =%' OR pg_get_constraintdef(oid) LIKE '%usage_snapshot%') LOOP
 EXECUTE format('ALTER TABLE ops.call_attempts DROP CONSTRAINT %I',c.conname);
 END LOOP;
END;$fix$;
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_parent_kind CHECK(
 (run_id IS NOT NULL AND job_id IS NULL AND index_id IS NULL AND batch_ordinal IS NULL AND operation='generate_general' AND agent_key='general' AND step_key='generation') OR
 (run_id IS NULL AND job_id IS NOT NULL AND index_id IS NOT NULL AND batch_ordinal IS NOT NULL AND operation='embed_document' AND agent_key='rules_rag' AND step_key='batch-'||batch_ordinal::text));
ALTER TABLE rag.jobs ADD CONSTRAINT job_call_binding UNIQUE(tenant_id,job_id,index_id,initiator_user_id,execution_mode);
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_job_binding FOREIGN KEY(tenant_id,job_id,index_id,initiator_user_id,mode) REFERENCES rag.jobs(tenant_id,job_id,index_id,initiator_user_id,execution_mode);
CREATE UNIQUE INDEX calls_index_batch ON ops.call_attempts(tenant_id,index_id,batch_ordinal) WHERE operation='embed_document' AND state<>'released_no_dispatch';
ALTER TABLE ops.call_attempts ADD CONSTRAINT call_usage_typed CHECK(usage_snapshot IS NULL OR
 (jsonb_typeof(usage_snapshot)='object' AND usage_snapshot - ARRAY['input_tokens','output_tokens','total_tokens','observed_model','observed_tier','provider_request_id']::text[]='{}'::jsonb
 AND ops.valid_token_counts(usage_snapshot - ARRAY['observed_model','observed_tier','provider_request_id']::text[])
 AND usage_snapshot->>'observed_tier'='default'
 AND ((operation='generate_general' AND usage_snapshot->>'observed_model' IN ('gpt-4o-mini','gpt-4o-mini-2024-07-18')) OR (operation='embed_document' AND usage_snapshot->>'observed_model'='text-embedding-3-small' AND usage_snapshot->>'output_tokens'='0'))
 AND (usage_snapshot->'provider_request_id'='null'::jsonb OR (jsonb_typeof(usage_snapshot->'provider_request_id')='string' AND usage_snapshot->>'provider_request_id' ~ '^[!-~]{1,255}[!-~]?$'))));

CREATE OR REPLACE FUNCTION security.execution_scope(p_tenant uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user NOT IN ('ai_web','ai_meter','ai_index') THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM set_config('app.execution_scope','metadata',true);
 PERFORM set_config('app.execution_tenant',COALESCE(p_tenant::text,'all'),true);
END; $body$;

CREATE OR REPLACE FUNCTION security.execution_row_allowed(p_tenant uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 RETURN session_user IN ('ai_web','ai_meter','ai_index') AND current_setting('app.execution_scope',true)='metadata'
 AND current_setting('app.execution_tenant',true) IN (p_tenant::text,'all');
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
 AND ((v_call.operation='generate_general' AND p_receipt->>'observed_model' IN ('gpt-4o-mini','gpt-4o-mini-2024-07-18')) OR (v_call.operation='embed_document' AND p_receipt->>'observed_model'='text-embedding-3-small' AND p_receipt->>'output_tokens'='0')) AND p_receipt->>'observed_tier'='default'
 AND (p_receipt->'provider_request_id'='null'::jsonb OR (jsonb_typeof(p_receipt->'provider_request_id')='string'
 AND p_receipt->>'provider_request_id' ~ '^[!-~]{1,255}[!-~]?$'));
 IF p_receipt IS NOT NULL AND NOT COALESCE(v_valid,false) THEN p_invalid:=true; END IF;
 IF v_call.state='settled' THEN
  v_conflict:=p_receipt IS NOT NULL AND v_call.usage_snapshot IS DISTINCT FROM p_receipt;
 ELSE
  IF COALESCE(v_valid,false) AND NOT p_invalid THEN
   v_cost:=ceil(((p_receipt->>'input_tokens')::numeric*CASE WHEN v_call.operation='embed_document' THEN 0.02 ELSE 0.15 END+(p_receipt->>'output_tokens')::numeric*0.60)*2000*1.2/1000000*100)/100;
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

CREATE FUNCTION security.document_embedding_permit(p_tenant uuid,p_job uuid,p_epoch bigint,p_claim bytea,p_period date,p_batch integer,p_input bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE idx uuid;j rag.jobs%ROWTYPE;project ops.project_budget%ROWTYPE;tenant ops.tenant_budgets%ROWTYPE;c ops.call_attempts%ROWTYPE;price jsonb;
BEGIN
 -- Budget locks precede payload transaction; worker guard locks current identities/doc/Job.
 PERFORM security.execution_scope(p_tenant);
 idx:=security.document_worker_guard(p_tenant,p_job,p_epoch,p_claim);
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job;
 SELECT * INTO project FROM ops.project_budget WHERE period=p_period AND mode=j.execution_mode FOR UPDATE;
 SELECT * INTO tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=project.budget_id FOR UPDATE;

 IF p_batch IS NULL OR p_batch NOT BETWEEN 0 AND 15 OR p_input IS NULL OR octet_length(p_input)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND index_id=idx AND batch_ordinal=p_batch AND state<>'released_no_dispatch' FOR UPDATE;
 IF FOUND THEN
  IF c.input_fingerprint IS DISTINCT FROM p_input THEN RAISE EXCEPTION 'BATCH_CONFLICT' USING ERRCODE='A0409'; END IF;
  RETURN jsonb_build_object('call_id',c.call_id,'state',c.state,'created',false,'epoch',c.execution_epoch,'mode',c.mode);
 END IF;
 IF project.budget_id IS NULL OR tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF project.stopped OR project.stop_latch OR tenant.stopped OR (j.execution_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09')) THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF project.accounted_krw+project.reserved_krw+0.20>project.operational_cap_krw OR tenant.accounted_krw+tenant.reserved_krw+0.20>LEAST(tenant.local_cap_krw,tenant.allocated_cap_krw) THEN RAISE EXCEPTION 'QUOTA_EXCEEDED' USING ERRCODE='B0430'; END IF;
 IF project.active_slot>=2 OR tenant.active_slot>=1 THEN RAISE EXCEPTION 'CAPACITY_BUSY' USING ERRCODE='B0431'; END IF;
 price:='{"embedding_model":"text-embedding-3-small","embedding_usd_per_million":"0.02","generation_model":"gpt-4o-mini","input_usd_per_million":"0.15","krw_per_usd":"2000","output_usd_per_million":"0.60","protection_factor":"1.2","quantum_krw":"0.01","version":"price-20261004-v1"}';
 c.call_id:=gen_random_uuid();
 INSERT INTO ops.call_attempts(tenant_id,call_id,job_id,index_id,batch_ordinal,initiator_user_id,operation,budget_id,mode,agent_key,config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,execution_epoch,reserved_krw,price_snapshot)
 VALUES(p_tenant,c.call_id,p_job,idx,p_batch,j.initiator_user_id,'embed_document',project.budget_id,j.execution_mode,'rules_rag',(SELECT config_version FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag'),'batch-'||p_batch::text,p_input,j.revision,clock_timestamp()+interval '10 seconds',p_epoch,0.20,price);
 INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot) VALUES(p_tenant,gen_random_uuid(),c.call_id,'reserve',0.20,0,price);
 UPDATE ops.project_budget SET reserved_krw=reserved_krw+0.20,active_slot=active_slot+1,revision=revision+1 WHERE budget_id=project.budget_id;
 UPDATE ops.tenant_budgets SET reserved_krw=reserved_krw+0.20,active_slot=active_slot+1,revision=revision+1 WHERE tenant_id=p_tenant AND budget_id=project.budget_id;
 RETURN jsonb_build_object('call_id',c.call_id,'state','reserved','created',true,'epoch',p_epoch,'mode',j.execution_mode);
END;$body$;

CREATE FUNCTION security.document_embedding_dispatch(p_tenant uuid,p_job uuid,p_epoch bigint,p_worker bytea,p_call uuid,p_dispatch bytea) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE idx uuid;c ops.call_attempts%ROWTYPE;j rag.jobs%ROWTYPE;project ops.project_budget%ROWTYPE;tenant ops.tenant_budgets%ROWTYPE;
BEGIN
 PERFORM security.execution_scope(p_tenant);
 idx:=security.document_worker_guard(p_tenant,p_job,p_epoch,p_worker);
 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND job_id=p_job;
 SELECT * INTO project FROM ops.project_budget WHERE budget_id=c.budget_id FOR UPDATE;
 SELECT * INTO tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=c.budget_id FOR UPDATE;

 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND job_id=p_job FOR UPDATE;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job;
 IF c.state IS DISTINCT FROM 'reserved' OR c.execution_epoch<>p_epoch THEN RETURN false; END IF;
 IF p_dispatch IS NULL OR octet_length(p_dispatch)<>32 OR c.permit_expires_at<=clock_timestamp() OR c.permit_revision<>j.revision OR c.config_revision<>(SELECT config_version FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag') THEN RAISE EXCEPTION 'PERMIT_EXPIRED' USING ERRCODE='B0407'; END IF;
 IF project.stopped OR project.stop_latch OR tenant.stopped OR project.accounted_krw+project.reserved_krw>project.operational_cap_krw OR tenant.accounted_krw+tenant.reserved_krw>LEAST(tenant.local_cap_krw,tenant.allocated_cap_krw) THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 UPDATE ops.call_attempts SET state='dispatched',dispatch_claim_hash=p_dispatch,dispatched_at=clock_timestamp(),provider_end_status='unknown' WHERE tenant_id=p_tenant AND call_id=p_call;
 RETURN true;
END;$body$;

CREATE FUNCTION security.document_embedding_recover(p_tenant uuid,p_job uuid,p_epoch bigint,p_worker bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE idx uuid;c record;unknowns integer:=0;
BEGIN
 PERFORM security.execution_scope(p_tenant);
 idx:=security.document_worker_guard(p_tenant,p_job,p_epoch,p_worker);
 PERFORM budget_id FROM ops.project_budget ORDER BY budget_id FOR UPDATE;
 PERFORM budget_id FROM ops.tenant_budgets WHERE tenant_id=p_tenant ORDER BY budget_id FOR UPDATE;

 FOR c IN SELECT * FROM ops.call_attempts WHERE tenant_id=p_tenant AND index_id=idx ORDER BY call_id FOR UPDATE LOOP
  IF c.state='reserved' THEN PERFORM security.call_release_internal(p_tenant,c.call_id);
  ELSIF c.state IN ('dispatched','usage_unknown') THEN
   INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot) VALUES(p_tenant,gen_random_uuid(),c.call_id,'mark_unknown',0,0,c.price_snapshot) ON CONFLICT(tenant_id,call_id,event_kind) DO NOTHING;
   UPDATE ops.call_attempts SET state='usage_unknown' WHERE tenant_id=p_tenant AND call_id=c.call_id;unknowns:=unknowns+1;
  END IF;
 END LOOP;
 RETURN jsonb_build_object('unknown_batches',unknowns);
END;$body$;

ALTER FUNCTION security.document_embedding_permit(uuid,uuid,bigint,bytea,date,integer,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_embedding_permit(uuid,uuid,bigint,bytea,date,integer,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_embedding_permit(uuid,uuid,bigint,bytea,date,integer,bytea) TO ai_index;

ALTER FUNCTION security.document_embedding_dispatch(uuid,uuid,bigint,bytea,uuid,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_embedding_dispatch(uuid,uuid,bigint,bytea,uuid,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_embedding_dispatch(uuid,uuid,bigint,bytea,uuid,bytea) TO ai_index;

ALTER FUNCTION security.document_embedding_recover(uuid,uuid,bigint,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_embedding_recover(uuid,uuid,bigint,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_embedding_recover(uuid,uuid,bigint,bytea) TO ai_index;

CREATE OR REPLACE FUNCTION ops.call_binding_immutable() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog AS $body$
BEGIN
 IF (NEW.tenant_id,NEW.call_id,NEW.run_id,NEW.job_id,NEW.index_id,NEW.batch_ordinal,NEW.initiator_user_id,NEW.operation,NEW.budget_id,NEW.mode,
     NEW.agent_key,NEW.config_revision,NEW.step_key,NEW.attempt_no,NEW.input_fingerprint,NEW.permit_revision,
     NEW.permit_expires_at,NEW.execution_epoch,NEW.reserved_krw,NEW.price_snapshot,NEW.created_at)
 IS DISTINCT FROM (OLD.tenant_id,OLD.call_id,OLD.run_id,OLD.job_id,OLD.index_id,OLD.batch_ordinal,OLD.initiator_user_id,OLD.operation,OLD.budget_id,OLD.mode,
     OLD.agent_key,OLD.config_revision,OLD.step_key,OLD.attempt_no,OLD.input_fingerprint,OLD.permit_revision,
     OLD.permit_expires_at,OLD.execution_epoch,OLD.reserved_krw,OLD.price_snapshot,OLD.created_at)
 THEN RAISE EXCEPTION 'CALL_BINDING_IMMUTABLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $body$;
