-- Runtime policy: current authenticated members may inspect their own tenant.
CREATE FUNCTION security.guardrail_runtime_policy(p_session uuid,p_tenant uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE v_policy jsonb;v_revision int;v_engine text;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 SELECT h.current_revision,v.policy,v.engine_revision INTO v_revision,v_policy,v_engine
 FROM ops.guardrail_policy_heads h JOIN ops.guardrail_policy_versions v
 ON v.tenant_id=h.tenant_id AND v.revision=h.current_revision
 WHERE h.tenant_id=p_tenant;
 IF NOT FOUND THEN
  IF EXISTS(SELECT 1 FROM ops.guardrail_policy_heads WHERE tenant_id=p_tenant) THEN
   RAISE EXCEPTION 'POLICY_UNAVAILABLE' USING ERRCODE='A0409';
  END IF;
  v_revision:=1;v_engine:='guardrail-v1';v_policy:='{"output_pii_action":"mask"}'::jsonb;
 END IF;
 RETURN v_policy || jsonb_build_object('revision',v_revision,'engine_revision',v_engine,
   'input_enabled',true,'output_enabled',true,'pii_severity','block',
   'injection_severity','block','forbidden_severity','block');
END; $body$;
ALTER FUNCTION security.guardrail_runtime_policy(uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.guardrail_runtime_policy(uuid,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.guardrail_runtime_policy(uuid,uuid) TO ai_web;
