-- DP11-05 private immutable evaluation cases and deterministic checks.
CREATE TABLE portal.builder_cases(
 tenant_id uuid NOT NULL,case_id uuid NOT NULL DEFAULT gen_random_uuid(),owner_user_id uuid NOT NULL,
 asset_id uuid NOT NULL,version_id uuid NOT NULL,client_request_id uuid NOT NULL,
 case_hash text NOT NULL,profile_hash text NOT NULL,composition_hash text NOT NULL,spec jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,case_id),UNIQUE(tenant_id,owner_user_id,client_request_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.asset_versions(tenant_id,version_id),
 CHECK(jsonb_typeof(spec)='object' AND octet_length(spec::text)<=32000));
CREATE TABLE portal.builder_evaluations(
 tenant_id uuid NOT NULL,evaluation_id uuid NOT NULL DEFAULT gen_random_uuid(),owner_user_id uuid NOT NULL,
 case_id uuid NOT NULL,run_id uuid NOT NULL,case_hash text NOT NULL,result_hash text NOT NULL,
 engine text NOT NULL CHECK(engine='literal-v1'),checks jsonb NOT NULL,passed boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,evaluation_id),UNIQUE(tenant_id,case_id,run_id),
 FOREIGN KEY(tenant_id,case_id) REFERENCES portal.builder_cases(tenant_id,case_id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES portal.builder_trials(tenant_id,run_id),
 CHECK(jsonb_typeof(checks)='array' AND octet_length(checks::text)<=16000));
ALTER TABLE portal.builder_cases OWNER TO ai_owner;
ALTER TABLE portal.builder_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_cases FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.builder_cases FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.builder_cases TO ai_policy_executor;
CREATE POLICY builder_cases_owner ON portal.builder_cases TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE TRIGGER builder_cases_immutable BEFORE UPDATE OR DELETE ON portal.builder_cases FOR EACH ROW EXECUTE FUNCTION portal.builder_assessment_immutable();
ALTER TABLE portal.builder_evaluations OWNER TO ai_owner;
ALTER TABLE portal.builder_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_evaluations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.builder_evaluations FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.builder_evaluations TO ai_policy_executor;
CREATE POLICY builder_evaluations_owner ON portal.builder_evaluations TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE TRIGGER builder_evaluations_immutable BEFORE UPDATE OR DELETE ON portal.builder_evaluations FOR EACH ROW EXECUTE FUNCTION portal.builder_assessment_immutable();

CREATE FUNCTION security.builder_case_save(p_session uuid,p_tenant uuid,p_asset uuid,p_version uuid,p_client uuid,p_body jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v jsonb;messages jsonb;c jsonb;h text;u uuid;old portal.builder_cases%ROWTYPE;fresh portal.builder_cases%ROWTYPE;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 v:=security.builder_version(p_session,p_tenant,p_asset,p_version);
 PERFORM security.builder_profile_validate(v->'config',v->'profile');
 c:=p_body->'criteria';
 IF p_client IS NULL OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['criteria','name','purpose','values']
 OR jsonb_typeof(p_body->'name') IS DISTINCT FROM 'string' OR btrim(p_body->>'name')='' OR char_length(p_body->>'name')>100
 OR coalesce(p_body->>'purpose','') NOT IN ('generate','search')
 OR (p_body->>'purpose'='search' AND v->'profile'->>'model_ref'<>'default_rules_rag')
 OR jsonb_typeof(c) IS DISTINCT FROM 'object'
 OR ARRAY(SELECT jsonb_object_keys(c) ORDER BY 1)<>ARRAY['expected_answer','forbidden_terms','required_sources','required_terms']
 OR coalesce(c->>'expected_answer','') NOT IN ('answer','insufficient_evidence')
 OR jsonb_typeof(c->'required_terms') IS DISTINCT FROM 'array' OR jsonb_typeof(c->'forbidden_terms') IS DISTINCT FROM 'array'
 OR jsonb_typeof(c->'required_sources') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF jsonb_array_length(c->'required_terms')>10 OR jsonb_array_length(c->'forbidden_terms')>10 OR jsonb_array_length(c->'required_sources')>5
 OR EXISTS(SELECT 1 FROM jsonb_array_elements((c->'required_terms')||(c->'forbidden_terms')) x WHERE jsonb_typeof(x)<>'string' OR btrim(x#>>'{}')='' OR char_length(x#>>'{}')>200)
 OR (SELECT count(DISTINCT x) FROM jsonb_array_elements(c->'required_terms') x)<>jsonb_array_length(c->'required_terms')
 OR (SELECT count(DISTINCT x) FROM jsonb_array_elements(c->'forbidden_terms') x)<>jsonb_array_length(c->'forbidden_terms')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(c->'required_terms') x WHERE c->'forbidden_terms' @> jsonb_build_array(x))
 OR (SELECT count(DISTINCT x) FROM jsonb_array_elements(c->'required_sources') x)<>jsonb_array_length(c->'required_sources')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(c->'required_sources') x WHERE NOT (v->'profile'->'document_refs' @> jsonb_build_array(x)) OR jsonb_typeof(x)<>'object' OR ARRAY(SELECT jsonb_object_keys(x) ORDER BY 1)<>ARRAY['document_id','version_id'])
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 messages:=security.builder_trial_compose(v->'profile',p_body->'values');
 h:=encode(sha256(convert_to(jsonb_build_object('asset',p_asset,'version',p_version,'spec',p_body)::text,'UTF8')),'hex');u:=nullif(current_setting('app.user_id',true),'')::uuid;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||p_client::text,0));
 SELECT * INTO old FROM portal.builder_cases WHERE tenant_id=p_tenant AND owner_user_id=u AND client_request_id=p_client;
 IF FOUND THEN
 IF old.case_hash<>h THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 RETURN jsonb_build_object('case_id',old.case_id,'case_hash',old.case_hash,'replayed',true);END IF;
 INSERT INTO portal.builder_cases(tenant_id,owner_user_id,asset_id,version_id,client_request_id,case_hash,profile_hash,composition_hash,spec)
 VALUES(p_tenant,u,p_asset,p_version,p_client,h,v->>'profile_hash',encode(sha256(convert_to(messages::text,'UTF8')),'hex'),p_body) RETURNING * INTO fresh;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.case_saved',fresh.case_id,'ok');
 RETURN jsonb_build_object('case_id',fresh.case_id,'case_hash',h,'replayed',false);
