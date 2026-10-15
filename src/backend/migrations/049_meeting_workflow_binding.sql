-- Meeting contract is sealed at submission; no retroactive assignment to old versions.
ALTER TABLE portal.workflow_versions ADD COLUMN use_case_id text,ADD COLUMN use_case_digest text,ADD COLUMN use_case_revision bigint;
ALTER TABLE portal.workflow_versions ADD CONSTRAINT workflow_case_seal CHECK((use_case_id IS NULL AND use_case_digest IS NULL AND use_case_revision IS NULL) OR (use_case_id='AGENT_03' AND use_case_digest IS NOT NULL AND use_case_revision IS NOT NULL AND use_case_digest ~ '^[0-9a-f]{64}$' AND use_case_revision>=0));
GRANT UPDATE(use_case_id,use_case_digest,use_case_revision) ON portal.workflow_versions TO ai_policy_executor;
CREATE TABLE portal.use_case_heads(
 tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),use_case_id text NOT NULL CHECK(use_case_id='AGENT_03'),
 version_id uuid NOT NULL,revision bigint NOT NULL CHECK(revision>0),PRIMARY KEY(tenant_id,use_case_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.workflow_versions(tenant_id,version_id));
ALTER TABLE portal.use_case_heads OWNER TO ai_owner;
ALTER TABLE portal.use_case_heads ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.use_case_heads FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.use_case_heads FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT,UPDATE ON portal.use_case_heads TO ai_policy_executor;
CREATE POLICY case_head_scope ON portal.use_case_heads TO ai_policy_executor USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_agent(tenant_id)) WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id));
CREATE FUNCTION portal.workflow_case_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF OLD.use_case_id IS NOT NULL AND ROW(NEW.use_case_id,NEW.use_case_digest,NEW.use_case_revision) IS DISTINCT FROM ROW(OLD.use_case_id,OLD.use_case_digest,OLD.use_case_revision) OR OLD.use_case_id IS NULL AND NEW.use_case_id IS NOT NULL AND OLD.status<>'pending' THEN RAISE EXCEPTION 'CASE_IMMUTABLE' USING ERRCODE='23514';END IF;
 RETURN NEW;
END;$$;
ALTER FUNCTION portal.workflow_case_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.workflow_case_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter;
CREATE TRIGGER workflow_case_immutable BEFORE UPDATE ON portal.workflow_versions FOR EACH ROW EXECUTE FUNCTION portal.workflow_case_immutable();

ALTER FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) RENAME TO workflow_approval_control_v048;
REVOKE ALL ON FUNCTION security.workflow_approval_control_v048(uuid,uuid,text,uuid,jsonb,text,uuid) FROM ai_web;
CREATE FUNCTION security.workflow_approval_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_trace uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;vw portal.workflow_versions%ROWTYPE;head bigint;item jsonb;items jsonb:='[]';clean jsonb;bound text;
BEGIN
 clean:=p_body-ARRAY['use_case_id','expected_use_case_revision','meeting_digest'];bound:=p_body->>'use_case_id';
 IF bound IS NOT NULL AND (p_action<>'submit' OR bound<>'AGENT_03' OR coalesce(p_body->>'meeting_digest','') !~ '^[0-9a-f]{64}$' OR coalesce(p_body->>'expected_use_case_revision','') !~ '^(0|[1-9][0-9]*)$') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action IN ('submit','approve') THEN
  PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':meeting-head',0));
  IF p_action='approve' THEN
   SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=p_id;
   IF vw.use_case_id IS NOT NULL AND vw.status='pending' THEN
    SELECT revision INTO head FROM portal.use_case_heads WHERE tenant_id=p_tenant AND use_case_id=vw.use_case_id FOR UPDATE;
    IF coalesce(head,0)<>vw.use_case_revision OR vw.use_case_digest IS DISTINCT FROM p_body->>'meeting_digest' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   END IF;
  END IF;
 END IF;
 data:=security.workflow_approval_control_v048(p_session,p_tenant,p_action,p_id,clean,p_mode,p_trace);
 IF p_action='submit' THEN
  SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=(data->>'version_id')::uuid FOR UPDATE;
  IF (data->>'replayed')::boolean THEN
   IF vw.use_case_id IS DISTINCT FROM bound OR bound IS NOT NULL AND (vw.use_case_digest IS DISTINCT FROM p_body->>'meeting_digest' OR vw.use_case_revision IS DISTINCT FROM (p_body->>'expected_use_case_revision')::bigint) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  ELSIF bound IS NOT NULL THEN
   SELECT revision INTO head FROM portal.use_case_heads WHERE tenant_id=p_tenant AND use_case_id=bound;
   IF coalesce(head,0)<>(p_body->>'expected_use_case_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   IF EXISTS(SELECT 1 FROM jsonb_array_elements(vw.definition->'nodes') n WHERE n->>'node_type'='read_tool') OR (SELECT count(*) FROM jsonb_array_elements(vw.definition->'nodes') n WHERE n->>'node_type'='llm')<>1
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(vw.definition->'nodes') n WHERE n->>'node_type'='output' AND (n->'config'->'source'->>'node_id' IS DISTINCT FROM (SELECT m->>'node_id' FROM jsonb_array_elements(vw.definition->'nodes') m WHERE m->>'node_type'='llm') OR n->'config'->'source'->'path' IS DISTINCT FROM '["text"]'::jsonb))
   OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(vw.definition->'nodes') n CROSS JOIN LATERAL jsonb_each(coalesce(n->'config'->'values','{}'::jsonb)) b WHERE n->>'node_type'='llm' AND jsonb_typeof(b.value)='object' AND b.value->>'node_id'=(SELECT i->>'node_id' FROM jsonb_array_elements(vw.definition->'nodes') i WHERE i->>'node_type'='input') AND coalesce(b.value->'path','[]'::jsonb)='[]'::jsonb) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
   UPDATE portal.workflow_versions SET use_case_id=bound,use_case_digest=p_body->>'meeting_digest',use_case_revision=(p_body->>'expected_use_case_revision')::bigint WHERE tenant_id=p_tenant AND version_id=vw.version_id;
  END IF;
 ELSIF p_action='approve' AND vw.use_case_id IS NOT NULL AND NOT (data->>'replayed')::boolean THEN
  INSERT INTO portal.use_case_heads(tenant_id,use_case_id,version_id,revision) VALUES(p_tenant,vw.use_case_id,vw.version_id,coalesce(head,0)+1)
  ON CONFLICT(tenant_id,use_case_id) DO UPDATE SET version_id=EXCLUDED.version_id,revision=EXCLUDED.revision;
 ELSIF p_action IN ('list','catalog') THEN
  FOR item IN SELECT value FROM jsonb_array_elements(data->'items') LOOP
   SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=(item->>'version_id')::uuid;
   items:=items||jsonb_build_array(item||jsonb_build_object('use_case_id',vw.use_case_id,'use_case_digest',vw.use_case_digest,'expected_use_case_revision',vw.use_case_revision));
  END LOOP;data:=jsonb_build_object('items',items);
 END IF;RETURN data;
