-- Canonical UUID deduplication at the private SQL boundary; no row changes.
CREATE OR REPLACE FUNCTION security.builder_profile_validate(p_config jsonb,p_profile jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE k text;r jsonb;remainder text;names text[];model text;
BEGIN
 IF p_config IS NULL OR jsonb_typeof(p_config)<>'object' OR p_profile IS NULL OR jsonb_typeof(p_profile)<>'object'
 OR p_profile-ARRAY['schema_version','system_prompt','developer_prompt','user_template','model_ref','document_refs']::text[]<>'{}'::jsonb
 OR NOT p_profile ?& ARRAY['schema_version','system_prompt','developer_prompt','user_template','model_ref','document_refs']
 OR p_profile->'schema_version' IS DISTINCT FROM '1'::jsonb THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 FOR k IN SELECT unnest(ARRAY['system_prompt','developer_prompt','user_template','model_ref']) LOOP
  IF jsonb_typeof(p_profile->k) IS DISTINCT FROM 'string' OR char_length(p_profile->>k)>2000
  OR (k<>'developer_prompt' AND btrim(p_profile->>k)='') OR (k='developer_prompt' AND p_profile->>k<>'' AND btrim(p_profile->>k)='') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 END LOOP;
 IF p_profile->>'system_prompt' IS DISTINCT FROM p_config->>'instructions' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 model:=CASE p_config->>'execution_kind' WHEN 'general' THEN 'default_general' WHEN 'rules_rag' THEN 'default_rules_rag' ELSE NULL END;
 IF model IS NULL OR p_profile->>'model_ref' IS DISTINCT FROM model THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 remainder:=concat(p_profile->>'system_prompt',E'\n',p_profile->>'developer_prompt',E'\n',p_profile->>'user_template');
 SELECT array_agg(DISTINCT x[1]) INTO names FROM regexp_matches(remainder,'\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}','g') AS x;
 remainder:=regexp_replace(remainder,'\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}','','g');
 IF strpos(remainder,'{{')>0 OR strpos(remainder,'}}')>0 OR coalesce(cardinality(names),0)>20 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF jsonb_typeof(p_profile->'document_refs') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF jsonb_array_length(p_profile->'document_refs')>5 OR (model='default_general' AND p_profile->'document_refs'<>'[]'::jsonb) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 FOR r IN SELECT value FROM jsonb_array_elements(p_profile->'document_refs') LOOP
  IF jsonb_typeof(r)<>'object' OR r-ARRAY['document_id','version_id']::text[]<>'{}'::jsonb OR NOT r ?& ARRAY['document_id','version_id']
  OR jsonb_typeof(r->'document_id') IS DISTINCT FROM 'string' OR jsonb_typeof(r->'version_id') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  IF NOT EXISTS(SELECT 1 FROM rag.document_versions v JOIN rag.index_builds i ON (i.tenant_id,i.document_id,i.version_id)=(v.tenant_id,v.document_id,v.version_id)
   WHERE v.document_id=(r->>'document_id')::uuid AND v.version_id=(r->>'version_id')::uuid AND security.document_can_read(v.tenant_id,v.document_id,v.version_id,i.index_id)) THEN
   RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='D0404';END IF;
 END LOOP;
 IF (SELECT count(DISTINCT ROW((value->>'document_id')::uuid,(value->>'version_id')::uuid)) FROM jsonb_array_elements(p_profile->'document_refs'))<>jsonb_array_length(p_profile->'document_refs') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
END;$body$;
ALTER FUNCTION security.builder_profile_validate(jsonb,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_profile_validate(jsonb,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;

