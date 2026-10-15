-- Additive migration: existing ledgers/settings/000~025 are preserved.
CREATE TABLE portal.agent_deployments (
 tenant_id uuid NOT NULL,request_id uuid NOT NULL,client_request_id uuid NOT NULL,
 requester_id uuid NOT NULL,agent_key text NOT NULL,base_version bigint NOT NULL CHECK(base_version>0),
 previous jsonb NOT NULL,proposed jsonb NOT NULL,reason text NOT NULL CHECK(char_length(reason) BETWEEN 1 AND 500),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision IN (1,2)),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 decided_by uuid,decided_at timestamptz,comment text,deployed_version bigint,
 PRIMARY KEY(tenant_id,request_id),UNIQUE(tenant_id,requester_id,client_request_id),
 FOREIGN KEY(tenant_id,agent_key) REFERENCES portal.agent_configs(tenant_id,agent_key),
 FOREIGN KEY(tenant_id,requester_id) REFERENCES security.memberships(tenant_id,user_id),
 FOREIGN KEY(tenant_id,decided_by) REFERENCES security.memberships(tenant_id,user_id),
 CHECK(jsonb_typeof(previous)='object' AND jsonb_typeof(proposed)='object'),
 CHECK((status='pending' AND revision=1 AND decided_by IS NULL AND decided_at IS NULL AND comment IS NULL AND deployed_version IS NULL)
 OR (status IN ('approved','rejected') AND revision=2 AND decided_by IS NOT NULL AND decided_by<>requester_id
 AND decided_at IS NOT NULL AND char_length(comment) BETWEEN 1 AND 500
 AND ((status='approved' AND deployed_version=base_version+1) OR (status='rejected' AND deployed_version IS NULL))))
);
ALTER TABLE portal.agent_deployments OWNER TO ai_owner;
ALTER TABLE portal.agent_deployments ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.agent_deployments FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.agent_deployments FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.agent_deployments TO ai_policy_executor;
GRANT UPDATE(status,revision,decided_by,decided_at,comment,deployed_version) ON portal.agent_deployments TO ai_policy_executor;
CREATE POLICY deployment_access ON portal.agent_deployments TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true) IN ('agent_admin','agent_settings')
 AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_settings'
 AND security.can_manage_current_tenant(tenant_id));
CREATE INDEX deployment_queue ON portal.agent_deployments(tenant_id,status,created_at DESC,request_id DESC);

