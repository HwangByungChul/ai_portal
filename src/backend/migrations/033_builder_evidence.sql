-- DP11-04 owner-only history and append-only manual assessments.
CREATE INDEX builder_trials_asset_owner ON portal.builder_trials(tenant_id,owner_user_id,asset_id,run_id);
CREATE TABLE portal.builder_assessments(
 tenant_id uuid NOT NULL,assessment_id uuid NOT NULL DEFAULT gen_random_uuid(),run_id uuid NOT NULL,
 owner_user_id uuid NOT NULL,client_request_id uuid NOT NULL,request_hash text NOT NULL,
 result_hash text NOT NULL,profile_hash text NOT NULL,rubric text NOT NULL CHECK(rubric='manual-v1'),
 assessment jsonb NOT NULL CHECK(jsonb_typeof(assessment)='object' AND octet_length(assessment::text)<=8192),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,assessment_id),UNIQUE(tenant_id,owner_user_id,client_request_id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES portal.builder_trials(tenant_id,run_id));
ALTER TABLE portal.builder_assessments OWNER TO ai_owner;
ALTER TABLE portal.builder_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_assessments FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.builder_assessments FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.builder_assessments TO ai_policy_executor;
CREATE POLICY builder_assessment_owner ON portal.builder_assessments TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE FUNCTION portal.builder_assessment_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN RAISE EXCEPTION 'ASSESSMENT_IMMUTABLE' USING ERRCODE='23514';END;$body$;
ALTER FUNCTION portal.builder_assessment_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.builder_assessment_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER builder_assessment_immutable BEFORE UPDATE OR DELETE ON portal.builder_assessments FOR EACH ROW EXECUTE FUNCTION portal.builder_assessment_immutable();

CREATE FUNCTION security.builder_trial_history(p_session uuid,p_tenant uuid,p_asset uuid,p_cursor uuid,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE anchor timestamptz;items jsonb;next_id uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 IF p_limit IS NULL OR p_limit<1 OR p_limit>20 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF NOT EXISTS(SELECT 1 FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=p_asset) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF p_cursor IS NOT NULL THEN
 SELECT r.created_at INTO anchor FROM portal.runs r JOIN portal.builder_trials q USING(tenant_id,run_id) WHERE r.tenant_id=p_tenant AND r.run_id=p_cursor AND q.asset_id=p_asset;
 IF anchor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.run_id DESC),'[]') INTO items FROM
 (SELECT r.run_id,q.version_id,r.asset_revision AS revision,r.state,r.execution_mode,q.purpose,r.created_at,r.ended_at
 FROM portal.runs r JOIN portal.builder_trials q USING(tenant_id,run_id)
 WHERE r.tenant_id=p_tenant AND q.asset_id=p_asset AND (p_cursor IS NULL OR (r.created_at,r.run_id)<(anchor,p_cursor))
 ORDER BY r.created_at DESC,r.run_id DESC LIMIT p_limit+1) x;
 IF jsonb_array_length(items)>p_limit THEN items:=items-p_limit;next_id:=(items->(p_limit-1)->>'run_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
END;$body$;

CREATE FUNCTION security.builder_trial_evidence(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE q jsonb;v jsonb;reviews jsonb;total integer;prices jsonb;
BEGIN
 v:=security.builder_trial_read(p_session,p_tenant,p_run);q:=security.builder_trial_guard(p_session,p_tenant,p_run);
 SELECT count(*) INTO total FROM portal.builder_assessments WHERE tenant_id=p_tenant AND run_id=p_run;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.assessment_id DESC),'[]') INTO reviews FROM
 (SELECT assessment_id,rubric,assessment,result_hash,profile_hash,created_at FROM portal.builder_assessments
 WHERE tenant_id=p_tenant AND run_id=p_run ORDER BY created_at DESC,assessment_id DESC LIMIT 20) x;
 SELECT coalesce(jsonb_agg(DISTINCT jsonb_build_object('version',price_snapshot->>'version','generation_model',price_snapshot->>'generation_model','embedding_model',price_snapshot->>'embedding_model')),'[]') INTO prices FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run;
 RETURN v||jsonb_build_object('price_snapshots',prices,'price_basis','frozen_internal_estimate','sources',q->'sources','question_hash',encode(sha256(convert_to((q->'messages'->-1->>'content'),'UTF8')),'hex'),
 'result_hash',CASE WHEN q->'result'='null'::jsonb THEN NULL ELSE encode(sha256(convert_to((q->'result')::text,'UTF8')),'hex') END,
 'assessments',reviews,'assessment_count',total,'assessment_limit',20,'assessment_kind','manual');
