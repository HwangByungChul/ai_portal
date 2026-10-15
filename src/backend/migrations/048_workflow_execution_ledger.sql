-- W5b: parent orchestration has no provider cost; children retain existing call/receipt ledgers.
ALTER TABLE portal.workflow_versions ADD COLUMN execution_mode text CHECK(execution_mode IN ('mock','real'));
ALTER TABLE portal.workflow_versions ADD COLUMN runtime_digest text CHECK(runtime_digest ~ '^[0-9a-f]{64}$');
ALTER TABLE portal.workflow_versions ADD CHECK((execution_mode IS NULL)=(runtime_digest IS NULL));
GRANT UPDATE(execution_mode,runtime_digest) ON portal.workflow_versions TO ai_policy_executor;
CREATE FUNCTION portal.workflow_version_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF TG_OP='DELETE' OR (NEW.tenant_id,NEW.workflow_id,NEW.version_id,NEW.revision,NEW.created_by,NEW.client_request_id,NEW.definition,NEW.version_digest,NEW.audience,NEW.member_ids,NEW.expected_head_revision,NEW.created_at)
 IS DISTINCT FROM (OLD.tenant_id,OLD.workflow_id,OLD.version_id,OLD.revision,OLD.created_by,OLD.client_request_id,OLD.definition,OLD.version_digest,OLD.audience,OLD.member_ids,OLD.expected_head_revision,OLD.created_at)
 OR OLD.runtime_digest IS NOT NULL AND (NEW.execution_mode,NEW.runtime_digest) IS DISTINCT FROM (OLD.execution_mode,OLD.runtime_digest)
 THEN RAISE EXCEPTION 'WORKFLOW_VERSION_IMMUTABLE' USING ERRCODE='23514';END IF;RETURN NEW;
END;$$;
ALTER FUNCTION portal.workflow_version_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.workflow_version_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter;
CREATE TRIGGER workflow_version_seal BEFORE UPDATE OR DELETE ON portal.workflow_versions FOR EACH ROW EXECUTE FUNCTION portal.workflow_version_immutable();

CREATE TABLE portal.workflow_runs(
 tenant_id uuid NOT NULL,run_id uuid NOT NULL DEFAULT gen_random_uuid(),owner_id uuid NOT NULL REFERENCES security.accounts(user_id),
 origin_session_id uuid NOT NULL,worker_session_id uuid,workflow_id uuid NOT NULL,version_id uuid NOT NULL,head_revision bigint NOT NULL,
 client_request_id uuid NOT NULL,request_hash text NOT NULL,execution_mode text NOT NULL CHECK(execution_mode IN ('mock','real')),runtime_digest text NOT NULL,budget_period date NOT NULL,
 inputs jsonb NOT NULL, state text NOT NULL DEFAULT 'accepted' CHECK(state IN ('accepted','running','completed','cancelled','failed','blocked','interrupted')),
 revision bigint NOT NULL DEFAULT 1,worker_token uuid,lease_until timestamptz,result jsonb,error_code text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),started_at timestamptz,ended_at timestamptz,
 PRIMARY KEY(tenant_id,run_id),UNIQUE(tenant_id,owner_id,client_request_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.workflow_versions(tenant_id,version_id),
 CHECK(octet_length(inputs::text)<=16384 AND (result IS NULL OR octet_length(result::text)<=32768)));
CREATE TABLE portal.workflow_steps(
 tenant_id uuid NOT NULL,parent_id uuid NOT NULL,owner_id uuid NOT NULL,node_id text NOT NULL,ordinal integer NOT NULL,node_type text NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','running','succeeded','failed','cancelled','interrupted','skipped')),
 child_run_id uuid,tool_client_id uuid,result jsonb,error_code text,
 PRIMARY KEY(tenant_id,parent_id,node_id),UNIQUE(tenant_id,child_run_id),UNIQUE(tenant_id,owner_id,tool_client_id),
 FOREIGN KEY(tenant_id,parent_id) REFERENCES portal.workflow_runs(tenant_id,run_id),
 FOREIGN KEY(tenant_id,child_run_id) REFERENCES portal.runs(tenant_id,run_id),
 FOREIGN KEY(tenant_id,owner_id,tool_client_id) REFERENCES portal.tool_receipts(tenant_id,user_id,client_request_id),
 CHECK(result IS NULL OR octet_length(result::text)<=32768));
