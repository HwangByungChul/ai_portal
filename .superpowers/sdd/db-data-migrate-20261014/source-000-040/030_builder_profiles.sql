-- Immutable structured prompt profiles; no draft activation or model calls.
CREATE TABLE portal.builder_profiles (
 tenant_id uuid NOT NULL,version_id uuid NOT NULL,
 profile jsonb NOT NULL CHECK(jsonb_typeof(profile)='object'),
 profile_hash text NOT NULL CHECK(profile_hash ~ '^[0-9a-f]{64}$'),
 parent_version_id uuid,
 PRIMARY KEY(tenant_id,version_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.asset_versions(tenant_id,version_id),
 FOREIGN KEY(tenant_id,parent_version_id) REFERENCES portal.asset_versions(tenant_id,version_id)
);
CREATE TABLE portal.builder_receipts (
 tenant_id uuid NOT NULL,actor_id uuid NOT NULL,client_request_id uuid NOT NULL,
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),receipt jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,actor_id,client_request_id),
 FOREIGN KEY(tenant_id,actor_id) REFERENCES security.memberships(tenant_id,user_id)
);
ALTER TABLE portal.builder_profiles OWNER TO ai_owner;
ALTER TABLE portal.builder_receipts OWNER TO ai_owner;
ALTER TABLE portal.builder_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_receipts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.builder_profiles,portal.builder_receipts FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.builder_profiles,portal.builder_receipts TO ai_policy_executor;
CREATE POLICY builder_profile_access ON portal.builder_profiles TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY builder_receipt_access ON portal.builder_receipts TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND actor_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND actor_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));

CREATE FUNCTION security.builder_profile_validate(p_config jsonb,p_profile jsonb) RETURNS void
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
 IF (SELECT count(DISTINCT value) FROM jsonb_array_elements(p_profile->'document_refs'))<>jsonb_array_length(p_profile->'document_refs') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
