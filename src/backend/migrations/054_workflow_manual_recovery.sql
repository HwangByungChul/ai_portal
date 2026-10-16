-- Owner requested recovery requires a different tenant PADMIN approval.
CREATE TABLE portal.workflow_recovery_events(
 tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
 event_id uuid NOT NULL,
 request_id uuid NOT NULL,
 run_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES security.accounts(user_id),
 action text NOT NULL CHECK(action IN ('requested','approved','rejected','resumed')),
 client_request_id uuid NOT NULL,
 expected_run_revision bigint NOT NULL CHECK(expected_run_revision>0),
 version_digest text NOT NULL CHECK(version_digest ~ '^[0-9a-f]{64}$'),
 resume_node_id text NOT NULL CHECK(char_length(resume_node_id) BETWEEN 1 AND 64),
 reason text NOT NULL CHECK(char_length(btrim(reason)) BETWEEN 8 AND 1000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,event_id),
 UNIQUE(tenant_id,action,client_request_id),
 UNIQUE(tenant_id,request_id,action),
 FOREIGN KEY(tenant_id,run_id) REFERENCES portal.workflow_runs(tenant_id,run_id)
);
ALTER TABLE portal.workflow_recovery_events OWNER TO ai_owner;
ALTER TABLE portal.workflow_recovery_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.workflow_recovery_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.workflow_recovery_events FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.workflow_recovery_events TO ai_policy_executor;
CREATE POLICY workflow_recovery_events_guard ON portal.workflow_recovery_events TO ai_policy_executor
 USING(session_user='ai_web' AND current_setting('app.workflow_recovery',true)='yes'
  AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK(session_user='ai_web' AND current_setting('app.workflow_recovery',true)='yes'
  AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid);

CREATE FUNCTION security.workflow_recovery_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_code text,p_period date,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $$
DECLARE u uuid;role_name text;wr portal.workflow_runs%ROWTYPE;vw portal.workflow_versions%ROWTYPE;
 req portal.workflow_recovery_events%ROWTYPE;existing portal.workflow_recovery_events%ROWTYPE;
 definition jsonb;step_id text;items jsonb;v_request_id uuid;target_id uuid;expected bigint;digest text;reason_text text;
BEGIN
 IF p_action NOT IN ('list','mine','request','decide','resume') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='mine' THEN
  IF p_id IS NULL OR p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  u:=security.run_authorize(p_session,p_tenant,false);PERFORM set_config('app.workflow_recovery','yes',true);
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_id;
  IF NOT FOUND OR wr.owner_id<>u THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object('request_id',q.request_id,'status',q.status,'run_id',q.run_id,
   'expected_run_revision',q.expected_run_revision,'version_digest',q.version_digest,'resume_node_id',q.resume_node_id,
   'reason',q.reason,'created_at',q.created_at,'current_run_revision',wr.revision) ORDER BY q.created_at DESC),'[]'::jsonb) INTO items
  FROM (SELECT DISTINCT ON(e.request_id) e.*,
   (SELECT x.action FROM portal.workflow_recovery_events x WHERE x.tenant_id=p_tenant AND x.request_id=e.request_id ORDER BY x.created_at DESC,x.event_id DESC LIMIT 1) AS status
   FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.run_id=p_id AND e.actor_id=u AND e.action='requested'
   ORDER BY e.request_id,e.created_at DESC,e.event_id DESC) q;
  RETURN jsonb_build_object('items',items);
 END IF;
 IF p_action='list' THEN
  IF p_id IS NOT NULL OR p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',false);
  IF (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN' THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  PERFORM set_config('app.workflow_recovery','yes',true);
  PERFORM set_config('app.execution_scope','metadata',true);PERFORM set_config('app.execution_tenant',p_tenant::text,true);
  SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY q.created_at DESC),'[]'::jsonb) INTO items FROM (
   SELECT DISTINCT ON(e.request_id) e.request_id,e.run_id,e.actor_id AS requester_id,e.expected_run_revision,e.version_digest,
    e.resume_node_id,e.reason,e.created_at,
    (SELECT x.action FROM portal.workflow_recovery_events x WHERE x.tenant_id=p_tenant AND x.request_id=e.request_id ORDER BY x.created_at DESC,x.event_id DESC LIMIT 1) AS status,
    r.workflow_id,r.version_id,r.state AS run_state,r.revision AS current_run_revision,
    (SELECT coalesce(jsonb_agg(jsonb_build_object('node_id',s.node_id,'node_type',s.node_type,'state',s.state,'error_code',s.error_code) ORDER BY s.ordinal),'[]'::jsonb)
      FROM portal.workflow_steps s WHERE s.tenant_id=p_tenant AND s.parent_id=e.run_id) AS steps
   FROM portal.workflow_recovery_events e JOIN portal.workflow_runs r ON (r.tenant_id,r.run_id)=(e.tenant_id,e.run_id)
   WHERE e.tenant_id=p_tenant AND e.action='requested'
   ORDER BY e.request_id,e.created_at DESC,e.event_id DESC LIMIT 200
  ) q;
  RETURN jsonb_build_object('items',items);
 END IF;

 IF p_action='request' THEN
  IF p_id IS NULL OR p_body-ARRAY['client_request_id','expected_run_revision','resume_node_id','reason']<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  u:=security.run_authorize(p_session,p_tenant,false);
  v_request_id:=(p_body->>'client_request_id')::uuid;expected:=(p_body->>'expected_run_revision')::bigint;
  step_id:=p_body->>'resume_node_id';reason_text:=btrim(p_body->>'reason');
  IF v_request_id IS NULL OR expected<1 OR step_id IS NULL OR char_length(step_id) NOT BETWEEN 1 AND 64 OR reason_text IS NULL OR char_length(reason_text) NOT BETWEEN 8 AND 1000 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM set_config('app.workflow_recovery','yes',true);
  PERFORM set_config('app.execution_scope','metadata',true);PERFORM set_config('app.execution_tenant',p_tenant::text,true);
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_id FOR UPDATE;
  IF NOT FOUND OR wr.owner_id<>u THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  SELECT * INTO existing FROM portal.workflow_recovery_events WHERE tenant_id=p_tenant AND action='requested' AND client_request_id=v_request_id;
  IF FOUND THEN
   IF (existing.run_id,existing.actor_id,existing.expected_run_revision,existing.version_digest,existing.resume_node_id,existing.reason)
      IS DISTINCT FROM (p_id,u,expected,digest,step_id,reason_text) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN jsonb_build_object('request_id',existing.request_id,'run_id',existing.run_id,'status','requested','replayed',true);
  END IF;
  IF wr.state<>'interrupted' OR wr.revision<>expected OR wr.execution_mode<>p_mode OR wr.runtime_digest<>p_code THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=wr.version_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  digest:=vw.version_digest;
  definition:=(security.workflow_version_guard(p_session,p_tenant,wr.version_id,p_mode,p_code,wr.budget_period))->'definition';
  IF (SELECT count(*) FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND state='interrupted')<>1
    OR NOT EXISTS(SELECT 1 FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND node_id=step_id AND state='interrupted')
   THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  IF EXISTS(SELECT 1 FROM portal.workflow_steps s JOIN portal.tool_receipts t ON (t.tenant_id,t.user_id,t.client_request_id)=(s.tenant_id,s.owner_id,s.tool_client_id)
      WHERE s.tenant_id=p_tenant AND s.parent_id=p_id AND s.tool_client_id IS NOT NULL AND t.state<>'succeeded')
   OR EXISTS(SELECT 1 FROM portal.workflow_steps s JOIN portal.runs c ON (c.tenant_id,c.run_id)=(s.tenant_id,s.child_run_id)
      WHERE s.tenant_id=p_tenant AND s.parent_id=p_id AND s.child_run_id IS NOT NULL AND c.state<>'completed')
   THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
  IF EXISTS(SELECT 1 FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.run_id=p_id AND e.action='requested'
      AND NOT EXISTS(SELECT 1 FROM portal.workflow_recovery_events d WHERE d.tenant_id=p_tenant AND d.request_id=e.request_id AND d.action IN ('rejected','resumed'))) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  INSERT INTO portal.workflow_recovery_events(tenant_id,event_id,request_id,run_id,actor_id,action,client_request_id,expected_run_revision,version_digest,resume_node_id,reason)
  VALUES(p_tenant,p_trace,v_request_id,p_id,u,'requested',v_request_id,expected,digest,step_id,reason_text);
  IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401';END IF;
  RETURN jsonb_build_object('request_id',v_request_id,'run_id',p_id,'status','requested','replayed',false);
 END IF;

 IF p_action='decide' THEN
  IF p_id IS NULL OR p_body-ARRAY['client_request_id','expected_run_revision','decision','comment']<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
  IF (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN' THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  v_request_id:=p_id;expected:=(p_body->>'expected_run_revision')::bigint;reason_text:=btrim(p_body->>'comment');
  target_id:=(p_body->>'client_request_id')::uuid;
  IF v_request_id IS NULL OR target_id IS NULL OR expected<1 OR p_body->>'decision' NOT IN ('approve','reject') OR reason_text IS NULL OR char_length(reason_text) NOT BETWEEN 8 AND 1000 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM set_config('app.workflow_recovery','yes',true);
  PERFORM set_config('app.execution_scope','metadata',true);PERFORM set_config('app.execution_tenant',p_tenant::text,true);
  SELECT * INTO existing FROM portal.workflow_recovery_events WHERE tenant_id=p_tenant AND action=CASE p_body->>'decision' WHEN 'approve' THEN 'approved' ELSE 'rejected' END AND client_request_id=target_id;
  IF FOUND THEN
   IF existing.request_id<>v_request_id OR existing.actor_id<>u OR existing.reason<>reason_text THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN jsonb_build_object('request_id',v_request_id,'status',existing.action,'replayed',true);
  END IF;
  SELECT * INTO req FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.request_id=v_request_id AND e.action='requested';
  IF NOT FOUND OR req.actor_id=u THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  IF EXISTS(SELECT 1 FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.request_id=v_request_id AND e.action IN ('approved','rejected','resumed')) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=req.run_id FOR UPDATE;
  IF wr.state<>'interrupted' OR wr.revision<>expected OR expected<>req.expected_run_revision OR wr.owner_id<>req.actor_id OR wr.execution_mode<>p_mode OR wr.runtime_digest<>p_code THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=wr.version_id;
  IF vw.version_digest<>req.version_digest THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  IF p_body->>'decision'='approve' THEN
   IF vw.status<>'approved' OR NOT EXISTS(SELECT 1 FROM portal.workflow_heads h WHERE h.tenant_id=p_tenant AND h.workflow_id=wr.workflow_id AND h.version_id=wr.version_id AND h.enabled) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
   IF EXISTS(SELECT 1 FROM portal.workflow_steps s JOIN portal.tool_receipts t ON (t.tenant_id,t.user_id,t.client_request_id)=(s.tenant_id,s.owner_id,s.tool_client_id)
      WHERE s.tenant_id=p_tenant AND s.parent_id=wr.run_id AND s.tool_client_id IS NOT NULL AND t.state<>'succeeded')
    OR EXISTS(SELECT 1 FROM portal.workflow_steps s JOIN portal.runs c ON (c.tenant_id,c.run_id)=(s.tenant_id,s.child_run_id)
      WHERE s.tenant_id=p_tenant AND s.parent_id=wr.run_id AND s.child_run_id IS NOT NULL AND c.state<>'completed')
    THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
  END IF;
  INSERT INTO portal.workflow_recovery_events(tenant_id,event_id,request_id,run_id,actor_id,action,client_request_id,expected_run_revision,version_digest,resume_node_id,reason)
  VALUES(p_tenant,p_trace,v_request_id,wr.run_id,u,CASE p_body->>'decision' WHEN 'approve' THEN 'approved' ELSE 'rejected' END,target_id,expected,req.version_digest,req.resume_node_id,reason_text);
  IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401';END IF;
  RETURN jsonb_build_object('request_id',v_request_id,'run_id',wr.run_id,'status',CASE p_body->>'decision' WHEN 'approve' THEN 'approved' ELSE 'rejected' END,'replayed',false);
 END IF;

 IF p_action='resume' THEN
  IF p_id IS NULL OR p_body-ARRAY['client_request_id','request_id','expected_run_revision']<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  u:=security.run_authorize(p_session,p_tenant,true);
  v_request_id:=(p_body->>'request_id')::uuid;target_id:=(p_body->>'client_request_id')::uuid;expected:=(p_body->>'expected_run_revision')::bigint;
  IF v_request_id IS NULL OR target_id IS NULL OR expected<1 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM set_config('app.workflow_recovery','yes',true);
  PERFORM set_config('app.execution_scope','metadata',true);PERFORM set_config('app.execution_tenant',p_tenant::text,true);
  SELECT * INTO existing FROM portal.workflow_recovery_events WHERE tenant_id=p_tenant AND action='resumed' AND client_request_id=target_id;
  IF FOUND THEN
   IF existing.request_id<>v_request_id OR existing.run_id<>p_id OR existing.actor_id<>u OR existing.expected_run_revision<>expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN jsonb_build_object('request_id',v_request_id,'run_id',p_id,'state','accepted','revision',expected+1,'replayed',true);
  END IF;
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_id FOR UPDATE;
  IF NOT FOUND OR wr.owner_id<>u THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  SELECT * INTO req FROM portal.workflow_recovery_events e WHERE e.tenant_id=p_tenant AND e.request_id=v_request_id AND e.action='requested';
  IF NOT FOUND OR req.run_id<>p_id OR req.actor_id<>u OR NOT EXISTS(SELECT 1 FROM portal.workflow_recovery_events d WHERE d.tenant_id=p_tenant AND d.request_id=v_request_id AND d.action='approved' AND d.actor_id<>u) THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  digest:=req.version_digest;
  IF wr.state<>'interrupted' OR wr.revision<>expected OR expected<>req.expected_run_revision OR wr.execution_mode<>p_mode OR wr.runtime_digest<>p_code THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=wr.version_id;
  IF vw.version_digest<>digest THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  PERFORM security.workflow_version_guard(p_session,p_tenant,wr.version_id,p_mode,p_code,wr.budget_period);
  IF EXISTS(SELECT 1 FROM portal.workflow_steps s JOIN portal.tool_receipts t ON (t.tenant_id,t.user_id,t.client_request_id)=(s.tenant_id,s.owner_id,s.tool_client_id)
      WHERE s.tenant_id=p_tenant AND s.parent_id=p_id AND s.tool_client_id IS NOT NULL AND t.state<>'succeeded')
    OR EXISTS(SELECT 1 FROM portal.workflow_steps s JOIN portal.runs c ON (c.tenant_id,c.run_id)=(s.tenant_id,s.child_run_id)
      WHERE s.tenant_id=p_tenant AND s.parent_id=p_id AND s.child_run_id IS NOT NULL AND c.state<>'completed')
    THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
  IF NOT EXISTS(SELECT 1 FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND node_id=req.resume_node_id AND state='interrupted')
    OR (SELECT count(*) FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND state='interrupted')<>1 THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  UPDATE portal.workflow_steps SET state='pending',error_code=NULL WHERE tenant_id=p_tenant AND parent_id=p_id AND state IN ('interrupted','skipped');
  UPDATE portal.workflow_runs SET state='accepted',revision=revision+1,worker_token=NULL,worker_session_id=NULL,lease_until=NULL,
   result=NULL,error_code=NULL,started_at=NULL,ended_at=NULL WHERE tenant_id=p_tenant AND run_id=p_id RETURNING * INTO wr;
  INSERT INTO portal.workflow_recovery_events(tenant_id,event_id,request_id,run_id,actor_id,action,client_request_id,expected_run_revision,version_digest,resume_node_id,reason)
   VALUES(p_tenant,p_trace,v_request_id,p_id,u,'resumed',target_id,expected,digest,req.resume_node_id,'사용자 승인된 복구 재개');
  IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401';END IF;
  RETURN jsonb_build_object('request_id',v_request_id,'run_id',p_id,'state',wr.state,'revision',wr.revision,'replayed',false);
 END IF;
END;$$;

CREATE FUNCTION security.workflow_checkpoint_load(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,pg_temp AS $$
DECLARE u uuid;wr portal.workflow_runs%ROWTYPE;result jsonb;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,false);
 SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND OR wr.owner_id<>u OR wr.state<>'running' THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 SELECT coalesce(jsonb_object_agg(node_id,workflow_steps.result),'{}'::jsonb) INTO result FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_run AND state='succeeded';
 RETURN result;
END;$$;

ALTER FUNCTION security.workflow_recovery_control(uuid,uuid,text,uuid,jsonb,text,text,date,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_checkpoint_load(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.workflow_recovery_control(uuid,uuid,text,uuid,jsonb,text,text,date,uuid),security.workflow_checkpoint_load(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.workflow_recovery_control(uuid,uuid,text,uuid,jsonb,text,text,date,uuid),security.workflow_checkpoint_load(uuid,uuid,uuid) TO ai_web;