CREATE INDEX workflow_active_owner ON portal.workflow_runs(tenant_id,owner_id) WHERE state IN ('accepted','running');
CREATE INDEX workflow_recovery_mode ON portal.workflow_runs(execution_mode) WHERE state='running';
ALTER TABLE portal.workflow_runs OWNER TO ai_owner;ALTER TABLE portal.workflow_steps OWNER TO ai_owner;
ALTER TABLE portal.workflow_runs ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.workflow_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.workflow_steps ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.workflow_steps FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.workflow_runs,portal.workflow_steps FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.workflow_runs,portal.workflow_steps TO ai_policy_executor;
GRANT UPDATE(state,revision,worker_session_id,worker_token,lease_until,result,error_code,started_at,ended_at) ON portal.workflow_runs TO ai_policy_executor;
GRANT UPDATE(state,child_run_id,tool_client_id,result,error_code) ON portal.workflow_steps TO ai_policy_executor;
CREATE POLICY workflow_run_owner ON portal.workflow_runs TO ai_policy_executor
 USING(session_user='ai_web' AND (current_setting('app.workflow_recovery',true)='yes' OR tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND
 (current_setting('app.workflow_scope',true)='capacity' OR owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,owner_id))))
 WITH CHECK(session_user='ai_web' AND (current_setting('app.workflow_recovery',true)='yes' OR tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,owner_id)));
CREATE POLICY workflow_step_owner ON portal.workflow_steps TO ai_policy_executor
 USING(session_user='ai_web' AND (current_setting('app.workflow_recovery',true)='yes' OR tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,owner_id)))
 WITH CHECK(session_user='ai_web' AND (current_setting('app.workflow_recovery',true)='yes' OR tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,owner_id)));
CREATE POLICY workflow_recovery_tool ON portal.tool_receipts TO ai_policy_executor USING(session_user='ai_web' AND current_setting('app.workflow_recovery',true)='yes') WITH CHECK(session_user='ai_web' AND current_setting('app.workflow_recovery',true)='yes');
CREATE POLICY audit_workflow_run ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(session_user='ai_web' AND scope_kind='tenant'
 AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid
 AND security.can_read_own_conversation(tenant_id,actor_id) AND action IN ('workflow.run_admitted','workflow.claimed','workflow.checkpoint','workflow.completed','workflow.failed','workflow.cancelled','workflow.interrupted'));

