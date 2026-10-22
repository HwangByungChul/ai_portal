-- Revision-bound review requests for dynamic MCP tool registrations.
-- A review head is not an execution permit: risk_class remains unclassified
-- until a separate risk-policy implementation can establish a safe policy.
CREATE FUNCTION security.mcp_tool_approval_control(
 p_session uuid,p_tenant uuid,p_action text,p_tool text,p_client uuid,
 p_audience text,p_members jsonb,p_expected_head bigint,p_mode text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog,security,portal,pg_temp AS $body$
DECLARE u uuid; spec jsonb; descriptor jsonb; digest_value text; ids uuid[]; existing portal.tool_approvals%ROWTYPE; rev bigint;
BEGIN
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action='submit');
 IF p_action NOT IN ('describe','submit') OR p_mode NOT IN ('mock','real') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_tool IS NULL OR p_tool !~ '^[a-zA-Z][a-zA-Z0-9_-]{1,99}$'
    OR p_tool IN ('financial_product_lookup','kb_rule_query','data_view_reader') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT jsonb_build_object('tool_id',d.tool_id,'revision_number',v.revision_number,
   'name',d.name,'description',d.description,'source_type',d.source_type,
   'input_schema',v.mcp_tool_spec->'inputSchema','mode',p_mode,
   'risk_class','unclassified','approval_scope','registration_review_only')
 INTO descriptor
 FROM portal.mcp_tool_definitions d JOIN LATERAL (
   SELECT revision_number,mcp_tool_spec FROM portal.mcp_tool_versions
   WHERE tenant_id=d.tenant_id AND tool_id=d.tool_id ORDER BY revision_number DESC LIMIT 1
 ) v ON true
 WHERE d.tenant_id=p_tenant AND d.tool_id=p_tool AND d.enabled;
 IF descriptor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 digest_value:=encode(sha256(convert_to(descriptor::text,'UTF8')),'hex');
 descriptor:=descriptor||jsonb_build_object('digest',digest_value);
 IF p_action='describe' THEN RETURN jsonb_build_object('descriptor',descriptor,'head_revision',coalesce((SELECT revision FROM portal.tool_heads WHERE tenant_id=p_tenant AND tool_id=p_tool),0),'execution_ready',false); END IF;
 IF p_client IS NULL OR p_audience NOT IN ('all','restricted') OR jsonb_typeof(p_members) IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_members)>200 OR p_expected_head IS NULL OR p_expected_head<0
  OR (p_audience='all' AND p_members<>'[]'::jsonb) THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 SELECT coalesce(array_agg(value::uuid),'{}') INTO ids FROM jsonb_array_elements_text(p_members);
 IF cardinality(ids)<>(SELECT count(DISTINCT x) FROM unnest(ids) x) OR EXISTS(
   SELECT 1 FROM unnest(ids) id WHERE NOT EXISTS(
    SELECT 1 FROM security.memberships m JOIN security.accounts a USING(user_id)
    WHERE m.tenant_id=p_tenant AND m.user_id=id AND m.active AND a.active)) THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':tool-admin',0));
 SELECT * INTO existing FROM portal.tool_approvals WHERE tenant_id=p_tenant AND requester_id=u AND client_request_id=p_client;
 IF FOUND THEN
  IF existing.tool_id<>p_tool OR existing.descriptor<>descriptor OR existing.audience<>p_audience OR existing.member_ids<>ids OR existing.expected_head_revision<>p_expected_head THEN
   RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  RETURN jsonb_build_object('request_id',existing.request_id,'status',existing.status,'revision',existing.revision,'replayed',true,'execution_ready',false);
 END IF;
 SELECT coalesce(revision,0) INTO rev FROM portal.tool_heads WHERE tenant_id=p_tenant AND tool_id=p_tool;
 IF coalesce(rev,0)<>p_expected_head THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 INSERT INTO portal.tool_approvals(tenant_id,request_id,requester_id,client_request_id,tool_id,descriptor,request_body,audience,member_ids,expected_head_revision)
 VALUES(p_tenant,gen_random_uuid(),u,p_client,p_tool,descriptor,
  jsonb_build_object('client_request_id',p_client,'tool_id',p_tool,'descriptor',descriptor,'audience',p_audience,'member_ids',p_members,'expected_head_revision',p_expected_head),
  p_audience,ids,p_expected_head)
 RETURNING * INTO existing;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result)
 VALUES(gen_random_uuid(),'tenant',p_tenant,u,'tool.dynamic_review_submitted',existing.request_id,'ok');
 RETURN jsonb_build_object('request_id',existing.request_id,'status',existing.status,'revision',existing.revision,'replayed',false,'execution_ready',false);
END;$body$;
ALTER FUNCTION security.mcp_tool_approval_control(uuid,uuid,text,text,uuid,text,jsonb,bigint,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.mcp_tool_approval_control(uuid,uuid,text,text,uuid,text,jsonb,bigint,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.mcp_tool_approval_control(uuid,uuid,text,text,uuid,text,jsonb,bigint,text) TO ai_web;
CREATE POLICY audit_dynamic_tool_review ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(
 session_user='ai_web' AND scope_kind='tenant' AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_agent(tenant_id)
 AND action='tool.dynamic_review_submitted');

CREATE FUNCTION portal.reject_unclassified_dynamic_tool_approval() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,portal,pg_temp AS $guard$
BEGIN
 IF NEW.status='approved' AND NEW.descriptor->>'approval_scope'='registration_review_only'
    AND NEW.descriptor->>'risk_class'='unclassified' THEN
  RAISE EXCEPTION 'TOOL_RISK_UNCLASSIFIED' USING ERRCODE='A0403';
 END IF;
 RETURN NEW;
END;$guard$;
ALTER FUNCTION portal.reject_unclassified_dynamic_tool_approval() OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION portal.reject_unclassified_dynamic_tool_approval() FROM PUBLIC,ai_web,ai_index,ai_meter;
CREATE TRIGGER tool_approval_risk_gate BEFORE UPDATE OF status ON portal.tool_approvals
 FOR EACH ROW EXECUTE FUNCTION portal.reject_unclassified_dynamic_tool_approval();
