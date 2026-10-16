-- Preserve migration 054's control while correcting idempotent retry and stale-head behavior.
ALTER FUNCTION security.workflow_recovery_control(uuid,uuid,text,uuid,jsonb,text,text,date,uuid)
 RENAME TO workflow_recovery_control_v054;
REVOKE ALL ON FUNCTION security.workflow_recovery_control_v054(uuid,uuid,text,uuid,jsonb,text,text,date,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;

CREATE FUNCTION security.workflow_recovery_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_code text,p_period date,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $$
DECLARE u uuid;wr portal.workflow_runs%ROWTYPE;req portal.workflow_recovery_events%ROWTYPE;existing portal.workflow_recovery_events%ROWTYPE;
 request_id uuid;expected bigint;digest text;step_id text;reason_text text;status_text text;head_revision bigint;
BEGIN
 IF p_action='request' THEN
  u:=security.run_authorize(p_session,p_tenant,false);
  PERFORM set_config('app.workflow_recovery','yes',true);
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_id;
  IF NOT FOUND OR wr.owner_id<>u THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  request_id:=(p_body->>'client_request_id')::uuid;expected:=(p_body->>'expected_run_revision')::bigint;
  step_id:=p_body->>'resume_node_id';reason_text:=btrim(p_body->>'reason');
  SELECT * INTO existing FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.action='requested' AND e.client_request_id=request_id;
  IF FOUND THEN
   SELECT version_digest INTO digest FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=wr.version_id;
   IF (existing.run_id,existing.actor_id,existing.expected_run_revision,existing.version_digest,existing.resume_node_id,existing.reason)
    IS DISTINCT FROM (p_id,u,expected,digest,step_id,reason_text) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   SELECT e.action INTO status_text FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.request_id=existing.request_id ORDER BY e.created_at DESC,e.event_id DESC LIMIT 1;
   RETURN jsonb_build_object('request_id',existing.request_id,'run_id',p_id,'status',status_text,'replayed',true);
  END IF;
  IF wr.state<>'interrupted' OR wr.revision<>expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  SELECT h.revision INTO head_revision FROM portal.workflow_heads h WHERE h.tenant_id=p_tenant AND h.workflow_id=wr.workflow_id AND h.version_id=wr.version_id AND h.enabled;
  IF head_revision IS DISTINCT FROM wr.head_revision THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 ELSIF p_action='decide' AND p_body->>'decision'='approve' THEN
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
  IF (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN' THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  PERFORM set_config('app.workflow_recovery','yes',true);
  request_id:=p_id;
  SELECT * INTO existing FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.action='approved' AND e.client_request_id=(p_body->>'client_request_id')::uuid;
  IF NOT FOUND THEN
   SELECT * INTO req FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.request_id=request_id AND e.action='requested';
   IF NOT FOUND OR req.actor_id=u THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
   SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=req.run_id;
   SELECT h.revision INTO head_revision FROM portal.workflow_heads h WHERE h.tenant_id=p_tenant AND h.workflow_id=wr.workflow_id AND h.version_id=wr.version_id AND h.enabled;
   IF wr.state<>'interrupted' OR wr.revision<>(p_body->>'expected_run_revision')::bigint OR wr.revision<>req.expected_run_revision OR head_revision IS DISTINCT FROM wr.head_revision THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  END IF;
 ELSIF p_action='resume' THEN
  u:=security.run_authorize(p_session,p_tenant,true);
  PERFORM set_config('app.workflow_recovery','yes',true);
  request_id:=(p_body->>'request_id')::uuid;expected:=(p_body->>'expected_run_revision')::bigint;
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_id;
  IF NOT FOUND OR wr.owner_id<>u THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  SELECT * INTO existing FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.action='resumed' AND e.client_request_id=(p_body->>'client_request_id')::uuid;
  IF FOUND THEN
   IF existing.request_id<>request_id OR existing.run_id<>p_id OR existing.actor_id<>u OR existing.expected_run_revision<>expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN jsonb_build_object('request_id',request_id,'run_id',p_id,'state',wr.state,'revision',wr.revision,'replayed',true);
  END IF;
  SELECT * INTO req FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.request_id=request_id AND e.action='requested';
  IF NOT FOUND OR req.run_id<>p_id OR req.actor_id<>u OR NOT EXISTS(SELECT 1 FROM portal.workflow_recovery_events d WHERE d.tenant_id=p_tenant AND d.request_id=request_id AND d.action='approved' AND d.actor_id<>u) THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  SELECT h.revision INTO head_revision FROM portal.workflow_heads h WHERE h.tenant_id=p_tenant AND h.workflow_id=wr.workflow_id AND h.version_id=wr.version_id AND h.enabled;
  IF wr.state<>'interrupted' OR wr.revision<>expected OR expected<>req.expected_run_revision OR head_revision IS DISTINCT FROM wr.head_revision THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 END IF;
 RETURN security.workflow_recovery_control_v054(p_session,p_tenant,p_action,p_id,p_body,p_mode,p_code,p_period,p_trace);
END;$$;

ALTER FUNCTION security.workflow_recovery_control(uuid,uuid,text,uuid,jsonb,text,text,date,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.workflow_recovery_control(uuid,uuid,text,uuid,jsonb,text,text,date,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.workflow_recovery_control(uuid,uuid,text,uuid,jsonb,text,text,date,uuid) TO ai_web;
