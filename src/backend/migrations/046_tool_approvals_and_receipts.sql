-- W4: additive tenant approvals and owner receipts; no existing cache backfill.
CREATE TABLE portal.tool_approvals (
 tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id), request_id uuid NOT NULL,
 requester_id uuid NOT NULL REFERENCES security.accounts(user_id), client_request_id uuid NOT NULL,
 tool_id text NOT NULL, descriptor jsonb NOT NULL, request_body jsonb NOT NULL,
 audience text NOT NULL CHECK(audience IN ('all','restricted')), member_ids uuid[] NOT NULL,
 expected_head_revision bigint NOT NULL CHECK(expected_head_revision>=0),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 revision bigint NOT NULL DEFAULT 1, decided_by uuid REFERENCES security.accounts(user_id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), decided_at timestamptz,
 PRIMARY KEY(tenant_id,request_id), UNIQUE(tenant_id,requester_id,client_request_id)
);
CREATE TABLE portal.tool_heads (
 tenant_id uuid NOT NULL, tool_id text NOT NULL, request_id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>0), enabled boolean NOT NULL,
 PRIMARY KEY(tenant_id,tool_id), FOREIGN KEY(tenant_id,request_id) REFERENCES portal.tool_approvals(tenant_id,request_id)
);
CREATE TABLE portal.tool_receipts (
 tenant_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES security.accounts(user_id), client_request_id uuid NOT NULL,
 receipt_id uuid NOT NULL DEFAULT gen_random_uuid(), tool_id text NOT NULL, approval_id uuid NOT NULL,
 version_digest text NOT NULL, arguments_hash text NOT NULL,
 state text NOT NULL DEFAULT 'accepted' CHECK(state IN ('accepted','dispatched','succeeded','failed','unknown')),
 revision bigint NOT NULL DEFAULT 1, dispatch_token uuid, lease_until timestamptz,
 result jsonb, error_code text, created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,user_id,client_request_id), UNIQUE(tenant_id,receipt_id),
 FOREIGN KEY(tenant_id,approval_id) REFERENCES portal.tool_approvals(tenant_id,request_id)
);
ALTER TABLE portal.tool_approvals OWNER TO ai_owner;
ALTER TABLE portal.tool_heads OWNER TO ai_owner;
ALTER TABLE portal.tool_receipts OWNER TO ai_owner;
ALTER TABLE portal.tool_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.tool_approvals FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.tool_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.tool_heads FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.tool_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.tool_receipts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.tool_approvals,portal.tool_heads,portal.tool_receipts FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.tool_approvals TO ai_policy_executor;
GRANT UPDATE(status,revision,decided_by,decided_at) ON portal.tool_approvals TO ai_policy_executor;
GRANT SELECT,INSERT ON portal.tool_heads,portal.tool_receipts TO ai_policy_executor;
GRANT UPDATE(request_id,revision,enabled) ON portal.tool_heads TO ai_policy_executor;
GRANT UPDATE(state,revision,dispatch_token,lease_until,result,error_code,updated_at) ON portal.tool_receipts TO ai_policy_executor;
CREATE POLICY tool_approval_tenant ON portal.tool_approvals TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_agent(tenant_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY tool_head_tenant ON portal.tool_heads TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_agent(tenant_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY tool_receipt_owner ON portal.tool_receipts TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,user_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,user_id));
CREATE POLICY audit_tool_runtime ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(
 session_user='ai_web' AND scope_kind='tenant' AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_agent(tenant_id)
 AND action IN ('tool.submitted','tool.approved','tool.rejected','tool.revoked','tool.accepted','tool.dispatched','tool.succeeded','tool.failed','tool.unknown'));