END;$body$;

CREATE FUNCTION security.builder_case_read(p_session uuid,p_tenant uuid,p_case uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE c portal.builder_cases%ROWTYPE;v jsonb;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 SELECT * INTO c FROM portal.builder_cases WHERE tenant_id=p_tenant AND case_id=p_case;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 v:=security.builder_version(p_session,p_tenant,c.asset_id,c.version_id);
 PERFORM security.builder_profile_validate(v->'config',v->'profile');
 IF v->>'profile_hash' IS DISTINCT FROM c.profile_hash THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 RETURN to_jsonb(c)-ARRAY['owner_user_id','client_request_id'];
END;$body$;

CREATE FUNCTION security.builder_case_list(p_session uuid,p_tenant uuid,p_asset uuid,p_version uuid,p_cursor uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE items jsonb;anchor timestamptz;next_id uuid;v jsonb;
BEGIN
 v:=security.builder_version(p_session,p_tenant,p_asset,p_version);PERFORM security.builder_profile_validate(v->'config',v->'profile');
 IF p_cursor IS NOT NULL THEN SELECT created_at INTO anchor FROM portal.builder_cases WHERE tenant_id=p_tenant AND asset_id=p_asset AND version_id=p_version AND case_id=p_cursor;
 IF anchor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.case_id DESC),'[]') INTO items FROM
 (SELECT case_id,spec->>'name' AS name,spec->>'purpose' AS purpose,created_at FROM portal.builder_cases
 WHERE tenant_id=p_tenant AND asset_id=p_asset AND version_id=p_version AND (p_cursor IS NULL OR (created_at,case_id)<(anchor,p_cursor)) ORDER BY created_at DESC,case_id DESC LIMIT 21) x;
 IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'case_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
END;$body$;

