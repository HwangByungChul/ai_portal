-- Additive registry: existing settings, runs, ledgers and SQL000~026 remain untouched.
CREATE TABLE portal.assets (
 tenant_id uuid NOT NULL,asset_id uuid NOT NULL,owner_id uuid NOT NULL,client_request_id uuid NOT NULL,
 latest_revision bigint NOT NULL CHECK(latest_revision BETWEEN 1 AND 1000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,asset_id),UNIQUE(tenant_id,owner_id,client_request_id),
 FOREIGN KEY(tenant_id,owner_id) REFERENCES security.memberships(tenant_id,user_id)
);
CREATE TABLE portal.asset_versions (
 tenant_id uuid NOT NULL,asset_id uuid NOT NULL,revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 1000),
 version_id uuid NOT NULL,client_request_id uuid NOT NULL,created_by uuid NOT NULL,
 config jsonb NOT NULL CHECK(jsonb_typeof(config)='object'),config_hash text NOT NULL CHECK(config_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,asset_id,revision),UNIQUE(tenant_id,version_id),UNIQUE(tenant_id,asset_id,created_by,client_request_id),
 FOREIGN KEY(tenant_id,asset_id) REFERENCES portal.assets(tenant_id,asset_id),
 FOREIGN KEY(tenant_id,created_by) REFERENCES security.memberships(tenant_id,user_id)
);
ALTER TABLE portal.assets OWNER TO ai_owner;
ALTER TABLE portal.asset_versions OWNER TO ai_owner;
ALTER TABLE portal.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.assets FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.asset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.asset_versions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.assets,portal.asset_versions FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.assets,portal.asset_versions TO ai_policy_executor;
GRANT UPDATE(latest_revision) ON portal.assets TO ai_policy_executor;
CREATE POLICY asset_access ON portal.assets TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY asset_version_access ON portal.asset_versions TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
-- Read-only deterministic aliases also work for tenants seeded after this migration.
-- The view owner has neither BYPASSRLS nor table ownership; base-table forced RLS applies.
CREATE VIEW portal.asset_registry_records AS
 SELECT a.tenant_id,a.asset_id,a.owner_id,a.latest_revision,a.created_at,
  NULL::text AS legacy_agent_key,v.version_id,v.config,v.config_hash,'draft'::text AS state
 FROM portal.assets a JOIN portal.asset_versions v ON (v.tenant_id,v.asset_id,v.revision)=(a.tenant_id,a.asset_id,a.latest_revision)
 UNION ALL
 SELECT c.tenant_id,md5(c.tenant_id::text||':portal-agent:'||c.agent_key)::uuid,NULL::uuid,c.config_version,NULL::timestamptz,
  c.agent_key,NULL::uuid,normalized.config,
  encode(sha256(convert_to(normalized.config::text,'UTF8')),'hex'),'legacy'
 FROM portal.agent_configs c CROSS JOIN LATERAL (SELECT jsonb_build_object(
  'name',COALESCE(c.settings->>'name',CASE WHEN c.agent_key='general' THEN '일반 대화' ELSE '규정 검색' END),
  'description',COALESCE(c.settings->>'description',''),
  'instructions',COALESCE(c.settings->>'instructions','질문에 답해 주세요.'),
  'execution_kind',c.agent_key) AS config) normalized;
ALTER VIEW portal.asset_registry_records OWNER TO ai_policy_executor;
REVOKE ALL ON portal.asset_registry_records FROM PUBLIC,ai_web,ai_index,ai_meter;