END;$$;

ALTER FUNCTION security.workflow_version_guard(uuid,uuid,uuid,text,text,date) RENAME TO workflow_version_guard_v048;
REVOKE ALL ON FUNCTION security.workflow_version_guard_v048(uuid,uuid,uuid,text,text,date) FROM ai_web;
CREATE FUNCTION security.workflow_version_guard(p_session uuid,p_tenant uuid,p_version uuid,p_mode text,p_code text,p_period date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;vw portal.workflow_versions%ROWTYPE;
BEGIN
 data:=security.workflow_version_guard_v048(p_session,p_tenant,p_version,p_mode,p_code,p_period);
 SELECT * INTO vw FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=p_version;
 IF vw.use_case_id IS NOT NULL THEN
  PERFORM version_id FROM portal.use_case_heads WHERE tenant_id=p_tenant AND use_case_id=vw.use_case_id AND version_id=p_version FOR SHARE;
  IF NOT FOUND OR (SELECT effective_role FROM security.current_membership(p_session,p_tenant)) NOT IN ('USER','PADMIN') THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401';END IF;
 END IF;
 RETURN data||jsonb_build_object('use_case_id',vw.use_case_id,'use_case_digest',vw.use_case_digest);
END;$$;

CREATE FUNCTION security.meeting_binding(p_session uuid,p_tenant uuid,p_run uuid,p_mode text,p_code text,p_period date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE vw portal.workflow_versions%ROWTYPE;data jsonb;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_run IS NULL THEN
  SELECT v.* INTO vw FROM portal.use_case_heads h JOIN portal.workflow_versions v ON (v.tenant_id,v.version_id)=(h.tenant_id,h.version_id) WHERE h.tenant_id=p_tenant AND h.use_case_id='AGENT_03';
  IF NOT FOUND THEN RETURN NULL;END IF;
  PERFORM security.workflow_version_guard(p_session,p_tenant,vw.version_id,p_mode,p_code,p_period);
 ELSE
  SELECT v.* INTO vw FROM portal.workflow_runs r JOIN portal.workflow_versions v ON (v.tenant_id,v.version_id)=(r.tenant_id,r.version_id) WHERE r.tenant_id=p_tenant AND r.run_id=p_run AND r.owner_id=NULLIF(current_setting('app.user_id'),'')::uuid;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  IF vw.use_case_id IS NULL THEN RETURN NULL;END IF;
 END IF;
 RETURN jsonb_build_object('use_case_id',vw.use_case_id,'version_id',vw.version_id,'use_case_digest',vw.use_case_digest,'input_key',(SELECT n->'config'->>'input_key' FROM jsonb_array_elements(vw.definition->'nodes') n WHERE n->>'node_type'='input'));
END;$$;
ALTER FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_version_guard(uuid,uuid,uuid,text,text,date) OWNER TO ai_policy_executor;
ALTER FUNCTION security.meeting_binding(uuid,uuid,uuid,text,text,date) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid),security.workflow_version_guard(uuid,uuid,uuid,text,text,date),security.meeting_binding(uuid,uuid,uuid,text,text,date) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid),security.meeting_binding(uuid,uuid,uuid,text,text,date) TO ai_web;
