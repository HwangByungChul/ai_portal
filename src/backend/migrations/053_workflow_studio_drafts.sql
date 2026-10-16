-- Immutable, owner-scoped visual editor snapshots. Drafts are never executable.
CREATE TABLE portal.workflow_studio_drafts(
 tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
 draft_id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>0),
 owner_id uuid NOT NULL REFERENCES security.accounts(user_id),
 client_request_id uuid NOT NULL,
 request_digest text NOT NULL CHECK(request_digest ~ '^[0-9a-f]{64}$'),
 name text NOT NULL CHECK(char_length(btrim(name)) BETWEEN 1 AND 120),
 description text NOT NULL DEFAULT '' CHECK(char_length(description)<=500),
 graph jsonb NOT NULL CHECK(jsonb_typeof(graph)='object' AND graph ? 'nodes' AND graph ? 'edges'
  AND CASE WHEN jsonb_typeof(graph->'nodes')='array' THEN jsonb_array_length(graph->'nodes') BETWEEN 1 AND 20 ELSE false END
  AND CASE WHEN jsonb_typeof(graph->'edges')='array' THEN jsonb_array_length(graph->'edges')<=30 ELSE false END
  AND octet_length(graph::text)<=24576),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,draft_id,revision),
 UNIQUE(tenant_id,owner_id,client_request_id),
 FOREIGN KEY(tenant_id,owner_id) REFERENCES security.memberships(tenant_id,user_id));
CREATE INDEX workflow_studio_draft_owner ON portal.workflow_studio_drafts(tenant_id,owner_id,draft_id,revision DESC);
ALTER TABLE portal.workflow_studio_drafts OWNER TO ai_owner;
ALTER TABLE portal.workflow_studio_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.workflow_studio_drafts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.workflow_studio_drafts FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.workflow_studio_drafts TO ai_policy_executor;
CREATE POLICY workflow_studio_draft_owner ON portal.workflow_studio_drafts TO ai_policy_executor
 USING(session_user='ai_web' AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
  AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,owner_id))
 WITH CHECK(session_user='ai_web' AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
  AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,owner_id));
CREATE POLICY audit_workflow_studio_draft ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(
 session_user='ai_web' AND scope_kind='tenant' AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND action='workflow.studio_draft_saved'
 AND security.can_read_own_conversation(tenant_id,actor_id));

CREATE FUNCTION security.workflow_studio_draft_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,ops,pg_temp AS $$
DECLARE u uuid;current_rev bigint;rowdata portal.workflow_studio_drafts%ROWTYPE;prior portal.workflow_studio_drafts%ROWTYPE;
 result jsonb;digest text;expected bigint;
BEGIN
 IF p_action NOT IN ('list','detail','save') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action='save');
 IF p_action='list' THEN
  IF p_body<>'{}' OR p_id IS NOT NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(x)-ARRAY['tenant_id','owner_id','graph','request_digest','client_request_id']),'[]') INTO result
   FROM (SELECT DISTINCT ON(d.draft_id) d.* FROM portal.workflow_studio_drafts d WHERE d.tenant_id=p_tenant AND d.owner_id=u ORDER BY d.draft_id,d.revision DESC) x;
  RETURN jsonb_build_object('items',result);
 ELSIF p_action='detail' THEN
  IF p_body-ARRAY['revision']<>'{}' OR p_id IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT * INTO rowdata FROM portal.workflow_studio_drafts d WHERE d.tenant_id=p_tenant AND d.owner_id=u AND d.draft_id=p_id
   AND (p_body->>'revision' IS NULL OR d.revision=(p_body->>'revision')::bigint) ORDER BY d.revision DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  RETURN to_jsonb(rowdata)-ARRAY['tenant_id','owner_id','request_digest','client_request_id'];
 END IF;
 IF p_id IS NULL OR p_body-ARRAY['client_request_id','expected_revision','name','description','graph']<>'{}'
  OR jsonb_typeof(p_body->'client_request_id') IS DISTINCT FROM 'string'
  OR jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number'
  OR jsonb_typeof(p_body->'name') IS DISTINCT FROM 'string' OR jsonb_typeof(p_body->'description') IS DISTINCT FROM 'string'
  OR jsonb_typeof(p_body->'graph') IS DISTINCT FROM 'object' OR char_length(btrim(p_body->>'name')) NOT BETWEEN 1 AND 120
  OR char_length(p_body->>'description')>500 OR octet_length((p_body->'graph')::text)>24576
  OR (CASE WHEN jsonb_typeof(p_body->'graph'->'nodes')='array' THEN jsonb_array_length(p_body->'graph'->'nodes') BETWEEN 1 AND 20 ELSE false END) IS NOT TRUE
  OR (CASE WHEN jsonb_typeof(p_body->'graph'->'edges')='array' THEN jsonb_array_length(p_body->'graph'->'edges')<=30 ELSE false END) IS NOT TRUE THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 expected:=(p_body->>'expected_revision')::bigint;
 IF expected<0 OR expected>9223372036854775806 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 digest:=encode(sha256(convert_to((p_body-ARRAY['client_request_id','expected_revision'])::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||p_id::text||':workflow-studio-draft',0));
 SELECT * INTO prior FROM portal.workflow_studio_drafts WHERE tenant_id=p_tenant AND owner_id=u AND client_request_id=(p_body->>'client_request_id')::uuid;
 IF FOUND THEN
  IF prior.draft_id<>p_id OR prior.request_digest<>digest THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  RETURN to_jsonb(prior)-ARRAY['tenant_id','owner_id','request_digest','client_request_id']||jsonb_build_object('replayed',true);
 END IF;
 SELECT coalesce(max(revision),0) INTO current_rev FROM portal.workflow_studio_drafts WHERE tenant_id=p_tenant AND owner_id=u AND draft_id=p_id;
 IF current_rev<>expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 INSERT INTO portal.workflow_studio_drafts(tenant_id,draft_id,revision,owner_id,client_request_id,request_digest,name,description,graph)
  VALUES(p_tenant,p_id,expected+1,u,(p_body->>'client_request_id')::uuid,digest,btrim(p_body->>'name'),p_body->>'description',p_body->'graph') RETURNING * INTO rowdata;
 result:=to_jsonb(rowdata)-ARRAY['tenant_id','owner_id','request_digest','client_request_id'];
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
  VALUES(p_trace,'tenant',p_tenant,u,'workflow.studio_draft_saved',p_id,'ok',jsonb_build_object('revision',expected+1));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401';END IF;
 RETURN result||jsonb_build_object('replayed',false);
END;$$;
ALTER FUNCTION security.workflow_studio_draft_control(uuid,uuid,text,uuid,jsonb,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.workflow_studio_draft_control(uuid,uuid,text,uuid,jsonb,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.workflow_studio_draft_control(uuid,uuid,text,uuid,jsonb,uuid) TO ai_web;