CREATE FUNCTION security.tool_approval_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE u uuid; a portal.tool_approvals%ROWTYPE; h portal.tool_heads%ROWTYPE; ids uuid[]; items jsonb; cid uuid; tool text;
BEGIN
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action<>'list');
 IF p_action NOT IN ('list','submit','approve','reject','revoke') OR p_action IS NULL OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='list' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.request_id),'[]') INTO items FROM
  (SELECT request_id,tool_id,descriptor,audience,member_ids,expected_head_revision,status,revision,requester_id,decided_by,created_at,decided_at,coalesce((SELECT t.revision FROM portal.tool_heads t WHERE t.tenant_id=tool_approvals.tenant_id AND t.tool_id=tool_approvals.tool_id),0) AS current_head_revision FROM portal.tool_approvals WHERE tenant_id=p_tenant ORDER BY created_at DESC,request_id LIMIT 50) x;
  RETURN jsonb_build_object('items',items);
 END IF;
 IF p_action='submit' THEN
  IF p_body-ARRAY['client_request_id','descriptor','audience','member_ids','expected_head_revision']<>'{}'
  OR jsonb_typeof(p_body->'descriptor') IS DISTINCT FROM 'object' OR p_body->>'audience' IS NULL OR p_body->>'audience' NOT IN ('all','restricted')
  OR jsonb_typeof(p_body->'member_ids') IS DISTINCT FROM 'array' OR coalesce(p_body->>'expected_head_revision','') !~ '^(0|[1-9][0-9]*)$'
  OR coalesce(p_body->'descriptor'->>'digest','') !~ '^[0-9a-f]{64}$' OR coalesce(p_body->'descriptor'->>'mode','') NOT IN ('mock','real')
  OR coalesce(p_body->'descriptor'->>'timeout_seconds','') !~ '^([1-9]|[12][0-9]|30)$'
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  tool:=p_body->'descriptor'->>'tool_id';cid:=(p_body->>'client_request_id')::uuid;
  IF cid IS NULL OR tool IS NULL OR tool NOT IN ('financial_product_lookup','kb_rule_query','data_view_reader') OR jsonb_array_length(p_body->'member_ids')>200
  OR (p_body->>'audience'='all' AND p_body->'member_ids'<>'[]')
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT coalesce(array_agg(value::uuid),'{}') INTO ids FROM jsonb_array_elements_text(p_body->'member_ids');
  IF cardinality(ids)<>(SELECT count(DISTINCT x) FROM unnest(ids) x) OR EXISTS(SELECT 1 FROM unnest(ids) id WHERE NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts c USING(user_id) WHERE m.tenant_id=p_tenant AND m.user_id=id AND m.active AND c.active))
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':tool-admin',0));
  SELECT * INTO a FROM portal.tool_approvals WHERE tenant_id=p_tenant AND requester_id=u AND client_request_id=cid;
  IF FOUND THEN
   IF a.request_body<>p_body THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN jsonb_build_object('request_id',a.request_id,'status',a.status,'revision',a.revision,'replayed',true);
  END IF;
  SELECT * INTO h FROM portal.tool_heads WHERE tenant_id=p_tenant AND tool_id=tool;
  IF coalesce(h.revision,0)<>(p_body->>'expected_head_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  INSERT INTO portal.tool_approvals(tenant_id,request_id,requester_id,client_request_id,tool_id,descriptor,request_body,audience,member_ids,expected_head_revision)
  VALUES(p_tenant,gen_random_uuid(),u,cid,tool,p_body->'descriptor',p_body,p_body->>'audience',ids,(p_body->>'expected_head_revision')::bigint) RETURNING * INTO a;
 ELSE
  IF p_body-ARRAY['expected_revision','tool_id']<>'{}' OR coalesce(p_body->>'expected_revision','') !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':tool-admin',0));
  IF p_action='revoke' THEN
   UPDATE portal.tool_heads SET enabled=false,revision=revision+1 WHERE tenant_id=p_tenant AND tool_id=p_body->>'tool_id' AND revision=(p_body->>'expected_revision')::bigint RETURNING * INTO h;
   IF NOT FOUND THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(p_trace,'tenant',p_tenant,u,'tool.revoked',h.request_id,'ok');
   RETURN jsonb_build_object('enabled',h.enabled,'revision',h.revision);
  END IF;
  SELECT * INTO a FROM portal.tool_approvals WHERE tenant_id=p_tenant AND request_id=p_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  IF a.requester_id=u OR (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN' THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  IF a.status<>'pending' THEN
   IF a.status=(CASE WHEN p_action='approve' THEN 'approved' ELSE 'rejected' END) AND a.revision=(p_body->>'expected_revision')::bigint+1 THEN
    RETURN jsonb_build_object('request_id',a.request_id,'status',a.status,'revision',a.revision,'replayed',true);
   END IF;
   RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
  END IF;
  IF a.revision<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  IF p_action='approve' THEN
   SELECT * INTO h FROM portal.tool_heads WHERE tenant_id=p_tenant AND tool_id=a.tool_id FOR UPDATE;
   IF coalesce(h.revision,0)<>a.expected_head_revision THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   INSERT INTO portal.tool_heads(tenant_id,tool_id,request_id,revision,enabled) VALUES(p_tenant,a.tool_id,a.request_id,coalesce(h.revision,0)+1,true)
   ON CONFLICT(tenant_id,tool_id) DO UPDATE SET request_id=EXCLUDED.request_id,revision=EXCLUDED.revision,enabled=true;
  END IF;
  UPDATE portal.tool_approvals SET status=CASE WHEN p_action='approve' THEN 'approved' ELSE 'rejected' END,revision=revision+1,decided_by=u,decided_at=clock_timestamp() WHERE tenant_id=p_tenant AND request_id=p_id RETURNING * INTO a;
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result)
 VALUES(p_trace,'tenant',p_tenant,u,CASE p_action WHEN 'submit' THEN 'tool.submitted' WHEN 'approve' THEN 'tool.approved' ELSE 'tool.rejected' END,a.request_id,'ok');
 RETURN jsonb_build_object('request_id',a.request_id,'status',a.status,'revision',a.revision,'replayed',false);