CREATE FUNCTION security.asset_registry(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_trace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;a portal.assets%ROWTYPE;v portal.asset_versions%ROWTYPE;record portal.asset_registry_records%ROWTYPE;
 cfg jsonb;key text;items jsonb;history jsonb;n integer;cursor_id uuid;expected bigint;client_id uuid;hash text;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('list','detail','create','append') OR p_body IS NULL OR jsonb_typeof(p_body)<>'object' THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action IN ('create','append'));
 IF p_action='list' THEN
  IF p_body-ARRAY['limit','cursor']::text[]<>'{}'::jsonb
   OR (p_body ? 'limit' AND (jsonb_typeof(p_body->'limit')<>'number' OR p_body->>'limit' !~ '^[1-9][0-9]*$')) THEN
   RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  n:=COALESCE((p_body->>'limit')::integer,20);cursor_id:=(p_body->>'cursor')::uuid;
  IF n NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  IF cursor_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM portal.asset_registry_records WHERE tenant_id=p_tenant AND asset_id=cursor_id) THEN
   RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.asset_id),'[]'::jsonb) INTO items FROM
   (SELECT asset_id,owner_id,latest_revision,created_at,legacy_agent_key,version_id,config_hash,state,
    config->>'name' AS name,config->>'description' AS description,config->>'execution_kind' AS execution_kind,'agent'::text AS kind
    FROM portal.asset_registry_records WHERE tenant_id=p_tenant AND (cursor_id IS NULL OR asset_id>cursor_id)
    ORDER BY asset_id LIMIT n+1) x;
  RETURN jsonb_build_object('items',CASE WHEN jsonb_array_length(items)>n THEN items-n ELSE items END,
   'next_cursor',CASE WHEN jsonb_array_length(items)>n THEN items->(n-1)->>'asset_id' ELSE NULL END);
 END IF;
 IF p_action='detail' THEN
  IF p_body<>'{}'::jsonb OR p_id IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  SELECT * INTO record FROM portal.asset_registry_records WHERE tenant_id=p_tenant AND asset_id=p_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.revision DESC),'[]'::jsonb) INTO history FROM
   (SELECT revision,version_id,config_hash,created_by,created_at FROM portal.asset_versions
    WHERE tenant_id=p_tenant AND asset_id=p_id AND revision<=record.latest_revision ORDER BY revision DESC LIMIT 50) x;
  RETURN to_jsonb(record)-'tenant_id'||jsonb_build_object('kind','agent','versions',history,'history_more',record.legacy_agent_key IS NULL AND record.latest_revision>50);
 END IF;
 IF p_id IS NULL OR p_trace IS NULL OR NOT p_body ?& ARRAY['client_request_id','config']
 OR p_body-(CASE WHEN p_action='create' THEN ARRAY['client_request_id','config'] ELSE ARRAY['client_request_id','config','expected_revision'] END)::text[]<>'{}'::jsonb
 OR jsonb_typeof(p_body->'client_request_id') IS DISTINCT FROM 'string' THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 cfg:=p_body->'config';client_id:=(p_body->>'client_request_id')::uuid;
 IF jsonb_typeof(cfg) IS DISTINCT FROM 'object' OR cfg-ARRAY['name','description','instructions','execution_kind']::text[]<>'{}'::jsonb
  OR NOT cfg ?& ARRAY['name','description','instructions','execution_kind'] THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 FOR key IN SELECT unnest(ARRAY['name','description','instructions','execution_kind']) LOOP
  IF jsonb_typeof(cfg->key) IS DISTINCT FROM 'string' OR char_length(cfg->>key)>(CASE key WHEN 'name' THEN 80 WHEN 'description' THEN 500 WHEN 'instructions' THEN 2000 ELSE 20 END)
   OR (key<>'description' AND btrim(cfg->>key)='') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 END LOOP;
 IF cfg->>'execution_kind' NOT IN ('general','rules_rag') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 hash:=encode(sha256(convert_to(cfg::text,'UTF8')),'hex');
 IF p_action='create' THEN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':asset-registration',0));
  SELECT * INTO a FROM portal.assets WHERE tenant_id=p_tenant AND owner_id=u AND client_request_id=client_id;
  IF FOUND THEN
   SELECT * INTO v FROM portal.asset_versions WHERE tenant_id=p_tenant AND asset_id=a.asset_id AND revision=1;
   IF v.config<>cfg THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
   RETURN jsonb_build_object('asset_id',a.asset_id,'revision',v.revision,'version_id',v.version_id,'config_hash',v.config_hash,'replayed',true);
  END IF;
  IF (SELECT count(*) FROM portal.assets WHERE tenant_id=p_tenant)>=1000 THEN RAISE EXCEPTION 'ASSET_LIMIT' USING ERRCODE='D0429'; END IF;
  INSERT INTO portal.assets(tenant_id,asset_id,owner_id,client_request_id,latest_revision) VALUES(p_tenant,p_id,u,client_id,1);
  expected:=0;
 ELSE
  IF jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number' OR p_body->>'expected_revision' !~ '^[1-9][0-9]*$' THEN
   RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  expected:=(p_body->>'expected_revision')::bigint;
  SELECT * INTO a FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=p_id FOR UPDATE;
  IF NOT FOUND THEN
   IF EXISTS(SELECT 1 FROM portal.asset_registry_records WHERE tenant_id=p_tenant AND asset_id=p_id AND legacy_agent_key IS NOT NULL) THEN
    RAISE EXCEPTION 'LEGACY_READ_ONLY' USING ERRCODE='D0409'; END IF;
   RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
  SELECT * INTO v FROM portal.asset_versions WHERE tenant_id=p_tenant AND asset_id=p_id AND created_by=u AND client_request_id=client_id;
  IF FOUND THEN
   IF v.config<>cfg OR v.revision<>expected+1 THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
   RETURN jsonb_build_object('asset_id',p_id,'revision',v.revision,'version_id',v.version_id,'config_hash',v.config_hash,'replayed',true);
  END IF;
  IF a.latest_revision<>expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  IF expected>=1000 THEN RAISE EXCEPTION 'ASSET_LIMIT' USING ERRCODE='D0429'; END IF;
  UPDATE portal.assets SET latest_revision=expected+1 WHERE tenant_id=p_tenant AND asset_id=p_id;
 END IF;
 INSERT INTO portal.asset_versions(tenant_id,asset_id,revision,version_id,client_request_id,created_by,config,config_hash)
 VALUES(p_tenant,p_id,expected+1,gen_random_uuid(),client_id,u,cfg,hash) RETURNING * INTO v;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_trace,'tenant',p_tenant,u,CASE WHEN p_action='create' THEN 'asset.create' ELSE 'asset.version' END,p_id,'ok',jsonb_build_object('revision',v.revision));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN jsonb_build_object('asset_id',p_id,'revision',v.revision,'version_id',v.version_id,'config_hash',v.config_hash,'replayed',false);
END; $body$;
ALTER FUNCTION security.asset_registry(uuid,uuid,text,uuid,jsonb,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.asset_registry(uuid,uuid,text,uuid,jsonb,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.asset_registry(uuid,uuid,text,uuid,jsonb,uuid) TO ai_web;