-- Preserve other operation contracts while preventing direct settings-write bypass.
ALTER FUNCTION security.operations_mutate(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) RENAME TO operations_mutate_internal;
REVOKE ALL ON FUNCTION security.operations_mutate_internal(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
CREATE FUNCTION security.operations_mutate(p_session uuid,p_tenant uuid,p_kind text,p_period date,p_mode text,
 p_agent text,p_delta jsonb,p_expected bigint,p_request uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF p_kind='agent_settings' THEN
  PERFORM security.operations_authorize(p_session,p_tenant,'agent_settings',true);
  RAISE EXCEPTION 'APPROVAL_REQUIRED' USING ERRCODE='D0409';
 END IF;
 RETURN security.operations_mutate_internal(p_session,p_tenant,p_kind,p_period,p_mode,p_agent,p_delta,p_expected,p_request);
END; $body$;
ALTER FUNCTION security.operations_mutate(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.operations_mutate(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.operations_mutate(uuid,uuid,text,date,text,text,jsonb,bigint,uuid) TO ai_web;

CREATE FUNCTION security.agent_deployment(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_period date,p_mode text,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_role text;v_row portal.agent_deployments%ROWTYPE;v_agent portal.agent_configs%ROWTYPE;
 v_items jsonb;v_result jsonb;v_status text;v_limit integer;v_cursor portal.agent_deployments%ROWTYPE;v_key text;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('list','detail','submit','decide') OR p_body IS NULL OR jsonb_typeof(p_body)<>'object' THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 v_user:=security.operations_authorize(p_session,p_tenant,CASE WHEN p_action IN ('submit','decide') THEN 'agent_settings' ELSE 'agent_admin' END,p_action IN ('submit','decide'));
 IF p_action='list' THEN
  IF p_body-ARRAY['status','limit','cursor']::text[]<>'{}'::jsonb THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  v_status:=p_body->>'status';v_limit:=COALESCE((p_body->>'limit')::integer,20);
  IF v_limit NOT BETWEEN 1 AND 50 OR (v_status IS NOT NULL AND v_status NOT IN ('pending','approved','rejected')) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  IF p_body->>'cursor' IS NOT NULL THEN
   SELECT * INTO v_cursor FROM portal.agent_deployments WHERE tenant_id=p_tenant AND request_id=(p_body->>'cursor')::uuid;
   IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  END IF;
  SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.request_id DESC),'[]'::jsonb) INTO v_items FROM
   (SELECT request_id,agent_key,requester_id,base_version,status,revision,created_at,proposed-ARRAY['instructions']::text[] AS proposed
    FROM portal.agent_deployments WHERE tenant_id=p_tenant AND (v_status IS NULL OR status=v_status)
    AND (v_cursor.request_id IS NULL OR (created_at,request_id)<(v_cursor.created_at,v_cursor.request_id))
    ORDER BY created_at DESC,request_id DESC LIMIT v_limit+1) x;
  RETURN jsonb_build_object('items',CASE WHEN jsonb_array_length(v_items)>v_limit THEN v_items-v_limit ELSE v_items END,
   'next_cursor',CASE WHEN jsonb_array_length(v_items)>v_limit THEN v_items->(v_limit-1)->>'request_id' ELSE NULL END);
 END IF;
 IF p_action='submit' THEN
  IF p_body-ARRAY['client_request_id','agent_key','expected_revision','name','description','instructions','reason']::text[]<>'{}'::jsonb
   OR NOT p_body ?& ARRAY['client_request_id','agent_key','expected_revision','name','description','instructions','reason'] THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  FOR v_key IN SELECT unnest(ARRAY['name','description','instructions','reason']) LOOP
   IF jsonb_typeof(p_body->v_key)<>'string' OR char_length(p_body->>v_key)>(CASE v_key WHEN 'name' THEN 80 WHEN 'description' THEN 500 WHEN 'instructions' THEN 2000 ELSE 500 END)
    OR (v_key<>'description' AND btrim(p_body->>v_key)='') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  END LOOP;
  IF jsonb_typeof(p_body->'expected_revision')<>'number' OR p_body->>'expected_revision' !~ '^[1-9][0-9]*$' OR p_id IS NULL OR p_trace IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  -- Serialize on the live config; snapshot cannot change while admitting the proposal.
  SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=p_body->>'agent_key' FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  SELECT * INTO v_row FROM portal.agent_deployments WHERE tenant_id=p_tenant AND requester_id=v_user AND client_request_id=(p_body->>'client_request_id')::uuid;
  IF FOUND THEN
   IF v_row.agent_key<>p_body->>'agent_key' OR v_row.base_version<>(p_body->>'expected_revision')::bigint
    OR v_row.proposed<>jsonb_build_object('name',p_body->>'name','description',p_body->>'description','instructions',p_body->>'instructions') OR v_row.reason<>p_body->>'reason' THEN
    RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
   RETURN jsonb_build_object('request_id',v_row.request_id,'status',v_row.status,'revision',v_row.revision,'replayed',true);
  END IF;
  IF v_agent.config_version<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  IF (SELECT count(*) FROM portal.agent_deployments WHERE tenant_id=p_tenant AND requester_id=v_user AND status='pending')>=20 THEN RAISE EXCEPTION 'QUEUE_LIMIT' USING ERRCODE='D0429'; END IF;
  INSERT INTO portal.agent_deployments(tenant_id,request_id,client_request_id,requester_id,agent_key,base_version,previous,proposed,reason)
  VALUES(p_tenant,p_id,(p_body->>'client_request_id')::uuid,v_user,v_agent.agent_key,v_agent.config_version,v_agent.settings,
   jsonb_build_object('name',p_body->>'name','description',p_body->>'description','instructions',p_body->>'instructions'),p_body->>'reason');
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
  VALUES(p_trace,'tenant',p_tenant,v_user,'agent_deployment_submit',p_id,'ok',jsonb_build_object('base_version',v_agent.config_version,'revision',1));
  IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
  RETURN jsonb_build_object('request_id',p_id,'status','pending','revision',1,'replayed',false);
 END IF;
 SELECT * INTO v_row FROM portal.agent_deployments WHERE tenant_id=p_tenant AND request_id=p_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF p_action='decide' THEN
  SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=v_row.agent_key FOR UPDATE;
 ELSE
  SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=v_row.agent_key;
 END IF;
 -- Config before request lock follows submit and existing operation lock ordering.
 IF p_action='decide' THEN
  SELECT * INTO v_row FROM portal.agent_deployments WHERE tenant_id=p_tenant AND request_id=p_id FOR UPDATE;
 END IF;
 SELECT effective_role INTO v_role FROM security.current_membership(p_session,p_tenant);
 IF p_action='detail' THEN
  RETURN to_jsonb(v_row)-ARRAY['tenant_id','client_request_id']::text[]||jsonb_build_object('current_version',v_agent.config_version,'can_decide',v_role='PADMIN' AND v_row.requester_id<>v_user AND v_row.status='pending');
 END IF;
 IF p_body-ARRAY['decision','comment','expected_revision']::text[]<>'{}'::jsonb OR NOT p_body ?& ARRAY['decision','comment','expected_revision']
  OR p_body->>'decision' NOT IN ('approve','reject') OR jsonb_typeof(p_body->'comment')<>'string' OR char_length(p_body->>'comment') NOT BETWEEN 1 AND 500 OR btrim(p_body->>'comment')=''
  OR jsonb_typeof(p_body->'expected_revision')<>'number' OR p_body->>'expected_revision' !~ '^[1-9][0-9]*$' OR p_trace IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF v_role<>'PADMIN' OR v_row.requester_id=v_user THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403'; END IF;
 v_status:=CASE WHEN p_body->>'decision'='approve' THEN 'approved' ELSE 'rejected' END;
 IF v_row.status<>'pending' THEN
  IF v_row.status=v_status AND v_row.decided_by=v_user AND v_row.comment=p_body->>'comment'
   AND (p_body->>'expected_revision')::bigint IN (v_row.revision-1,v_row.revision) THEN RETURN jsonb_build_object('request_id',p_id,'status',v_row.status,'revision',v_row.revision,'deployed_version',v_row.deployed_version,'replayed',true); END IF;
  RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
 END IF;
 IF v_row.revision<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 IF v_status='approved' THEN
  IF v_agent.config_version<>v_row.base_version THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  v_result:=security.operations_mutate_internal(p_session,p_tenant,'agent_settings',p_period,p_mode,v_row.agent_key,v_row.proposed,v_row.base_version,gen_random_uuid());
  PERFORM set_config('app.operations_scope','agent_settings',true);
 END IF;
 UPDATE portal.agent_deployments SET status=v_status,revision=2,decided_by=v_user,decided_at=clock_timestamp(),comment=p_body->>'comment',
 deployed_version=CASE WHEN v_status='approved' THEN v_row.base_version+1 ELSE NULL END WHERE tenant_id=p_tenant AND request_id=p_id;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_trace,'tenant',p_tenant,v_user,'agent_deployment_'||v_status,p_id,'ok',jsonb_build_object('base_version',v_row.base_version,'revision',2));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN jsonb_build_object('request_id',p_id,'status',v_status,'revision',2,'deployed_version',CASE WHEN v_status='approved' THEN v_row.base_version+1 ELSE NULL END,'replayed',false);
END; $body$;
ALTER FUNCTION security.agent_deployment(uuid,uuid,text,uuid,jsonb,date,text,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.agent_deployment(uuid,uuid,text,uuid,jsonb,date,text,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.agent_deployment(uuid,uuid,text,uuid,jsonb,date,text,uuid) TO ai_web;
