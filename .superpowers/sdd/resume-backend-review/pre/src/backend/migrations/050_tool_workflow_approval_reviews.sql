-- Additive review ledger; historical decisions remain without comments.
CREATE TABLE portal.approval_reviews(
 tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),review_id uuid NOT NULL DEFAULT gen_random_uuid(),
 kind text NOT NULL CHECK(kind IN ('tool','workflow')),target_id uuid NOT NULL,actor_id uuid NOT NULL REFERENCES security.accounts(user_id),
 action text NOT NULL CHECK(action IN ('approve','reject','revoke')),expected_revision bigint NOT NULL,
 comment text NOT NULL CHECK(char_length(btrim(comment)) BETWEEN 1 AND 500 AND comment=btrim(comment)),
 result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,review_id),
 UNIQUE(tenant_id,kind,target_id,action,expected_revision));
ALTER TABLE portal.approval_reviews OWNER TO ai_owner;
ALTER TABLE portal.approval_reviews ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.approval_reviews FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.approval_reviews FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.approval_reviews TO ai_policy_executor;
CREATE POLICY review_scope ON portal.approval_reviews TO ai_policy_executor USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id)) WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id));
CREATE FUNCTION portal.review_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN RAISE EXCEPTION 'REVIEW_IMMUTABLE' USING ERRCODE='23514';END;$$;
ALTER FUNCTION portal.review_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.review_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter;
CREATE TRIGGER review_immutable BEFORE UPDATE OR DELETE ON portal.approval_reviews FOR EACH ROW EXECUTE FUNCTION portal.review_immutable();
ALTER TABLE portal.workflow_versions ADD COLUMN manifest_snapshot jsonb;
ALTER TABLE portal.workflow_versions ADD CONSTRAINT manifest_snapshot_contract CHECK(manifest_snapshot IS NULL OR jsonb_typeof(manifest_snapshot)='object' AND use_case_id='AGENT_03' AND manifest_snapshot->>'use_case_id'=use_case_id AND manifest_snapshot->>'manifest_digest'=use_case_digest);
GRANT UPDATE(manifest_snapshot) ON portal.workflow_versions TO ai_policy_executor;
CREATE FUNCTION portal.manifest_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF OLD.manifest_snapshot IS NOT NULL AND NEW.manifest_snapshot IS DISTINCT FROM OLD.manifest_snapshot OR OLD.manifest_snapshot IS NULL AND NEW.manifest_snapshot IS NOT NULL AND OLD.status<>'pending' THEN RAISE EXCEPTION 'MANIFEST_IMMUTABLE' USING ERRCODE='23514';END IF;RETURN NEW;END;$$;
ALTER FUNCTION portal.manifest_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.manifest_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter;
CREATE TRIGGER manifest_immutable BEFORE UPDATE ON portal.workflow_versions FOR EACH ROW EXECUTE FUNCTION portal.manifest_immutable();
ALTER FUNCTION security.tool_approval_control(uuid,uuid,text,uuid,jsonb,uuid) RENAME TO tool_approval_control_v046;
REVOKE ALL ON FUNCTION security.tool_approval_control_v046(uuid,uuid,text,uuid,jsonb,uuid) FROM ai_web;
CREATE FUNCTION security.tool_approval_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_trace uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE u uuid;target uuid:=p_id;clean jsonb:=p_body-ARRAY['comment','manifest_snapshot','current_descriptor'];data jsonb;prior portal.approval_reviews%ROWTYPE;note text;
BEGIN
 IF p_action IN ('approve','reject','revoke') THEN
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
  note:=btrim(p_body->>'comment');
  IF jsonb_typeof(p_body->'comment') IS DISTINCT FROM 'string' OR char_length(note) NOT BETWEEN 1 AND 500 OR coalesce(p_body->>'expected_revision','') !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':tool-review',0));
  IF p_action IN ('approve','reject') AND ((SELECT requester_id FROM portal.tool_approvals WHERE tenant_id=p_tenant AND request_id=p_id)=u OR (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN') THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  IF p_action='approve' AND (SELECT descriptor FROM portal.tool_approvals WHERE tenant_id=p_tenant AND request_id=p_id) IS DISTINCT FROM p_body->'current_descriptor' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  IF p_action='revoke' THEN SELECT request_id INTO target FROM portal.tool_heads WHERE tenant_id=p_tenant AND tool_id=p_body->>'tool_id'; END IF;
  SELECT * INTO prior FROM portal.approval_reviews WHERE tenant_id=p_tenant AND kind='tool' AND target_id=target AND action=p_action AND expected_revision=(p_body->>'expected_revision')::bigint;
  IF FOUND THEN
   IF prior.actor_id<>u OR prior.comment<>note THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN prior.result||jsonb_build_object('replayed',true);
  END IF;
 END IF;
 IF p_action='approve' AND EXISTS(SELECT 1 FROM portal.tool_approvals t CROSS JOIN LATERAL unnest(t.member_ids) member_id WHERE t.tenant_id=p_tenant AND t.request_id=p_id AND t.audience='restricted' AND NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts a USING(user_id) WHERE m.tenant_id=p_tenant AND m.user_id=member_id AND m.active AND a.active)) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 data:=security.tool_approval_control_v046(p_session,p_tenant,p_action,p_id,clean,p_trace);
 IF p_action IN ('approve','reject','revoke') THEN
  IF coalesce((data->>'replayed')::boolean,false) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  INSERT INTO portal.approval_reviews(tenant_id,kind,target_id,actor_id,action,expected_revision,comment,result) VALUES(p_tenant,'tool',target,u,p_action,(p_body->>'expected_revision')::bigint,note,data);
 END IF;
 RETURN data;END;$$;
ALTER FUNCTION security.tool_approval_control(uuid,uuid,text,uuid,jsonb,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.tool_approval_control(uuid,uuid,text,uuid,jsonb,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.tool_approval_control(uuid,uuid,text,uuid,jsonb,uuid) TO ai_web;
ALTER FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) RENAME TO workflow_approval_control_v049;
REVOKE ALL ON FUNCTION security.workflow_approval_control_v049(uuid,uuid,text,uuid,jsonb,text,uuid) FROM ai_web;
CREATE FUNCTION security.workflow_approval_control(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_trace uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE u uuid;target uuid:=p_id;clean jsonb:=p_body-ARRAY['comment','manifest_snapshot'];data jsonb;prior portal.approval_reviews%ROWTYPE;note text;
BEGIN
 IF p_action IN ('approve','reject','revoke') THEN
  u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
  note:=btrim(p_body->>'comment');
  IF jsonb_typeof(p_body->'comment') IS DISTINCT FROM 'string' OR char_length(note) NOT BETWEEN 1 AND 500 OR coalesce(p_body->>'expected_revision','') !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':workflow-review',0));
  IF p_action IN ('approve','reject') AND ((SELECT created_by FROM portal.workflow_versions WHERE tenant_id=p_tenant AND version_id=p_id)=u OR (SELECT effective_role FROM security.current_membership(p_session,p_tenant))<>'PADMIN') THEN RAISE EXCEPTION 'APPROVAL_DENIED' USING ERRCODE='A0403';END IF;
  IF p_action='revoke' THEN SELECT version_id INTO target FROM portal.workflow_heads WHERE tenant_id=p_tenant AND workflow_id=(p_body->>'workflow_id')::uuid; END IF;
  SELECT * INTO prior FROM portal.approval_reviews WHERE tenant_id=p_tenant AND kind='workflow' AND target_id=target AND action=p_action AND expected_revision=(p_body->>'expected_revision')::bigint;
  IF FOUND THEN
   IF prior.actor_id<>u OR prior.comment<>note THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   RETURN prior.result||jsonb_build_object('replayed',true);
  END IF;
 END IF;
 data:=security.workflow_approval_control_v049(p_session,p_tenant,p_action,p_id,clean,p_mode,p_trace);
 IF p_action IN ('approve','reject','revoke') THEN
  IF coalesce((data->>'replayed')::boolean,false) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  INSERT INTO portal.approval_reviews(tenant_id,kind,target_id,actor_id,action,expected_revision,comment,result) VALUES(p_tenant,'workflow',target,u,p_action,(p_body->>'expected_revision')::bigint,note,data);
 END IF;
 IF p_action='submit' AND p_body->>'use_case_id' IS NOT NULL AND NOT (data->>'replayed')::boolean THEN
 IF jsonb_typeof(p_body->'manifest_snapshot') IS DISTINCT FROM 'object' OR p_body->'manifest_snapshot'->>'manifest_digest' IS DISTINCT FROM p_body->>'meeting_digest' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 UPDATE portal.workflow_versions SET manifest_snapshot=p_body->'manifest_snapshot' WHERE tenant_id=p_tenant AND version_id=(data->>'version_id')::uuid;
 END IF;
 RETURN data;END;$$;
ALTER FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.workflow_approval_control(uuid,uuid,text,uuid,jsonb,text,uuid) TO ai_web;
CREATE FUNCTION security.approval_review_read(p_session uuid,p_tenant uuid,p_kind text,p_id uuid,p_body jsonb,p_mode text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE u uuid;items jsonb;pending bigint;actionable bigint;rowdata jsonb;head jsonb;hist jsonb;valid boolean:=true;reason text;node jsonb;pub jsonb;checks jsonb:='[]';role text;revision bigint;bound bigint;
BEGIN
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 IF p_kind NOT IN ('tool','workflow') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT effective_role INTO role FROM security.current_membership(p_session,p_tenant);
 IF p_body->>'action'='support' THEN
 IF p_kind='tool' THEN
 SELECT coalesce(jsonb_agg(to_jsonb(h)-'tenant_id'),'[]') INTO items FROM portal.tool_heads h WHERE tenant_id=p_tenant;
 ELSE
 SELECT coalesce(jsonb_agg(to_jsonb(h)-'tenant_id'),'[]') INTO items FROM portal.workflow_heads h WHERE tenant_id=p_tenant;
 END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(h)-'tenant_id'),'[]') INTO hist FROM portal.use_case_heads h WHERE tenant_id=p_tenant;
 RETURN jsonb_build_object('heads',items,'use_case_heads',hist);END IF;
 IF p_id IS NULL THEN
 IF p_kind='tool' THEN
 SELECT count(*),count(*) FILTER(WHERE requester_id<>u AND role='PADMIN') INTO pending,actionable FROM portal.tool_approvals WHERE tenant_id=p_tenant AND status='pending';
 SELECT coalesce(jsonb_agg(x.data ORDER BY x.created_at DESC,x.id),'[]') INTO items FROM
 (SELECT to_jsonb(a)-ARRAY['tenant_id','request_body','client_request_id'] AS data,a.created_at,a.request_id AS id FROM portal.tool_approvals a WHERE tenant_id=p_tenant
 AND (p_body->>'status' IS NULL OR status=p_body->>'status') AND (coalesce(p_body->>'q','')='' OR position(lower(p_body->>'q') IN lower(tool_id||' '||coalesce(descriptor->>'name','')||' '||request_id::text))>0)
 AND (p_body->>'after_time' IS NULL OR created_at<(p_body->>'after_time')::timestamptz OR created_at=(p_body->>'after_time')::timestamptz AND request_id>(p_body->>'after_id')::uuid)
 ORDER BY created_at DESC,request_id LIMIT (p_body->>'limit')::integer)x;
 ELSE
 SELECT count(*),count(*) FILTER(WHERE created_by<>u AND role='PADMIN') INTO pending,actionable FROM portal.workflow_versions WHERE tenant_id=p_tenant AND status='pending';
 SELECT coalesce(jsonb_agg(x.data ORDER BY x.created_at DESC,x.id),'[]') INTO items FROM
 (SELECT to_jsonb(a)-ARRAY['tenant_id','client_request_id'] AS data,a.created_at,a.version_id AS id FROM portal.workflow_versions a WHERE tenant_id=p_tenant
 AND (p_body->>'status' IS NULL OR status=p_body->>'status') AND (coalesce(p_body->>'q','')='' OR position(lower(p_body->>'q') IN lower(coalesce(definition->>'name','')||' '||version_id::text))>0)
 AND (p_body->>'after_time' IS NULL OR created_at<(p_body->>'after_time')::timestamptz OR created_at=(p_body->>'after_time')::timestamptz AND version_id>(p_body->>'after_id')::uuid)
 ORDER BY created_at DESC,version_id LIMIT (p_body->>'limit')::integer)x;
 END IF;RETURN jsonb_build_object('items',items,'total_pending',pending,'actionable_pending',actionable);END IF;
 IF p_kind='tool' THEN
 SELECT to_jsonb(a)-ARRAY['tenant_id','request_body','client_request_id'] INTO rowdata FROM portal.tool_approvals a WHERE tenant_id=p_tenant AND request_id=p_id;
 SELECT (to_jsonb(a)-ARRAY['tenant_id','request_body','client_request_id'])||jsonb_build_object('head_revision',h.revision,'enabled',h.enabled) INTO head FROM portal.tool_heads h JOIN portal.tool_approvals a USING(tenant_id,request_id) WHERE h.tenant_id=p_tenant AND h.tool_id=rowdata->>'tool_id';
 ELSE
 SELECT to_jsonb(a)-ARRAY['tenant_id','client_request_id'] INTO rowdata FROM portal.workflow_versions a WHERE tenant_id=p_tenant AND version_id=p_id;
 SELECT (to_jsonb(a)-ARRAY['tenant_id','client_request_id'])||jsonb_build_object('head_revision',h.revision,'enabled',h.enabled) INTO head FROM portal.workflow_heads h JOIN portal.workflow_versions a USING(tenant_id,version_id) WHERE h.tenant_id=p_tenant AND h.workflow_id=(rowdata->>'workflow_id')::uuid;
 END IF;
 IF rowdata IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF coalesce((head->>'head_revision')::bigint,0)<>(rowdata->>'expected_head_revision')::bigint THEN valid:=false;checks:=checks||jsonb_build_array(jsonb_build_object('code','HEAD_CHANGED','status','fail','message','현재 승인 head가 변경되었습니다.'));END IF;
 IF rowdata->>'audience'='restricted' AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(rowdata->'member_ids') m WHERE NOT EXISTS(SELECT 1 FROM security.memberships sm JOIN security.accounts a USING(user_id) WHERE sm.tenant_id=p_tenant AND sm.user_id=m.value::uuid AND sm.active AND a.active)) THEN valid:=false;checks:=checks||jsonb_build_array(jsonb_build_object('code','AUDIENCE_CHANGED','status','fail','message','현재 공개대상 회원을 확인할 수 없습니다.'));END IF;
 IF p_kind='workflow' THEN
 IF rowdata->>'runtime_digest' IS DISTINCT FROM p_body->>'runtime_digest' OR rowdata->>'execution_mode' IS DISTINCT FROM p_mode THEN valid:=false;checks:=checks||jsonb_build_array(jsonb_build_object('code','CODE_CHANGED','status','fail','message','현재 실행 계약이 변경되었습니다.'));END IF;
 IF rowdata->>'use_case_id' IS NOT NULL THEN
 SELECT h.revision INTO bound FROM portal.use_case_heads h WHERE tenant_id=p_tenant AND use_case_id=rowdata->>'use_case_id';
 IF coalesce(bound,0)<>(rowdata->>'use_case_revision')::bigint OR rowdata->>'use_case_digest' IS DISTINCT FROM p_body->>'meeting_digest' THEN valid:=false;checks:=checks||jsonb_build_array(jsonb_build_object('code','CASE_CHANGED','status','fail','message','업무 승인 계약이 변경되었습니다.'));END IF;END IF;
 FOR node IN SELECT value FROM jsonb_array_elements(rowdata->'definition'->'nodes') LOOP
 BEGIN
 IF node->>'node_type'='llm' THEN
 pub:=security.published_asset_guard(p_session,p_tenant,(node->'config'->>'asset_id')::uuid,p_mode);
 IF pub->>'version_id' IS DISTINCT FROM node->'config'->>'version_id' OR pub->>'publication_revision' IS DISTINCT FROM node->'config'->>'publication_revision' THEN RAISE EXCEPTION 'DEPENDENCY_CHANGED' USING ERRCODE='A0409';END IF;
 ELSIF node->>'node_type'='read_tool' THEN
 IF NOT EXISTS(SELECT 1 FROM portal.tool_heads h JOIN portal.tool_approvals a USING(tenant_id,request_id) WHERE h.tenant_id=p_tenant AND h.tool_id=node->'config'->>'tool_id' AND h.enabled AND a.status='approved' AND a.descriptor->>'digest'=node->'config'->>'version_digest' AND a.descriptor->>'mode'=p_mode AND (a.audience='all' OR u=ANY(a.member_ids))) THEN RAISE EXCEPTION 'DEPENDENCY_UNAVAILABLE' USING ERRCODE='A0403';END IF;END IF;
 EXCEPTION WHEN SQLSTATE 'A0403' OR SQLSTATE 'A0404' OR SQLSTATE 'D0404' OR SQLSTATE 'B0340' OR SQLSTATE 'A0409' OR SQLSTATE 'B0401' THEN
 valid:=false;checks:=checks||jsonb_build_array(jsonb_build_object('code','DEPENDENCY_UNAVAILABLE','status','unavailable','message','의존 자산의 현재 버전 또는 접근 권한을 확인할 수 없습니다.'));
 END;END LOOP;END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('action',r.action,'actor_id',r.actor_id,'created_at',r.created_at,'comment',r.comment,'revision',r.expected_revision) ORDER BY r.created_at),'[]') INTO hist FROM portal.approval_reviews r WHERE tenant_id=p_tenant AND kind=p_kind AND target_id=p_id;
 hist:=jsonb_build_array(jsonb_build_object('action','submit','actor_id',coalesce(rowdata->>'requester_id',rowdata->>'created_by'),'created_at',rowdata->>'created_at','comment',NULL,'revision',NULL))||hist;
 IF rowdata->>'decided_at' IS NOT NULL AND NOT EXISTS(SELECT 1 FROM portal.approval_reviews WHERE tenant_id=p_tenant AND kind=p_kind AND target_id=p_id AND action IN ('approve','reject')) THEN hist:=hist||jsonb_build_array(jsonb_build_object('action',rowdata->>'status','actor_id',rowdata->>'decided_by','created_at',rowdata->>'decided_at','comment',NULL,'revision',NULL));END IF;
 IF role<>'PADMIN' THEN reason:='현재 조직 PADMIN만 결정할 수 있습니다.';ELSIF u::text=coalesce(rowdata->>'requester_id',rowdata->>'created_by') THEN reason:='본인 요청은 결정할 수 없습니다.';ELSIF rowdata->>'status'<>'pending' THEN reason:='이미 처리된 요청입니다.';END IF;
 SELECT jsonb_agg(value ORDER BY (value->>'created_at')::timestamptz) INTO hist FROM jsonb_array_elements(hist);
 RETURN jsonb_build_object('request',rowdata,'current_head',head,'validation',jsonb_build_object('valid',valid,'checks',checks,'checked_at',clock_timestamp()),'history',hist,'can_approve',reason IS NULL AND valid,'can_reject',reason IS NULL,'can_revoke',coalesce((head->>'enabled')::boolean,false) AND coalesce(head->>'request_id',head->>'version_id')=p_id::text,'decision_reason',reason);
END;$$;
ALTER FUNCTION security.approval_review_read(uuid,uuid,text,uuid,jsonb,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.approval_review_read(uuid,uuid,text,uuid,jsonb,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.approval_review_read(uuid,uuid,text,uuid,jsonb,text) TO ai_web;
