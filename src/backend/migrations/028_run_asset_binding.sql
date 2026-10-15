-- DP09-02: new run provenance only; no UPDATE/backfill of historical rows.
ALTER TABLE portal.runs ADD COLUMN asset_id uuid;
ALTER TABLE portal.runs ADD COLUMN asset_revision bigint;
ALTER TABLE portal.runs ADD COLUMN asset_version_id uuid;
ALTER TABLE portal.runs ADD COLUMN asset_config_hash text;
ALTER TABLE portal.runs ADD CONSTRAINT runs_asset_binding_complete CHECK(
 (asset_id IS NULL AND asset_revision IS NULL AND asset_version_id IS NULL AND asset_config_hash IS NULL)
 OR (asset_id IS NOT NULL AND asset_revision IS NOT NULL AND asset_revision>0
 AND asset_version_id IS NOT NULL AND asset_config_hash IS NOT NULL AND asset_config_hash ~ '^[0-9a-f]{64}$'));
GRANT SELECT(asset_id,asset_revision,asset_version_id,asset_config_hash) ON portal.runs TO ai_web;

CREATE FUNCTION portal.run_asset_binding() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
DECLARE cfg jsonb;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (NEW.asset_id,NEW.asset_revision,NEW.asset_version_id,NEW.asset_config_hash)
   IS DISTINCT FROM (OLD.asset_id,OLD.asset_revision,OLD.asset_version_id,OLD.asset_config_hash) THEN
   RAISE EXCEPTION 'RUN_ASSET_BINDING_IMMUTABLE' USING ERRCODE='23514';END IF;
  RETURN NEW;
 END IF;
 IF NEW.agent_key NOT IN ('general','rules_rag') OR NEW.config_snapshot->>'agent_key' IS DISTINCT FROM NEW.agent_key
 OR jsonb_typeof(NEW.config_snapshot->'config_version') IS DISTINCT FROM 'number'
 OR NEW.config_snapshot->>'config_version' !~ '^[1-9][0-9]*$' THEN
  RAISE EXCEPTION 'RUN_ASSET_BINDING_INVALID' USING ERRCODE='23514';END IF;
 cfg:=jsonb_build_object(
  'name',COALESCE(NEW.config_snapshot->>'name',CASE WHEN NEW.agent_key='general' THEN '일반 대화' ELSE '규정 검색' END),
  'description',COALESCE(NEW.config_snapshot->>'description',''),
  'instructions',COALESCE(NEW.config_snapshot->>'instructions','질문에 답해 주세요.'),
  'execution_kind',NEW.agent_key);
 NEW.asset_id:=md5(NEW.tenant_id::text||':portal-agent:'||NEW.agent_key)::uuid;
 NEW.asset_revision:=(NEW.config_snapshot->>'config_version')::bigint;
 NEW.asset_config_hash:=encode(sha256(convert_to(cfg::text,'UTF8')),'hex');
 NEW.asset_version_id:=md5(NEW.asset_id::text||':revision:'||NEW.asset_revision::text||':'||NEW.asset_config_hash)::uuid;
 RETURN NEW;
END;$body$;
ALTER FUNCTION portal.run_asset_binding() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.run_asset_binding() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER run_asset_binding BEFORE INSERT OR UPDATE ON portal.runs FOR EACH ROW EXECUTE FUNCTION portal.run_asset_binding();

CREATE FUNCTION security.run_asset_resolve(p_session uuid,p_tenant uuid,p_agent text,p_asset uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE expected uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_agent IS NULL OR p_agent NOT IN ('general','rules_rag') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 expected:=md5(p_tenant::text||':portal-agent:'||p_agent)::uuid;
 -- Only existing fixed aliases are executable. Draft/random/cross-tenant all return the same error.
 IF p_asset IS NOT NULL AND p_asset<>expected THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 RETURN expected;
END;$body$;
ALTER FUNCTION security.run_asset_resolve(uuid,uuid,text,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.run_asset_resolve(uuid,uuid,text,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.run_asset_resolve(uuid,uuid,text,uuid) TO ai_web;

CREATE OR REPLACE FUNCTION security.run_view(p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_result jsonb;v_usage text;v_terminal boolean;
BEGIN
 IF current_setting('app.run_scope',true) IS DISTINCT FROM 'owner' THEN
  RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF NOT EXISTS(SELECT 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id AND deleted_at IS NULL) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 v_terminal:=v_run.state IN ('completed','failed','cancelled','blocked','interrupted');
 SELECT CASE WHEN bool_or(c.state='usage_unknown') THEN 'unknown'
  WHEN bool_or(c.state IN ('reserved','dispatched')) THEN 'estimated'
  WHEN bool_or(c.state='settled') THEN 'final' ELSE 'none' END INTO v_usage
 FROM ops.call_attempts c WHERE c.tenant_id=p_tenant AND c.run_id=p_run;
 IF v_run.state='completed' THEN
  SELECT jsonb_build_object('message_id',m.message_id,'text',m.body,'evidence','[]'::jsonb) INTO v_result
  FROM portal.messages m WHERE m.tenant_id=p_tenant AND m.run_id=p_run AND m.role='assistant'
  ORDER BY m.sequence_no DESC LIMIT 1;
 END IF;
 RETURN jsonb_build_object('run_id',v_run.run_id,'tenant_id',v_run.tenant_id,'conversation_id',v_run.conversation_id,
  'agent_key',v_run.agent_key,'config_version',v_run.config_snapshot->'config_version',
  'asset_binding',CASE WHEN v_run.asset_id IS NULL THEN NULL ELSE jsonb_build_object(
   'source','legacy','asset_id',v_run.asset_id,'revision',v_run.asset_revision,
   'version_id',v_run.asset_version_id,'config_hash',v_run.asset_config_hash) END,'state',v_run.state,
  'stage',v_run.stage,'revision',v_run.revision,'is_terminal',v_terminal,'answer_kind',v_run.answer_kind,
  'content_status',CASE WHEN v_run.state='completed' AND v_result IS NOT NULL THEN 'final' WHEN v_terminal THEN 'unavailable' ELSE 'pending' END,
  'execution_mode',v_run.execution_mode,'usage_status',v_usage,'error_code',v_run.safe_error_code,
  'created_at',v_run.created_at,'ended_at',v_run.ended_at,'cancel_requested_at',v_run.cancel_requested_at,'result',v_result);
END; $body$;
