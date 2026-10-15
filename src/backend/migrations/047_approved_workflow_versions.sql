-- W5a: immutable server-validated Workflow definitions and separate approval heads.
CREATE TABLE portal.workflows(
 tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),workflow_id uuid NOT NULL,
 owner_id uuid NOT NULL REFERENCES security.accounts(user_id),client_request_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,workflow_id),
 UNIQUE(tenant_id,owner_id,client_request_id));
CREATE TABLE portal.workflow_versions(
 tenant_id uuid NOT NULL,workflow_id uuid NOT NULL,version_id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>0),decision_revision bigint NOT NULL DEFAULT 1 CHECK(decision_revision>0),created_by uuid NOT NULL REFERENCES security.accounts(user_id),
 client_request_id uuid NOT NULL,definition jsonb NOT NULL CHECK(jsonb_typeof(definition)='object'),
 version_digest text NOT NULL CHECK(version_digest ~ '^[0-9a-f]{64}$'),
 audience text NOT NULL CHECK(audience IN ('all','restricted')),member_ids uuid[] NOT NULL,
 expected_head_revision bigint NOT NULL CHECK(expected_head_revision>=0),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 decided_by uuid REFERENCES security.accounts(user_id),decided_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,version_id),UNIQUE(tenant_id,workflow_id,revision),
 UNIQUE(tenant_id,created_by,client_request_id),
 FOREIGN KEY(tenant_id,workflow_id) REFERENCES portal.workflows(tenant_id,workflow_id));
CREATE TABLE portal.workflow_heads(
 tenant_id uuid NOT NULL,workflow_id uuid NOT NULL,version_id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>0),enabled boolean NOT NULL DEFAULT true,
 PRIMARY KEY(tenant_id,workflow_id),
 FOREIGN KEY(tenant_id,workflow_id) REFERENCES portal.workflows(tenant_id,workflow_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.workflow_versions(tenant_id,version_id));
ALTER TABLE portal.workflows OWNER TO ai_owner;
ALTER TABLE portal.workflow_versions OWNER TO ai_owner;
ALTER TABLE portal.workflow_heads OWNER TO ai_owner;
ALTER TABLE portal.workflows ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.workflows FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.workflow_versions ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.workflow_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.workflow_heads ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.workflow_heads FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.workflows,portal.workflow_versions,portal.workflow_heads FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.workflows,portal.workflow_versions TO ai_policy_executor;
GRANT UPDATE(status,decision_revision,decided_by,decided_at) ON portal.workflow_versions TO ai_policy_executor;
GRANT SELECT,INSERT ON portal.workflow_heads TO ai_policy_executor;
GRANT UPDATE(version_id,revision,enabled) ON portal.workflow_heads TO ai_policy_executor;
CREATE POLICY workflow_tenant ON portal.workflows TO ai_policy_executor USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_agent(tenant_id)) WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY workflow_version_tenant ON portal.workflow_versions TO ai_policy_executor USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_agent(tenant_id)) WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY workflow_head_tenant ON portal.workflow_heads TO ai_policy_executor USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_agent(tenant_id)) WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY audit_workflow_approval ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(session_user='ai_web' AND scope_kind='tenant'
 AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid
 AND security.can_read_agent(tenant_id) AND action IN ('workflow.submitted','workflow.approved','workflow.rejected','workflow.revoked'));

CREATE FUNCTION security.workflow_approval_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;v portal.workflow_versions%ROWTYPE;h portal.workflow_heads%ROWTYPE;
 v_workflow_id uuid;client_id uuid;ids uuid[];items jsonb;node jsonb;pub jsonb;tool text;digest text;