CREATE FUNCTION security.builder_case_evaluate(p_session uuid,p_tenant uuid,p_case uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE c jsonb;v jsonb;rules jsonb;text_value text;term text;source jsonb;proofs jsonb;checks jsonb:='[]';passed boolean;fresh portal.builder_evaluations%ROWTYPE;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 c:=security.builder_case_read(p_session,p_tenant,p_case);v:=security.builder_trial_evidence(p_session,p_tenant,p_run);rules:=c->'spec'->'criteria';
 IF v->>'content_status'<>'final' OR v->'asset_binding'->>'version_id' IS DISTINCT FROM c->>'version_id'
 OR v->>'profile_hash' IS DISTINCT FROM c->>'profile_hash' OR v->>'composition_hash' IS DISTINCT FROM c->>'composition_hash'
 OR v->>'purpose' IS DISTINCT FROM c->'spec'->>'purpose' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||p_case::text||p_run::text,0));
 SELECT * INTO fresh FROM portal.builder_evaluations WHERE tenant_id=p_tenant AND case_id=p_case AND run_id=p_run;
 IF FOUND THEN RETURN (to_jsonb(fresh)-'owner_user_id')||jsonb_build_object('replayed',true);END IF;
 IF v->>'purpose'='search' THEN
 SELECT coalesce(string_agg(concat_ws(' ',x->>'subject',x->>'predicate',x->>'value',x->>'quote'),'
'),'') INTO text_value FROM jsonb_array_elements(v->'result'->'candidates') x;
 SELECT coalesce(jsonb_agg(x->'source'),'[]') INTO proofs FROM jsonb_array_elements(v->'result'->'candidates') x WHERE x->'source' IS NOT NULL;
 ELSE text_value:=coalesce(v->'result'->>'text','');proofs:=coalesce(v->'result'->'evidence','[]');END IF;
 checks:=jsonb_build_array(jsonb_build_object('rule','answer_kind','passed',v->'result'->>'answer_kind'=rules->>'expected_answer'));
 FOR term IN SELECT jsonb_array_elements_text(rules->'required_terms') LOOP checks:=checks||jsonb_build_array(jsonb_build_object('rule','required_term','value',term,'passed',strpos(text_value,term)>0));END LOOP;
 FOR term IN SELECT jsonb_array_elements_text(rules->'forbidden_terms') LOOP checks:=checks||jsonb_build_array(jsonb_build_object('rule','forbidden_term','value',term,'passed',strpos(text_value,term)=0));END LOOP;
 FOR source IN SELECT value FROM jsonb_array_elements(rules->'required_sources') LOOP
 checks:=checks||jsonb_build_array(jsonb_build_object('rule','required_source','value',source,'passed',EXISTS(SELECT 1 FROM jsonb_array_elements(proofs) x WHERE x->>'document_id'=source->>'document_id' AND x->>'version_id'=source->>'version_id')));END LOOP;
 SELECT bool_and((x->>'passed')::boolean) INTO passed FROM jsonb_array_elements(checks) x;
 INSERT INTO portal.builder_evaluations(tenant_id,owner_user_id,case_id,run_id,case_hash,result_hash,engine,checks,passed)
 VALUES(p_tenant,nullif(current_setting('app.user_id',true),'')::uuid,p_case,p_run,c->>'case_hash',v->>'result_hash','literal-v1',checks,passed) RETURNING * INTO fresh;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(gen_random_uuid(),'tenant',p_tenant,fresh.owner_user_id,'builder.evaluated',fresh.evaluation_id,'ok');
 RETURN (to_jsonb(fresh)-'owner_user_id')||jsonb_build_object('replayed',false);
END;$body$;
ALTER FUNCTION security.builder_case_save(uuid,uuid,uuid,uuid,uuid,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_case_save(uuid,uuid,uuid,uuid,uuid,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_case_save(uuid,uuid,uuid,uuid,uuid,jsonb) TO ai_web;
ALTER FUNCTION security.builder_case_read(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_case_read(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_case_read(uuid,uuid,uuid) TO ai_web;
ALTER FUNCTION security.builder_case_list(uuid,uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_case_list(uuid,uuid,uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_case_list(uuid,uuid,uuid,uuid,uuid) TO ai_web;
ALTER FUNCTION security.builder_case_evaluate(uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_case_evaluate(uuid,uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_case_evaluate(uuid,uuid,uuid,uuid) TO ai_web;
CREATE OR REPLACE FUNCTION security.builder_trial_evidence(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE q jsonb;v jsonb;reviews jsonb;total integer;prices jsonb;auto_checks jsonb;auto_count integer;
BEGIN
 v:=security.builder_trial_read(p_session,p_tenant,p_run);q:=security.builder_trial_guard(p_session,p_tenant,p_run);
 SELECT count(*) INTO total FROM portal.builder_assessments WHERE tenant_id=p_tenant AND run_id=p_run;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.assessment_id DESC),'[]') INTO reviews FROM
 (SELECT assessment_id,rubric,assessment,result_hash,profile_hash,created_at FROM portal.builder_assessments
 WHERE tenant_id=p_tenant AND run_id=p_run ORDER BY created_at DESC,assessment_id DESC LIMIT 20) x;
 SELECT coalesce(jsonb_agg(DISTINCT jsonb_build_object('version',price_snapshot->>'version','generation_model',price_snapshot->>'generation_model','embedding_model',price_snapshot->>'embedding_model')),'[]') INTO prices FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run;
 SELECT count(*) INTO auto_count FROM portal.builder_evaluations WHERE tenant_id=p_tenant AND run_id=p_run;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.evaluation_id DESC),'[]') INTO auto_checks FROM (SELECT evaluation_id,case_id,case_hash,result_hash,engine,checks,passed,created_at FROM portal.builder_evaluations WHERE tenant_id=p_tenant AND run_id=p_run ORDER BY created_at DESC,evaluation_id DESC LIMIT 20) x;
 RETURN v||jsonb_build_object('automatic_checks',auto_checks,'automatic_check_count',auto_count,'price_snapshots',prices,'price_basis','frozen_internal_estimate','sources',q->'sources','question_hash',encode(sha256(convert_to((q->'messages'->-1->>'content'),'UTF8')),'hex'),
 'result_hash',CASE WHEN q->'result'='null'::jsonb THEN NULL ELSE encode(sha256(convert_to((q->'result')::text,'UTF8')),'hex') END,
 'assessments',reviews,'assessment_count',total,'assessment_limit',20,'assessment_kind','manual');
END;$body$;

