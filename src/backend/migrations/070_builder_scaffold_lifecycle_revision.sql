-- Fix proposal lifecycle revision binding after reserve advances the admitted revision.
-- The original admitted revision remains the caller token; the reserve RPC binds the
-- generating revision to the shared call permit.
CREATE OR REPLACE FUNCTION security.builder_scaffold_fail(p_session uuid,p_tenant uuid,p_proposal uuid,p_revision bigint,p_code text)
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
 IF NOT ((q.state='admitted' AND q.revision=p_revision) OR
  (q.state='generating' AND q.revision=p_revision+1)) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 IF q.state='generating' THEN
  SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=q.meter_call_id AND proposal_id=q.proposal_id;
  IF c.call_id IS NULL OR c.permit_revision<>q.revision OR c.state NOT IN ('settled','usage_unknown','released_no_dispatch') THEN
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

CREATE OR REPLACE FUNCTION security.builder_scaffold_complete(
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
 IF q.revision<>p_revision+1 OR q.state<>'generating' OR q.meter_call_id IS NULL THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=q.meter_call_id AND proposal_id=q.proposal_id;
 IF c.permit_revision<>q.revision OR c.state<>'settled' OR c.provider_end_status<>'observed' OR c.usage_snapshot IS NULL OR c.cost_overrun THEN
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