END; $body$;

CREATE FUNCTION security.tool_execution_control(p_session uuid,p_tenant uuid,p_action text,p_tool text,p_digest text,p_mode text,p_client uuid,p_args jsonb,p_token uuid,p_result jsonb,p_error text,p_period date,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE u uuid;a portal.tool_approvals%ROWTYPE;r portal.tool_receipts%ROWTYPE;h text;claimed boolean:=false;changed boolean:=false;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,p_action<>'ready');
 IF p_action IS NULL OR p_action NOT IN ('ready','admit','dispatch','finish','read') OR p_mode NOT IN ('mock','real') OR p_digest IS NULL OR p_period IS NULL
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 -- Honor the configured period/mode platform stop, including stop latch.
 PERFORM budget_id FROM ops.project_budget WHERE period=p_period AND mode=p_mode FOR SHARE;
 IF NOT FOUND OR EXISTS(SELECT 1 FROM ops.project_budget WHERE period=p_period AND mode=p_mode AND (stopped OR stop_latch))
 OR EXISTS(SELECT 1 FROM ops.tenant_budgets t JOIN ops.project_budget b USING(budget_id) WHERE t.tenant_id=p_tenant AND b.period=p_period AND b.mode=p_mode AND t.stopped) THEN
  IF p_action='ready' THEN RETURN jsonb_build_object('execution_ready',false);END IF;
  RAISE EXCEPTION 'TOOL_NOT_PERMITTED' USING ERRCODE='A0403';
 END IF;
 -- A shared head lock fences a concurrent revocation/publication change during this transaction.
 PERFORM tool_id FROM portal.tool_heads WHERE tenant_id=p_tenant AND tool_id=p_tool FOR SHARE;
 SELECT q.* INTO a FROM portal.tool_heads t JOIN portal.tool_approvals q ON (q.tenant_id,q.request_id)=(t.tenant_id,t.request_id)
 WHERE t.tenant_id=p_tenant AND t.tool_id=p_tool AND t.enabled AND q.status='approved'
 AND q.descriptor->>'digest'=p_digest AND q.descriptor->>'mode'=p_mode AND (q.audience='all' OR u=ANY(q.member_ids));
 IF p_action='ready' THEN RETURN jsonb_build_object('execution_ready',FOUND);END IF;
 IF NOT FOUND THEN RAISE EXCEPTION 'TOOL_NOT_PERMITTED' USING ERRCODE='A0403';END IF;
 IF p_client IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||':tool-capacity',0));
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||p_client::text,0));
 SELECT * INTO r FROM portal.tool_receipts WHERE tenant_id=p_tenant AND user_id=u AND client_request_id=p_client FOR UPDATE;
 IF p_action='admit' THEN
  IF jsonb_typeof(p_args) IS DISTINCT FROM 'object' OR octet_length(p_args::text)>32768 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  h:=encode(sha256(convert_to(jsonb_build_object('tool',p_tool,'digest',p_digest,'args',p_args)::text,'UTF8')),'hex');
  IF r.receipt_id IS NOT NULL THEN
   IF r.arguments_hash<>h THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  ELSE
   IF (SELECT count(*) FROM portal.tool_receipts WHERE tenant_id=p_tenant AND user_id=u AND (state='accepted' OR state='dispatched' AND lease_until>clock_timestamp()))>=20 THEN
    RAISE EXCEPTION 'TOOL_QUEUE_LIMIT' USING ERRCODE='A0429';END IF;
   INSERT INTO portal.tool_receipts(tenant_id,user_id,client_request_id,tool_id,approval_id,version_digest,arguments_hash)
   VALUES(p_tenant,u,p_client,p_tool,a.request_id,p_digest,h) RETURNING * INTO r;changed:=true;
  END IF;
 ELSE
  IF r.receipt_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 END IF;
 IF r.tool_id<>p_tool OR r.version_digest<>p_digest OR r.approval_id<>a.request_id THEN RAISE EXCEPTION 'TOOL_NOT_PERMITTED' USING ERRCODE='A0403';END IF;
 IF r.state='dispatched' AND clock_timestamp()>=r.lease_until THEN
  UPDATE portal.tool_receipts SET state='unknown',error_code='TOOL_RESULT_UNKNOWN',revision=revision+1,updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND user_id=u AND client_request_id=p_client RETURNING * INTO r;changed:=true;
 END IF;
 IF p_action='dispatch' AND r.state='accepted' THEN
  IF p_token IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  UPDATE portal.tool_receipts SET state='dispatched',dispatch_token=p_token,lease_until=clock_timestamp()+make_interval(secs=>(a.descriptor->>'timeout_seconds')::int+5),revision=revision+1,updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND user_id=u AND client_request_id=p_client RETURNING * INTO r;
  claimed:=true;changed:=true;
 ELSIF p_action='finish' AND r.state='dispatched' THEN
  IF p_token IS NULL OR p_token IS DISTINCT FROM r.dispatch_token OR p_error IS NULL
  OR p_error NOT IN ('','TOOL_RESULT_UNKNOWN','TOOL_OUTPUT_BLOCKED','TOOL_OUTPUT_INVALID') OR p_result IS NULL OR octet_length(p_result::text)>32768
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  UPDATE portal.tool_receipts SET state=CASE WHEN p_error='' THEN 'succeeded' WHEN p_error='TOOL_RESULT_UNKNOWN' THEN 'unknown' ELSE 'failed' END,
   result=CASE WHEN p_error='' THEN p_result ELSE NULL END,error_code=NULLIF(p_error,''),revision=revision+1,updated_at=clock_timestamp()
  WHERE tenant_id=p_tenant AND user_id=u AND client_request_id=p_client RETURNING * INTO r;changed:=true;
 END IF;
 IF changed THEN
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result)
  VALUES(p_trace,'tenant',p_tenant,u,'tool.'||r.state,r.receipt_id,'ok');
 END IF;
 RETURN jsonb_build_object('receipt_id',r.receipt_id,'client_request_id',r.client_request_id,'tool_id',r.tool_id,'approval_id',r.approval_id,'version_digest',r.version_digest,'state',r.state,'revision',r.revision,'result',r.result,'error_code',r.error_code,'claimed',claimed);
END; $body$;
ALTER FUNCTION security.tool_approval_control(uuid,uuid,text,uuid,jsonb,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.tool_execution_control(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.tool_approval_control(uuid,uuid,text,uuid,jsonb,uuid),security.tool_execution_control(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.tool_approval_control(uuid,uuid,text,uuid,jsonb,uuid),security.tool_execution_control(uuid,uuid,text,text,text,text,uuid,jsonb,uuid,jsonb,text,date,uuid) TO ai_web;