END;$body$;

CREATE FUNCTION security.builder_trial_assess(p_session uuid,p_tenant uuid,p_run uuid,p_client uuid,p_body jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v jsonb;q jsonb;u uuid;h text;old portal.builder_assessments%ROWTYPE;fresh portal.builder_assessments%ROWTYPE;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 v:=security.builder_trial_evidence(p_session,p_tenant,p_run);u:=nullif(current_setting('app.user_id',true),'')::uuid;
 IF p_client IS NULL OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['comment','correctness','expected_answer','relevance','verdict']
 OR jsonb_typeof(p_body->'correctness') IS DISTINCT FROM 'number' OR p_body->>'correctness' !~ '^[1-5]$'
 OR jsonb_typeof(p_body->'relevance') IS DISTINCT FROM 'number' OR p_body->>'relevance' !~ '^[1-5]$'
 OR coalesce(p_body->>'verdict','') NOT IN ('suitable','needs_change','unsuitable')
 OR coalesce(p_body->>'expected_answer','') NOT IN ('answer','insufficient_evidence')
 OR jsonb_typeof(p_body->'comment') IS DISTINCT FROM 'string' OR char_length(p_body->>'comment')>1000
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF v->>'content_status'<>'final' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 h:=encode(sha256(convert_to(jsonb_build_object('run',p_run,'assessment',p_body)::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||p_client::text,0));
 SELECT * INTO old FROM portal.builder_assessments WHERE tenant_id=p_tenant AND owner_user_id=u AND client_request_id=p_client;
 IF FOUND THEN
 IF old.request_hash<>h THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 RETURN jsonb_build_object('assessment_id',old.assessment_id,'replayed',true);END IF;
 INSERT INTO portal.builder_assessments(tenant_id,run_id,owner_user_id,client_request_id,request_hash,result_hash,profile_hash,rubric,assessment)
 VALUES(p_tenant,p_run,u,p_client,h,v->>'result_hash',v->>'profile_hash','manual-v1',p_body) RETURNING * INTO fresh;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result)
 VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.assess',p_run,'ok');
 RETURN jsonb_build_object('assessment_id',fresh.assessment_id,'replayed',false);
END;$body$;

CREATE FUNCTION security.builder_trial_compare(p_session uuid,p_tenant uuid,p_left uuid,p_right uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE l jsonb;r jsonb;
BEGIN
 l:=security.builder_trial_evidence(p_session,p_tenant,p_left);r:=security.builder_trial_evidence(p_session,p_tenant,p_right);
 IF p_left=p_right OR l->'asset_binding'->>'asset_id' IS DISTINCT FROM r->'asset_binding'->>'asset_id'
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 RETURN jsonb_build_object('left',l,'right',r,'conditions',jsonb_build_object(
 'same_question',l->'question_hash'=r->'question_hash','same_purpose',l->'purpose'=r->'purpose',
 'same_mode',l->'execution_mode'=r->'execution_mode','same_sources',l->'sources'=r->'sources',
 'same_model',l->'model_ref'=r->'model_ref','same_runtime_policy',l->'config_version'=r->'config_version','same_prices',l->'price_snapshots'=r->'price_snapshots','both_final',l->>'content_status'='final' AND r->>'content_status'='final'));
END;$body$;
ALTER FUNCTION security.builder_trial_history(uuid,uuid,uuid,uuid,integer) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_history(uuid,uuid,uuid,uuid,integer) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_history(uuid,uuid,uuid,uuid,integer) TO ai_web;
ALTER FUNCTION security.builder_trial_evidence(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_evidence(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_evidence(uuid,uuid,uuid) TO ai_web;
ALTER FUNCTION security.builder_trial_assess(uuid,uuid,uuid,uuid,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_assess(uuid,uuid,uuid,uuid,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_assess(uuid,uuid,uuid,uuid,jsonb) TO ai_web;
ALTER FUNCTION security.builder_trial_compare(uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_trial_compare(uuid,uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_trial_compare(uuid,uuid,uuid,uuid) TO ai_web;