ALTER FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) RENAME TO workflow_approval_control_v047;
REVOKE ALL ON FUNCTION security.workflow_approval_control_v047(uuid,uuid,text,uuid,jsonb,text,uuid) FROM ai_web;
CREATE FUNCTION security.workflow_approval_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;vw portal.workflow_versions%ROWTYPE;u uuid;code text;clean jsonb;item jsonb;items jsonb:='[]';
BEGIN
 code:=p_body->>'runtime_digest';clean:=p_body-ARRAY['runtime_digest','execution_mode','budget_period'];
 IF code IS NULL OR code !~ '^[0-9a-f]{64}$' OR p_body->>'execution_mode' IS DISTINCT FROM p_mode THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action IN ('approve','reject') THEN
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
  SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=p_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  IF vw.created_by=u OR (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN' THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  IF clean-ARRAY['expected_revision']<>'{}' OR coalesce(clean->>'expected_revision','') !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  IF vw.status<>'pending' THEN
   IF vw.status=(CASE WHEN p_action='approve' THEN 'approved' ELSE 'rejected' END) AND vw.decision_revision=(clean->>'expected_revision')::bigint+1 THEN
    RETURN jsonb_build_object('version_id',vw.version_id,'workflow_id',vw.workflow_id,'revision',vw.decision_revision,'version_revision',vw.revision,'status',vw.status,'replayed',true);
   END IF;RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
  END IF;
  IF vw.decision_revision<>(clean->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  IF p_action='reject' THEN
   UPDATE portal.workflow_versions SET status='rejected',decision_revision=decision_revision+1,decided_by=u,decided_at=clock_timestamp() WHERE tenant_id=p_tenant AND version_id=p_id RETURNING * INTO vw;
   INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(p_trace,'tenant',p_tenant,u,'workflow.rejected',p_id,'ok');
   RETURN jsonb_build_object('version_id',vw.version_id,'workflow_id',vw.workflow_id,'revision',vw.decision_revision,'version_revision',vw.revision,'status',vw.status,'replayed',false);
  END IF;
  IF vw.runtime_digest IS DISTINCT FROM code OR vw.execution_mode IS DISTINCT FROM p_mode THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 END IF;
 data:=security.workflow_approval_control_v047(p_session,p_tenant,p_action,p_id,clean,p_mode,p_trace);
 IF p_action='submit' THEN
  SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=(data->>'version_id')::uuid FOR UPDATE;
  IF vw.runtime_digest IS NOT NULL AND (vw.runtime_digest<>code OR vw.execution_mode<>p_mode) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  IF vw.runtime_digest IS NULL AND vw.status<>'pending' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  IF vw.runtime_digest IS NULL THEN UPDATE portal.workflow_versions SET runtime_digest=code,execution_mode=p_mode WHERE tenant_id=p_tenant AND version_id=vw.version_id;END IF;
 ELSIF p_action IN ('list','catalog') THEN
  FOR item IN SELECT value FROM jsonb_array_elements(data->'items') LOOP
   SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=(item->>'version_id')::uuid;
   IF p_action='catalog' THEN
    BEGIN PERFORM security.workflow_version_guard(p_session,p_tenant,vw.version_id,p_mode,code,(p_body->>'budget_period')::date);
    EXCEPTION WHEN SQLSTATE 'A0404' OR SQLSTATE 'B0401' OR SQLSTATE 'D0404' OR SQLSTATE 'A0403' OR SQLSTATE 'B0340' THEN CONTINUE;END;
   END IF;
   items:=items||jsonb_build_array(item||jsonb_build_object('runtime_digest',vw.runtime_digest,'execution_mode',vw.execution_mode,'decision_revision',vw.decision_revision,'input_key',(SELECT n->'config'->>'input_key' FROM jsonb_array_elements(vw.definition->'nodes') n WHERE n->>'node_type'='input')));
  END LOOP;
  data:=jsonb_build_object('items',items);
 END IF;RETURN data;
END;$$;

CREATE FUNCTION security.workflow_version_guard(p_session uuid,p_tenant uuid,p_version uuid,p_mode text,p_code text,p_period date)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE u uuid;vw portal.workflow_versions%ROWTYPE;wh portal.workflow_heads%ROWTYPE;nd jsonb;pub jsonb;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=p_version;
 IF NOT FOUND OR vw.status<>'approved' OR vw.execution_mode IS DISTINCT FROM p_mode OR vw.runtime_digest IS DISTINCT FROM p_code THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 SELECT * INTO wh FROM portal.workflow_heads WHERE tenant_id=p_tenant AND workflow_id=vw.workflow_id FOR SHARE;
 IF wh.version_id IS DISTINCT FROM p_version OR NOT coalesce(wh.enabled,false) OR vw.audience='restricted' AND NOT u=ANY(vw.member_ids) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 PERFORM budget_id FROM ops.project_budget WHERE period=p_period AND mode=p_mode FOR SHARE;
 IF NOT FOUND OR EXISTS(SELECT 1 FROM ops.project_budget WHERE period=p_period AND mode=p_mode AND (stopped OR stop_latch)) OR EXISTS(SELECT 1 FROM ops.tenant_budgets t JOIN ops.project_budget b USING(budget_id) WHERE t.tenant_id=p_tenant AND b.period=p_period AND b.mode=p_mode AND t.stopped) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 FOR nd IN SELECT value FROM jsonb_array_elements(vw.definition->'nodes') LOOP
  IF nd->>'node_type'='llm' THEN
   pub:=security.published_asset_guard(p_session,p_tenant,(nd->'config'->>'asset_id')::uuid,p_mode);
   IF pub->>'version_id' IS DISTINCT FROM nd->'config'->>'version_id' OR (pub->>'publication_revision')::bigint IS DISTINCT FROM (nd->'config'->>'publication_revision')::bigint THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
   IF EXISTS(SELECT 1 FROM jsonb_array_elements(pub->'profile'->'document_refs') ref WHERE NOT EXISTS(SELECT 1 FROM rag.index_builds i WHERE i.document_id=(ref->>'document_id')::uuid AND i.version_id=(ref->>'version_id')::uuid AND i.execution_mode=p_mode AND security.document_can_read(i.tenant_id,i.document_id,i.version_id,i.index_id))) THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='D0404';END IF;
  ELSIF nd->>'node_type'='read_tool' THEN
   PERFORM t.tool_id FROM portal.tool_heads t JOIN portal.tool_approvals a ON (a.tenant_id,a.request_id)=(t.tenant_id,t.request_id) WHERE t.tenant_id=p_tenant AND t.tool_id=nd->'config'->>'tool_id' FOR SHARE OF t;
   IF NOT EXISTS(SELECT 1 FROM portal.tool_heads t JOIN portal.tool_approvals a ON (a.tenant_id,a.request_id)=(t.tenant_id,t.request_id) WHERE t.tenant_id=p_tenant AND t.tool_id=nd->'config'->>'tool_id' AND t.enabled AND a.status='approved' AND a.descriptor->>'digest'=nd->'config'->>'version_digest' AND a.descriptor->>'mode'=p_mode AND (a.audience='all' OR u=ANY(a.member_ids))) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
  END IF;
 END LOOP;
 RETURN jsonb_build_object('definition',vw.definition,'head_revision',wh.revision,'version_digest',vw.version_digest);
END;$$;

CREATE FUNCTION security.workflow_parent_guard(p_session uuid,p_tenant uuid,p_parent uuid,p_token uuid,p_active boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE wr portal.workflow_runs%ROWTYPE;data jsonb;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_parent FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 data:=security.workflow_version_guard(p_session,p_tenant,wr.version_id,wr.execution_mode,wr.runtime_digest,wr.budget_period);
 IF (data->>'head_revision')::bigint<>wr.head_revision OR wr.state NOT IN ('running','completed') OR (p_active AND (wr.state<>'running' OR wr.lease_until<=clock_timestamp() OR wr.started_at+interval '1200 seconds'<=clock_timestamp()))
 OR p_token IS NOT NULL AND (wr.worker_token IS DISTINCT FROM p_token OR wr.worker_session_id IS DISTINCT FROM p_session) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 RETURN data;
END;$$;

-- Bindings read only successful private checkpoint results. Clients cannot select a different value.
CREATE FUNCTION security.workflow_bindings(p_tenant uuid,p_parent uuid,p_node text,p_field text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE nd jsonb;cfg jsonb;item record;value jsonb;answer jsonb:='{}';
BEGIN
 SELECT n INTO nd FROM portal.workflow_runs r JOIN portal.workflow_versions v ON (v.tenant_id,v.version_id)=(r.tenant_id,r.version_id),jsonb_array_elements(v.definition->'nodes') n WHERE r.tenant_id=p_tenant AND r.run_id=p_parent AND n->>'node_id'=p_node;
 cfg:=nd->'config'->p_field;
 IF p_field='source' THEN cfg:=jsonb_build_object('source',cfg);END IF;
 FOR item IN SELECT * FROM jsonb_each(coalesce(cfg,'{}')) LOOP
  IF jsonb_typeof(item.value)='string' THEN value:=item.value;
  ELSE
   SELECT s.result INTO value FROM portal.workflow_steps s WHERE s.tenant_id=p_tenant AND s.parent_id=p_parent AND s.node_id=item.value->>'node_id' AND s.state='succeeded';
   IF item.value ? 'path' THEN value:=value #> ARRAY(SELECT jsonb_array_elements_text(item.value->'path'));END IF;
   IF value IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  END IF;
  answer:=answer||jsonb_build_object(item.key,value);
 END LOOP;
 RETURN CASE WHEN p_field='source' THEN answer->'source' ELSE answer END;
END;$$;

CREATE FUNCTION security.workflow_run_view(p_session uuid,p_tenant uuid,p_parent uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE wr portal.workflow_runs%ROWTYPE;items jsonb;value jsonb;child uuid;access text:='unavailable';
BEGIN
 SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_parent FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF wr.state='completed' THEN
  BEGIN
   PERFORM security.workflow_parent_guard(p_session,p_tenant,p_parent,NULL,false);
   FOR child IN SELECT child_run_id FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_parent AND child_run_id IS NOT NULL LOOP PERFORM security.published_run_guard(p_session,p_tenant,child);END LOOP;
   value:=wr.result;access:='final';
  EXCEPTION WHEN SQLSTATE 'A0404' OR SQLSTATE 'B0401' OR SQLSTATE 'D0404' OR SQLSTATE 'A0403' OR SQLSTATE 'B0340' THEN value:=NULL;END;
 END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('node_id',s.node_id,'node_type',s.node_type,'state',s.state,'child_run_id',s.child_run_id,'tool_client_id',s.tool_client_id,'error_code',s.error_code) ORDER BY s.ordinal),'[]') INTO items FROM portal.workflow_steps s WHERE s.tenant_id=p_tenant AND s.parent_id=p_parent;
 RETURN jsonb_build_object('run_id',wr.run_id,'version_id',wr.version_id,'workflow_id',wr.workflow_id,'state',wr.state,'revision',wr.revision,'is_terminal',wr.state NOT IN ('accepted','running'),'execution_mode',wr.execution_mode,'created_at',wr.created_at,'ended_at',wr.ended_at,'steps',items,'result_access',access,'result',value,'error_code',wr.error_code);
END;$$;

CREATE FUNCTION security.workflow_runtime(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_code text,p_token uuid,p_period date,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE u uuid;wr portal.workflow_runs%ROWTYPE;ws portal.workflow_steps%ROWTYPE;data jsonb;nd jsonb;hash text;changed boolean:=false;child record;event text;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,p_action<>'read');
 IF p_action IS NULL OR p_action NOT IN ('definition','admit','read','claim','heartbeat','step','checkpoint','finish','fail','cancel') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' OR p_body-ARRAY['version_id','client_request_id','inputs','node_id','result','error_code','expected_revision']<>'{}' OR octet_length(p_body::text)>32768 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='definition' THEN RETURN security.workflow_version_guard(p_session,p_tenant,p_id,p_mode,p_code,p_period);END IF;
 IF p_action='admit' THEN
  data:=security.workflow_version_guard(p_session,p_tenant,(p_body->>'version_id')::uuid,p_mode,p_code,p_period);
  IF jsonb_typeof(p_body->'inputs') IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(p_body->'inputs'))>20 OR p_body->>'client_request_id' IS NULL OR EXISTS(SELECT 1 FROM jsonb_each(p_body->'inputs') x WHERE jsonb_typeof(x.value)<>'string' OR char_length(x.value#>>'{}')>4000) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||':workflow-capacity',0));
  hash:=encode(sha256(convert_to(jsonb_build_object('version',p_body->>'version_id','inputs',p_body->'inputs','mode',p_mode,'code',p_code)::text,'UTF8')),'hex');
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND owner_id=u AND client_request_id=(p_body->>'client_request_id')::uuid FOR UPDATE;
  IF FOUND THEN IF wr.request_hash<>hash THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;RETURN security.workflow_run_view(p_session,p_tenant,wr.run_id)||jsonb_build_object('replayed',true);END IF;
  IF (SELECT count(*) FROM portal.workflow_runs WHERE tenant_id=p_tenant AND owner_id=u AND state IN ('accepted','running'))>=3 THEN RAISE EXCEPTION 'WORKFLOW_QUEUE_LIMIT' USING ERRCODE='A0429';END IF;
  PERFORM set_config('app.workflow_scope','capacity',true);
  IF (SELECT count(*) FROM portal.workflow_runs WHERE tenant_id=p_tenant AND state IN ('accepted','running'))>=20 THEN RAISE EXCEPTION 'WORKFLOW_QUEUE_LIMIT' USING ERRCODE='A0429';END IF;
  PERFORM set_config('app.workflow_scope','owner',true);
  INSERT INTO portal.workflow_runs(tenant_id,owner_id,origin_session_id,workflow_id,version_id,head_revision,client_request_id,request_hash,execution_mode,runtime_digest,budget_period,inputs)
  VALUES(p_tenant,u,p_session,(data->'definition'->>'workflow_id')::uuid,(p_body->>'version_id')::uuid,(data->>'head_revision')::bigint,(p_body->>'client_request_id')::uuid,hash,p_mode,p_code,p_period,p_body->'inputs') RETURNING * INTO wr;
  INSERT INTO portal.workflow_steps(tenant_id,parent_id,owner_id,node_id,ordinal,node_type) SELECT p_tenant,wr.run_id,u,n->>'node_id',ordinal,n->>'node_type' FROM jsonb_array_elements(data->'definition'->'nodes') WITH ORDINALITY AS x(n,ordinal);
  event:='workflow.run_admitted';changed:=true;
 ELSE
  SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  IF p_action='read' THEN
   IF wr.state='accepted' AND wr.created_at+interval '1200 seconds'<=clock_timestamp() OR wr.state='running' AND (wr.lease_until<=clock_timestamp() OR wr.started_at+interval '1200 seconds'<=clock_timestamp()) THEN
    UPDATE portal.tool_receipts SET state='unknown',result=NULL,error_code='TOOL_RESULT_UNKNOWN',revision=revision+1 WHERE tenant_id=p_tenant AND user_id=u AND state='dispatched' AND client_request_id IN (SELECT tool_client_id FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id);
    UPDATE portal.workflow_steps SET state=CASE WHEN state='running' THEN 'interrupted' ELSE 'skipped' END,error_code='WORKFLOW_INTERRUPTED' WHERE tenant_id=p_tenant AND parent_id=p_id AND state IN ('pending','running');
    UPDATE portal.workflow_runs SET state='interrupted',error_code='WORKFLOW_INTERRUPTED',revision=revision+1,ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_id;
    INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(p_trace,'tenant',p_tenant,u,'workflow.interrupted',p_id,'ok');
   END IF;
   RETURN security.workflow_run_view(p_session,p_tenant,p_id);
  END IF;
  IF p_action='cancel' THEN
   IF wr.revision IS DISTINCT FROM (p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   IF wr.state NOT IN ('accepted','running') THEN RETURN security.workflow_run_view(p_session,p_tenant,p_id);END IF;
  ELSIF p_action='fail' THEN
   IF wr.state NOT IN ('accepted','running') THEN RETURN security.workflow_run_view(p_session,p_tenant,p_id);END IF;
   IF p_token IS NULL OR wr.state='running' AND (wr.worker_token IS DISTINCT FROM p_token OR wr.worker_session_id IS DISTINCT FROM p_session) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
   IF coalesce(p_body->>'error_code','') NOT IN ('WORKFLOW_FAILED','WORKFLOW_BLOCKED','WORKFLOW_INTERRUPTED','WORKFLOW_CHILD_FAILED','WORKFLOW_BINDING_INVALID','WORKFLOW_INSUFFICIENT_EVIDENCE') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  ELSE
   IF wr.execution_mode<>p_mode OR wr.runtime_digest<>p_code THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
   data:=security.workflow_version_guard(p_session,p_tenant,wr.version_id,p_mode,p_code,p_period);
   IF (data->>'head_revision')::bigint<>wr.head_revision THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
   IF p_action='claim' THEN
    IF wr.state<>'accepted' THEN RETURN NULL;END IF;
    IF p_token IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
    UPDATE portal.workflow_runs SET state='running',worker_token=p_token,worker_session_id=p_session,lease_until=clock_timestamp()+interval '60 seconds',started_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=p_tenant AND run_id=p_id RETURNING * INTO wr;
    INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(p_trace,'tenant',p_tenant,u,'workflow.claimed',p_id,'ok');
    RETURN jsonb_build_object('definition',data->'definition','inputs',wr.inputs);
   END IF;
   PERFORM security.workflow_parent_guard(p_session,p_tenant,p_id,p_token,true);
   IF p_token IS NULL THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
   IF p_action='heartbeat' THEN UPDATE portal.workflow_runs SET lease_until=clock_timestamp()+interval '60 seconds' WHERE tenant_id=p_tenant AND run_id=p_id;RETURN jsonb_build_object('ok',true);END IF;
   IF p_action IN ('step','checkpoint') THEN
    SELECT * INTO ws FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND node_id=p_body->>'node_id' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
    IF p_action='step' THEN
     IF ws.state<>'pending' OR EXISTS(SELECT 1 FROM jsonb_array_elements(data->'definition'->'edges') e JOIN portal.workflow_steps s ON s.tenant_id=p_tenant AND s.parent_id=p_id AND s.node_id=e->>'source_node' WHERE e->>'target_node'=ws.node_id AND s.state<>'succeeded') OR EXISTS(SELECT 1 FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND state='running') THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
     UPDATE portal.workflow_steps SET state='running' WHERE tenant_id=p_tenant AND parent_id=p_id AND node_id=ws.node_id;
    ELSE
     IF ws.state<>'running' OR NOT p_body ? 'result' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
     IF ws.node_type='llm' AND NOT EXISTS(SELECT 1 FROM portal.runs WHERE tenant_id=p_tenant AND run_id=ws.child_run_id AND state='completed') OR ws.node_type='read_tool' AND NOT EXISTS(SELECT 1 FROM portal.tool_receipts WHERE tenant_id=p_tenant AND user_id=u AND client_request_id=ws.tool_client_id AND state='succeeded') THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
     IF ws.child_run_id IS NOT NULL THEN PERFORM security.published_run_guard(p_session,p_tenant,ws.child_run_id);END IF;
     UPDATE portal.workflow_steps SET state='succeeded',result=p_body->'result' WHERE tenant_id=p_tenant AND parent_id=p_id AND node_id=ws.node_id;
    END IF;event:='workflow.checkpoint';changed:=true;
   ELSIF p_action='finish' THEN
    IF EXISTS(SELECT 1 FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND state<>'succeeded') OR p_body->'result' IS DISTINCT FROM (SELECT result FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id AND node_type='output') THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
    UPDATE portal.workflow_runs SET state='completed',result=p_body->'result',revision=revision+1,ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_id;event:='workflow.completed';changed:=true;
   END IF;
  END IF;
  IF p_action IN ('cancel','fail') THEN
   -- Parent fence commits before separate child cancellation, avoiding parent/child lock inversion.
   UPDATE portal.tool_receipts SET state='unknown',result=NULL,error_code='TOOL_RESULT_UNKNOWN',revision=revision+1 WHERE tenant_id=p_tenant AND user_id=u AND state='dispatched' AND client_request_id IN (SELECT tool_client_id FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_id);
   UPDATE portal.workflow_steps SET state=CASE WHEN p_action='cancel' THEN 'cancelled' WHEN state='pending' THEN 'skipped' ELSE 'failed' END,error_code=CASE WHEN p_action='cancel' THEN NULL ELSE p_body->>'error_code' END WHERE tenant_id=p_tenant AND parent_id=p_id AND state IN ('pending','running');
   UPDATE portal.workflow_runs SET state=CASE WHEN p_action='cancel' THEN 'cancelled' WHEN p_body->>'error_code'='WORKFLOW_INTERRUPTED' THEN 'interrupted' WHEN p_body->>'error_code'='WORKFLOW_BLOCKED' THEN 'blocked' ELSE 'failed' END,error_code=CASE WHEN p_action='cancel' THEN NULL ELSE p_body->>'error_code' END,revision=revision+1,ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_id;
   event:=CASE WHEN p_action='cancel' THEN 'workflow.cancelled' ELSE 'workflow.failed' END;changed:=true;
  END IF;
 END IF;
 IF changed THEN INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(p_trace,'tenant',p_tenant,u,event,wr.run_id,'ok');END IF;
 RETURN security.workflow_run_view(p_session,p_tenant,wr.run_id)||jsonb_build_object('replayed',false);
END;$$;

CREATE FUNCTION security.workflow_child_admit(p_session uuid,p_tenant uuid,p_parent uuid,p_node text,p_token uuid,p_values jsonb,p_tokens integer,p_window bytea,p_mode text,p_code text,p_period date,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;nd jsonb;ws portal.workflow_steps%ROWTYPE;client_id uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 PERFORM run_id FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_parent AND execution_mode=p_mode AND budget_period=p_period AND runtime_digest=p_code FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 data:=security.workflow_parent_guard(p_session,p_tenant,p_parent,p_token,true);
 SELECT * INTO ws FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_parent AND node_id=p_node FOR UPDATE;
 SELECT value INTO nd FROM jsonb_array_elements(data->'definition'->'nodes') WHERE value->>'node_id'=p_node;
 IF ws.state IS DISTINCT FROM 'running' OR nd->>'node_type' IS DISTINCT FROM 'llm' OR p_values IS DISTINCT FROM security.workflow_bindings(p_tenant,p_parent,p_node,'values') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF ws.child_run_id IS NOT NULL THEN PERFORM security.published_run_guard(p_session,p_tenant,ws.child_run_id);RETURN security.run_view(p_tenant,ws.child_run_id)||jsonb_build_object('replayed',true);END IF;
 client_id:=md5(p_parent::text||':'||p_node||':llm')::uuid;
 IF EXISTS(SELECT 1 FROM portal.runs WHERE tenant_id=p_tenant AND client_send_id=client_id) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 data:=security.published_agent_admit(p_session,p_tenant,(nd->'config'->>'asset_id')::uuid,(nd->'config'->>'version_id')::uuid,client_id,p_values,'generate',(nd->'config'->>'publication_revision')::bigint,p_period,p_mode,p_tokens,p_window,p_trace);
 IF data ? 'admission_error' THEN RETURN data;END IF;
 UPDATE portal.workflow_steps SET child_run_id=(data->>'run_id')::uuid WHERE tenant_id=p_tenant AND parent_id=p_parent AND node_id=p_node;
 RETURN data;
END;$$;

ALTER FUNCTION security.published_run_guard(uuid,uuid,uuid) RENAME TO published_run_guard_v047;
REVOKE ALL ON FUNCTION security.published_run_guard_v047(uuid,uuid,uuid) FROM ai_web;
CREATE FUNCTION security.published_run_guard(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;parent uuid;active boolean;
BEGIN
 data:=security.published_run_guard_v047(p_session,p_tenant,p_run);
 SELECT parent_id INTO parent FROM portal.workflow_steps WHERE tenant_id=p_tenant AND child_run_id=p_run;
 IF FOUND THEN
  SELECT state<>'completed' INTO active FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
  PERFORM security.workflow_parent_guard(p_session,p_tenant,parent,NULL,active);
 END IF;RETURN data;
END;$$;

ALTER FUNCTION security.tool_execution_control(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid) RENAME TO tool_execution_control_v047;
REVOKE ALL ON FUNCTION security.tool_execution_control_v047(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid) FROM ai_web;
CREATE FUNCTION security.tool_execution_control(p_session uuid,p_tenant uuid,p_action text,p_tool text,p_digest text,p_mode text,p_client uuid,p_args jsonb,p_token uuid,p_result jsonb,p_error text,p_period date,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,p_action<>'ready');
 IF EXISTS(SELECT 1 FROM portal.workflow_steps WHERE tenant_id=p_tenant AND tool_client_id=p_client) THEN RAISE EXCEPTION 'TOOL_NOT_PERMITTED' USING ERRCODE='A0403';END IF;
 RETURN security.tool_execution_control_v047(p_session,p_tenant,p_action,p_tool,p_digest,p_mode,p_client,p_args,p_token,p_result,p_error,p_period,p_trace);
END;$$;
CREATE FUNCTION security.workflow_tool_control(p_session uuid,p_tenant uuid,p_parent uuid,p_node text,p_worker uuid,p_action text,p_tool text,p_digest text,p_mode text,p_client uuid,p_args jsonb,p_token uuid,p_result jsonb,p_error text,p_period date,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;nd jsonb;ws portal.workflow_steps%ROWTYPE;expected uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,true);
 PERFORM run_id FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_parent AND execution_mode=p_mode AND budget_period=p_period FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 data:=security.workflow_parent_guard(p_session,p_tenant,p_parent,p_worker,true);
 SELECT * INTO ws FROM portal.workflow_steps WHERE tenant_id=p_tenant AND parent_id=p_parent AND node_id=p_node FOR UPDATE;
 SELECT value INTO nd FROM jsonb_array_elements(data->'definition'->'nodes') WHERE value->>'node_id'=p_node;
 expected:=md5(p_parent::text||':'||p_node||':tool')::uuid;
 IF ws.state IS DISTINCT FROM 'running' OR nd->>'node_type' IS DISTINCT FROM 'read_tool' OR nd->'config'->>'tool_id' IS DISTINCT FROM p_tool OR nd->'config'->>'version_digest' IS DISTINCT FROM p_digest OR p_client IS DISTINCT FROM expected THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='admit' AND (p_args IS DISTINCT FROM security.workflow_bindings(p_tenant,p_parent,p_node,'arguments') OR ws.tool_client_id IS NULL AND EXISTS(SELECT 1 FROM portal.tool_receipts WHERE tenant_id=p_tenant AND user_id=NULLIF(current_setting('app.user_id'),'')::uuid AND client_request_id=p_client)) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 IF p_action<>'admit' AND ws.tool_client_id IS DISTINCT FROM p_client THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 data:=security.tool_execution_control_v047(p_session,p_tenant,p_action,p_tool,p_digest,p_mode,p_client,p_args,p_token,p_result,p_error,p_period,p_trace);
 IF p_action='admit' THEN UPDATE portal.workflow_steps SET tool_client_id=p_client WHERE tenant_id=p_tenant AND parent_id=p_parent AND node_id=p_node;END IF;
 RETURN data;
END;$$;

CREATE FUNCTION security.workflow_recover(p_mode text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE total integer;
BEGIN
 IF session_user<>'ai_web' OR coalesce(p_mode,'') NOT IN ('mock','real') THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501';END IF;
 PERFORM set_config('app.workflow_recovery','yes',true);
 UPDATE portal.tool_receipts SET state='unknown',result=NULL,error_code='TOOL_RESULT_UNKNOWN',revision=revision+1 WHERE state='dispatched' AND (tenant_id,user_id,client_request_id) IN (SELECT s.tenant_id,s.owner_id,s.tool_client_id FROM portal.workflow_steps s JOIN portal.workflow_runs r ON (r.tenant_id,r.run_id)=(s.tenant_id,s.parent_id) WHERE r.execution_mode=p_mode AND r.state='running');
 UPDATE portal.workflow_steps SET state=CASE WHEN state='running' THEN 'interrupted' ELSE 'skipped' END,error_code='WORKFLOW_INTERRUPTED' WHERE state IN ('pending','running') AND (tenant_id,parent_id) IN (SELECT tenant_id,run_id FROM portal.workflow_runs WHERE execution_mode=p_mode AND state='running');
 UPDATE portal.workflow_runs SET state='interrupted',error_code='WORKFLOW_INTERRUPTED',revision=revision+1,ended_at=clock_timestamp() WHERE execution_mode=p_mode AND state='running';GET DIAGNOSTICS total=ROW_COUNT;
 RETURN jsonb_build_object('interrupted',total);
END;$$;

-- New policy failures must terminate the existing child run after usage has been metered.
ALTER FUNCTION security.execution_fail(uuid,uuid,bigint,bytea,text) RENAME TO execution_fail_v047;
REVOKE ALL ON FUNCTION security.execution_fail_v047(uuid,uuid,bigint,bytea,text) FROM ai_web;
CREATE FUNCTION security.execution_fail(p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_code text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE child portal.runs%ROWTYPE;
BEGIN
 IF p_code IS NULL OR p_code NOT IN ('GUARDRAIL_INPUT_BLOCKED','GUARDRAIL_OUTPUT_BLOCKED','PAYLOAD_TOO_LARGE','OUTPUT_INVALID','MODEL_NOT_PERMITTED','PROVIDER_CONFIGURATION_REQUIRED','BUILDER_TEMPLATE_INVALID') THEN RETURN security.execution_fail_v047(p_tenant,p_run,p_epoch,p_worker,p_code);END IF;
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501';END IF;
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO child FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 IF p_worker IS NULL OR child.worker_claim_hash IS DISTINCT FROM p_worker OR child.execution_epoch IS DISTINCT FROM p_epoch OR child.state NOT IN ('running','cancel_requested') THEN RETURN false;END IF;
 UPDATE portal.runs SET state=CASE WHEN state='cancel_requested' THEN 'cancelled' ELSE 'failed' END,stage='terminal',revision=revision+1,safe_error_code=CASE WHEN state='cancel_requested' THEN NULL ELSE p_code END,ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN true;
END;$$;
ALTER FUNCTION security.execution_fail(uuid,uuid,bigint,bytea,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.execution_fail(uuid,uuid,bigint,bytea,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.execution_fail(uuid,uuid,bigint,bytea,text) TO ai_web;

-- Every public capability is a fixed SECURITY DEFINER; the renamed inner bodies stay web-inaccessible.
ALTER FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_version_guard(uuid,uuid,uuid,text,text,date) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_parent_guard(uuid,uuid,uuid,uuid,boolean) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_bindings(uuid,uuid,text,text) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_run_view(uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_runtime(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_child_admit(uuid,uuid,uuid,text,uuid,jsonb,integer,bytea,text,text,date,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.published_run_guard(uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.tool_execution_control(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_tool_control(uuid,uuid,uuid,text,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_recover(text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid),security.workflow_version_guard(uuid,uuid,uuid,text,text,date),security.workflow_parent_guard(uuid,uuid,uuid,uuid,boolean),security.workflow_bindings(uuid,uuid,text,text),security.workflow_run_view(uuid,uuid,uuid),security.workflow_runtime(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid),security.workflow_child_admit(uuid,uuid,uuid,text,uuid,jsonb,integer,bytea,text,text,date,uuid),security.published_run_guard(uuid,uuid,uuid),security.tool_execution_control(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid),security.workflow_tool_control(uuid,uuid,uuid,text,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid),security.workflow_recover(text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid),security.workflow_runtime(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid),security.workflow_child_admit(uuid,uuid,uuid,text,uuid,jsonb,integer,bytea,text,text,date,uuid),security.tool_execution_control(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid),security.workflow_tool_control(uuid,uuid,uuid,text,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid),security.workflow_recover(text) TO ai_web;