END;$body$;
ALTER FUNCTION security.builder_profile_validate(jsonb,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_profile_validate(jsonb,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;

CREATE FUNCTION security.builder_version(p_session uuid,p_tenant uuid,p_asset uuid,p_version uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v portal.asset_versions%ROWTYPE;p portal.builder_profiles%ROWTYPE;profile jsonb;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 IF p_asset IS NULL OR p_version IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO v FROM portal.asset_versions WHERE tenant_id=p_tenant AND asset_id=p_asset AND version_id=p_version;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 SELECT * INTO p FROM portal.builder_profiles WHERE tenant_id=p_tenant AND version_id=p_version;
 profile:=coalesce(p.profile,jsonb_build_object('schema_version',1,'system_prompt',v.config->>'instructions','developer_prompt','',
  'user_template','{{question}}','model_ref',CASE v.config->>'execution_kind' WHEN 'general' THEN 'default_general' ELSE 'default_rules_rag' END,'document_refs','[]'::jsonb));
 RETURN jsonb_build_object('asset_id',v.asset_id,'revision',v.revision,'version_id',v.version_id,'config',v.config,'config_hash',v.config_hash,
  'profile',profile,'profile_hash',coalesce(p.profile_hash,encode(sha256(convert_to(profile::text,'UTF8')),'hex')),
  'profile_source',CASE WHEN p.version_id IS NULL THEN 'legacy-derived' ELSE 'stored' END,'parent_version_id',p.parent_version_id,'created_at',v.created_at);
END;$body$;
ALTER FUNCTION security.builder_version(uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_version(uuid,uuid,uuid,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_version(uuid,uuid,uuid,uuid) TO ai_web;

-- Keep the former validated implementation private. Public legacy append cannot erase a profile.
ALTER FUNCTION security.asset_registry(uuid,uuid,text,uuid,jsonb,uuid) RENAME TO asset_registry_v029;
REVOKE ALL ON FUNCTION security.asset_registry_v029(uuid,uuid,text,uuid,jsonb,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
CREATE FUNCTION security.asset_registry(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_trace uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',p_action IN ('create','append'));
 IF p_action='append' THEN
  PERFORM 1 FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=p_id FOR UPDATE;
  IF EXISTS(SELECT 1 FROM portal.asset_versions v JOIN portal.builder_profiles p ON (p.tenant_id,p.version_id)=(v.tenant_id,v.version_id) WHERE v.tenant_id=p_tenant AND v.asset_id=p_id) THEN
   RAISE EXCEPTION 'BUILDER_PROFILE_REQUIRED' USING ERRCODE='D0410';END IF;
 END IF;
 RETURN security.asset_registry_v029(p_session,p_tenant,p_action,p_id,p_body,p_trace);
END;$body$;
ALTER FUNCTION security.asset_registry(uuid,uuid,text,uuid,jsonb,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.asset_registry(uuid,uuid,text,uuid,jsonb,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.asset_registry(uuid,uuid,text,uuid,jsonb,uuid) TO ai_web;

CREATE FUNCTION security.builder_save(p_session uuid,p_tenant uuid,p_action text,p_asset uuid,p_body jsonb,p_trace uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;client uuid;hash text;profile jsonb;cfg jsonb;receipt jsonb;old portal.builder_receipts%ROWTYPE;
 target uuid;parent uuid;source jsonb;expected bigint;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('create','append','clone') OR p_body IS NULL OR jsonb_typeof(p_body)<>'object' OR p_trace IS NULL
 OR jsonb_typeof(p_body->'client_request_id') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);client:=(p_body->>'client_request_id')::uuid;
 IF p_action='clone' THEN
  IF p_asset IS NULL OR p_body-ARRAY['client_request_id','source_version_id']::text[]<>'{}'::jsonb OR jsonb_typeof(p_body->'source_version_id') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  parent:=(p_body->>'source_version_id')::uuid;source:=security.builder_version(p_session,p_tenant,p_asset,parent);
  cfg:=source->'config';profile:=source->'profile';
 ELSE
  IF p_body-(CASE WHEN p_action='create' THEN ARRAY['client_request_id','config','profile'] ELSE ARRAY['client_request_id','config','profile','expected_revision'] END)::text[]<>'{}'::jsonb
   OR NOT p_body ?& ARRAY['client_request_id','config','profile'] THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  IF p_action='append' AND (p_asset IS NULL OR jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number'
   OR p_body->>'expected_revision' !~ '^[1-9][0-9]*$') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  cfg:=p_body->'config';profile:=p_body->'profile';
 END IF;
 -- Source visibility and document rights are checked even on replay.
 PERFORM security.builder_profile_validate(cfg,profile);
 hash:=encode(sha256(convert_to(jsonb_build_object('action',p_action,'asset_id',CASE WHEN p_action='create' THEN NULL ELSE p_asset END,'body',p_body)::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':builder-mutation:'||u::text||client::text,0));
 SELECT * INTO old FROM portal.builder_receipts WHERE tenant_id=p_tenant AND actor_id=u AND client_request_id=client;
 IF FOUND THEN
  IF old.request_hash<>hash THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  RETURN old.receipt||jsonb_build_object('replayed',true);
 END IF;
 IF (SELECT count(*) FROM portal.builder_receipts WHERE tenant_id=p_tenant AND actor_id=u)>=10000 THEN RAISE EXCEPTION 'ASSET_LIMIT' USING ERRCODE='D0429';END IF;
 IF p_action='append' THEN
  target:=p_asset;expected:=(p_body->>'expected_revision')::bigint;
  PERFORM 1 FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=p_asset FOR UPDATE;
  SELECT p.parent_version_id INTO parent FROM portal.assets a JOIN portal.asset_versions v ON (v.tenant_id,v.asset_id,v.revision)=(a.tenant_id,a.asset_id,a.latest_revision) JOIN portal.builder_profiles p ON (p.tenant_id,p.version_id)=(v.tenant_id,v.version_id) WHERE a.tenant_id=p_tenant AND a.asset_id=p_asset;
  receipt:=security.asset_registry_v029(p_session,p_tenant,'append',target,jsonb_build_object('client_request_id',client,'config',cfg,'expected_revision',expected),p_trace);
 ELSE
  target:=gen_random_uuid();receipt:=security.asset_registry_v029(p_session,p_tenant,'create',target,jsonb_build_object('client_request_id',client,'config',cfg),p_trace);
 END IF;
 -- A receipt from the legacy API cannot retroactively add metadata to an old version.
 IF (receipt->>'replayed')::boolean THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 target:=(receipt->>'asset_id')::uuid;
 INSERT INTO portal.builder_profiles(tenant_id,version_id,profile,profile_hash,parent_version_id)
 VALUES(p_tenant,(receipt->>'version_id')::uuid,profile,encode(sha256(convert_to(profile::text,'UTF8')),'hex'),parent);
 receipt:=receipt||jsonb_build_object('profile_hash',encode(sha256(convert_to(profile::text,'UTF8')),'hex'),'parent_version_id',parent);
 IF p_action='clone' THEN
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
  VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.clone',target,'ok',jsonb_build_object('revision',1,'parent_version_id',parent));
 END IF;
 INSERT INTO portal.builder_receipts(tenant_id,actor_id,client_request_id,request_hash,receipt) VALUES(p_tenant,u,client,hash,receipt);
 RETURN receipt;
END;$body$;
ALTER FUNCTION security.builder_save(uuid,uuid,text,uuid,jsonb,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_save(uuid,uuid,text,uuid,jsonb,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_save(uuid,uuid,text,uuid,jsonb,uuid) TO ai_web;