BEGIN
 IF p_action='catalog' THEN u:=security.run_authorize(p_session,p_tenant,false); ELSE u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action<>'list'); END IF;
 IF p_action IS NULL OR p_action NOT IN ('list','submit','approve','reject','revoke','catalog') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR p_mode NOT IN ('mock','real') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='catalog' THEN
  SELECT coalesce(jsonb_agg(jsonb_build_object('workflow_id',wv.workflow_id,'version_id',wv.version_id,'revision',wv.revision,'name',wv.definition->>'name','description',wv.definition->>'description','version_digest',wv.version_digest,'node_count',jsonb_array_length(wv.definition->'nodes')) ORDER BY wv.created_at DESC),'[]') INTO items FROM portal.workflow_heads wh JOIN portal.workflow_versions wv ON (wv.tenant_id,wv.version_id)=(wh.tenant_id,wh.version_id) WHERE wh.tenant_id=p_tenant AND wh.enabled AND wv.status='approved' AND (wv.audience='all' OR u=ANY(wv.member_ids));
  RETURN jsonb_build_object('items',items);
 END IF;
 IF p_action='list' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.version_id),'[]') INTO items FROM
  (SELECT wv.version_id,wv.workflow_id,wv.revision,wv.definition,wv.version_digest,wv.audience,wv.member_ids,v.expected_head_revision,wv.status,v.created_by,v.decided_by,wv.created_at,v.decided_at,
   coalesce((SELECT t.revision FROM portal.workflow_heads t WHERE t.tenant_id=wv.tenant_id AND t.workflow_id=wv.workflow_id),0) AS current_head_revision
   FROM portal.workflow_versions wv WHERE wv.tenant_id=p_tenant ORDER BY wv.created_at DESC,wv.version_id LIMIT 50)x;
  RETURN jsonb_build_object('items',items);
 END IF;
 IF p_action='submit' THEN
  IF p_body-ARRAY['workflow_id','client_request_id','definition','version_digest','audience','member_ids','expected_head_revision']<>'{}'
  OR jsonb_typeof(p_body->'definition') IS DISTINCT FROM 'object' OR jsonb_typeof(p_body->'member_ids') IS DISTINCT FROM 'array'
  OR coalesce(p_body->>'version_digest','') !~ '^[0-9a-f]{64}$' OR p_body->>'audience' NOT IN ('all','restricted')
  OR coalesce(p_body->>'expected_head_revision','') !~ '^(0|[1-9][0-9]*)$' OR octet_length(p_body::text)>32768
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  v_workflow_id:=(p_body->>'workflow_id')::uuid;client_id:=(p_body->>'client_request_id')::uuid;
  IF v_workflow_id IS NULL OR client_id IS NULL OR jsonb_typeof(p_body->'definition'->'nodes') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_body->'definition'->'nodes')>20 OR jsonb_typeof(p_body->'definition'->'edges') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_body->'definition'->'edges')>30 OR jsonb_array_length(p_body->'member_ids')>200
  OR (p_body->>'audience'='all' AND p_body->'member_ids'<>'[]') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT coalesce(array_agg(value::uuid),'{}') INTO ids FROM jsonb_array_elements_text(p_body->'member_ids');
  IF cardinality(ids)<>(SELECT count(DISTINCT x) FROM unnest(ids) x) OR EXISTS(SELECT 1 FROM unnest(ids) id WHERE NOT EXISTS
   (SELECT 1 FROM security.memberships m JOIN security.accounts a USING(user_id) WHERE m.tenant_id=p_tenant AND m.user_id=id AND m.active AND a.active))
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  -- Seal every current asset and Tool dependency at submission; approval/start repeat these checks.
  FOR node IN SELECT value FROM jsonb_array_elements(p_body->'definition'->'nodes') LOOP
   IF node->>'node_type'='llm' THEN
    pub:=security.published_asset_guard(p_session,p_tenant,(node->'config'->>'asset_id')::uuid,p_mode);
    IF pub->>'version_id' IS DISTINCT FROM node->'config'->>'version_id' OR (pub->>'publication_revision')::bigint IS DISTINCT FROM (node->'config'->>'publication_revision')::bigint
    THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   ELSIF node->>'node_type'='read_tool' THEN
    tool:=node->'config'->>'tool_id';digest:=node->'config'->>'version_digest';
    IF NOT EXISTS(SELECT 1 FROM portal.tool_heads t JOIN portal.tool_approvals a ON (a.tenant_id,a.request_id)=(t.tenant_id,t.request_id)
     WHERE t.tenant_id=p_tenant AND t.tool_id=tool AND t.enabled AND a.status='approved' AND a.descriptor->>'digest'=digest
     AND a.descriptor->>'mode'=p_mode AND (a.audience='all' OR u=ANY(a.member_ids))) THEN
     RAISE EXCEPTION 'TOOL_NOT_PERMITTED' USING ERRCODE='A0403';END IF;
   END IF;
  END LOOP;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':workflow-approval',0));
  SELECT * INTO v FROM portal.workflow_versions WHERE tenant_id=p_tenant AND created_by=u AND client_request_id=client_id;
  IF FOUND THEN
   IF v.workflow_id<>v_workflow_id OR v.definition<>p_body->'definition' OR v.version_digest<>p_body->>'version_digest' OR v.audience<>p_body->>'audience' OR to_jsonb(v.member_ids)<>p_body->'member_ids' OR v.expected_head_revision<>(p_body->>'expected_head_revision')::bigint
   THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN jsonb_build_object('version_id',v.version_id,'workflow_id',v.workflow_id,'revision',v.decision_revision,'version_revision',v.revision,'status',v.status,'replayed',true);
  END IF;
  SELECT * INTO h FROM portal.workflow_heads WHERE tenant_id=p_tenant AND portal.workflow_heads.workflow_id=v_workflow_id;
  IF coalesce(h.revision,0)<>(p_body->>'expected_head_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  INSERT INTO portal.workflows(tenant_id,workflow_id,owner_id,client_request_id) VALUES(p_tenant,v_workflow_id,u,client_id) ON CONFLICT(tenant_id,workflow_id) DO NOTHING;
  IF NOT FOUND AND NOT EXISTS(SELECT 1 FROM portal.workflows WHERE tenant_id=p_tenant AND portal.workflows.workflow_id=v_workflow_id AND owner_id=u) THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';END IF;
  INSERT INTO portal.workflow_versions(tenant_id,workflow_id,version_id,revision,created_by,client_request_id,definition,version_digest,audience,member_ids,expected_head_revision)
  VALUES(p_tenant,v_workflow_id,gen_random_uuid(),coalesce((SELECT max(revision)+1 FROM portal.workflow_versions WHERE tenant_id=p_tenant AND portal.workflow_versions.workflow_id=v_workflow_id),1),u,client_id,p_body->'definition',p_body->>'version_digest',p_body->>'audience',ids,(p_body->>'expected_head_revision')::bigint) RETURNING * INTO v;
 ELSE
  IF p_action='revoke' THEN
   IF p_body-ARRAY['workflow_id','expected_revision']<>'{}' OR coalesce(p_body->>'expected_revision','') !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
   UPDATE portal.workflow_heads SET enabled=false,revision=revision+1 WHERE tenant_id=p_tenant AND workflow_id=(p_body->>'workflow_id')::uuid AND revision=(p_body->>'expected_revision')::bigint RETURNING * INTO h;
   IF NOT FOUND THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(p_trace,'tenant',p_tenant,u,'workflow.revoked',h.version_id,'ok');
   RETURN jsonb_build_object('workflow_id',h.workflow_id,'enabled',false,'revision',h.revision);
  END IF;
  IF p_action NOT IN ('approve','reject') OR p_body-ARRAY['expected_revision']<>'{}' OR coalesce(p_body->>'expected_revision','') !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT * INTO v FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=p_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  IF v.created_by=u OR (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN' THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  IF v.status<>'pending' OR v.decision_revision<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  SELECT * INTO h FROM portal.workflow_heads WHERE tenant_id=p_tenant AND workflow_id=v.workflow_id FOR UPDATE;
  IF coalesce(h.revision,0)<>v.expected_head_revision THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  FOR node IN SELECT value FROM jsonb_array_elements(v.definition->'nodes') LOOP
   IF node->>'node_type'='llm' THEN
    pub:=security.published_asset_guard(p_session,p_tenant,(node->'config'->>'asset_id')::uuid,p_mode);
    IF pub->>'version_id' IS DISTINCT FROM node->'config'->>'version_id' OR (pub->>'publication_revision')::bigint IS DISTINCT FROM (node->'config'->>'publication_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   ELSIF node->>'node_type'='read_tool' THEN
    tool:=node->'config'->>'tool_id';digest:=node->'config'->>'version_digest';
    IF NOT EXISTS(SELECT 1 FROM portal.tool_heads t JOIN portal.tool_approvals a ON (a.tenant_id,a.request_id)=(t.tenant_id,t.request_id) WHERE t.tenant_id=p_tenant AND t.tool_id=tool AND t.enabled AND a.status='approved' AND a.descriptor->>'digest'=digest AND a.descriptor->>'mode'=p_mode AND (a.audience='all' OR u=ANY(a.member_ids))) THEN RAISE EXCEPTION 'TOOL_NOT_PERMITTED' USING ERRCODE='A0403';END IF;
   END IF;
  END LOOP;
  IF p_action='approve' THEN
   IF v.audience='restricted' AND EXISTS(SELECT 1 FROM unnest(v.member_ids) id WHERE NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts a USING(user_id) WHERE m.tenant_id=p_tenant AND m.user_id=id AND m.active AND a.active)) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   INSERT INTO portal.workflow_heads(tenant_id,workflow_id,version_id,revision,enabled) VALUES(p_tenant,v.workflow_id,v.version_id,coalesce(h.revision,0)+1,true)
   ON CONFLICT(tenant_id,workflow_id) DO UPDATE SET version_id=EXCLUDED.version_id,revision=EXCLUDED.revision,enabled=true;
  END IF;
  UPDATE portal.workflow_versions SET status=CASE WHEN p_action='approve' THEN 'approved' ELSE 'rejected' END,decision_revision=decision_revision+1,decided_by=u,decided_at=clock_timestamp() WHERE tenant_id=p_tenant AND version_id=p_id RETURNING * INTO v;
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(p_trace,'tenant',p_tenant,u,
 CASE p_action WHEN 'submit' THEN 'workflow.submitted' WHEN 'approve' THEN 'workflow.approved' ELSE 'workflow.rejected' END,v.version_id,'ok');
 RETURN jsonb_build_object('version_id',v.version_id,'workflow_id',v.workflow_id,'revision',v.decision_revision,'version_revision',v.revision,'status',v.status,'replayed',false);
END; $body$;
ALTER FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) TO ai_web;
