-- Delete access first; cleanup never reads payload or dispatches AI.
CREATE FUNCTION security.document_cleanup(p_session uuid,p_tenant uuid,p_document uuid,p_action text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;a security.document_access%ROWTYPE;v record;versions jsonb;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,true);
 SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document FOR UPDATE;
 IF NOT FOUND OR a.deleted_at IS NULL THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 IF p_action='purge' THEN
  SELECT coalesce(jsonb_agg(version_id),'[]') INTO versions FROM rag.document_versions WHERE tenant_id=p_tenant AND document_id=p_document;
  FOR v IN SELECT * FROM rag.index_builds WHERE tenant_id=p_tenant AND document_id=p_document ORDER BY index_id FOR UPDATE LOOP
   INSERT INTO rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,execution_mode,state,stage,origin_session_id)
   SELECT p_tenant,gen_random_uuid(),p_document,v.version_id,v.index_id,actor,'internal_cleanup',v.execution_mode,'queued','cleanup',p_session
   WHERE NOT EXISTS(SELECT 1 FROM rag.jobs WHERE tenant_id=p_tenant AND index_id=v.index_id AND job_kind='internal_cleanup' AND state IN ('queued','running','completed'));
   UPDATE rag.chunks SET text=NULL,location=NULL,embedding=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id=v.index_id;
   UPDATE rag.entities SET label=NULL,properties=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id=v.index_id;
   UPDATE rag.relations SET properties=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id=v.index_id;
   UPDATE rag.evidence SET exact_quote=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id=v.index_id;
   UPDATE rag.index_builds SET payload_purged=true WHERE tenant_id=p_tenant AND index_id=v.index_id;
  END LOOP;
  UPDATE rag.document_versions SET title=NULL,source_object_key=NULL,source_mapping=NULL,payload_purged=true WHERE tenant_id=p_tenant AND document_id=p_document;
  RETURN jsonb_build_object('version_ids',versions,'cleanup_state','pending');
 ELSIF p_action='finish' THEN
  UPDATE rag.jobs SET state='completed',stage='terminal',ended_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=p_tenant AND document_id=p_document AND job_kind='internal_cleanup' AND state='queued';
  RETURN jsonb_build_object('cleanup_state','completed');
 ELSE RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
END;$body$;

CREATE FUNCTION security.document_retry(p_session uuid,p_tenant uuid,p_job uuid,p_client uuid,p_expected bigint,p_hash bytea,p_new_job uuid,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;j rag.jobs%ROWTYPE;r security.operation_receipts%ROWTYPE;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,true);PERFORM security.execution_scope(p_tenant);
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM security.document_access WHERE tenant_id=p_tenant AND document_id=j.document_id AND deleted_at IS NULL) THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 SELECT * INTO r FROM security.operation_receipts WHERE tenant_id=p_tenant AND initiator_user_id=actor AND operation_kind='retry' AND client_operation_id=p_client;
 IF FOUND THEN
  IF r.request_hash IS DISTINCT FROM p_hash THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
  RETURN jsonb_build_object('job_id',r.job_id,'replayed',true);
 END IF;
 IF j.execution_mode IS DISTINCT FROM p_mode OR j.job_kind<>'internal_index' OR j.state NOT IN ('failed','interrupted','blocked') OR j.revision IS DISTINCT FROM p_expected
 OR EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND index_id=j.index_id AND state IN ('dispatched','usage_unknown'))
 THEN RAISE EXCEPTION 'RETRY_DENIED' USING ERRCODE='A0409'; END IF;
 INSERT INTO rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,execution_mode,retry_of,attempt,origin_session_id)
 VALUES(p_tenant,p_new_job,j.document_id,j.version_id,j.index_id,actor,'internal_index',j.execution_mode,j.job_id,j.attempt+1,p_session);
 INSERT INTO security.operation_receipts(tenant_id,initiator_user_id,operation_kind,client_operation_id,request_hash,document_id,version_id,index_id,job_id)
 VALUES(p_tenant,actor,'retry',p_client,p_hash,j.document_id,j.version_id,j.index_id,p_new_job);
 RETURN jsonb_build_object('job_id',p_new_job,'replayed',false);
END;$body$;

CREATE FUNCTION security.document_pending(p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE result jsonb;
BEGIN
 IF session_user<>'ai_web' OR p_mode NOT IN ('mock','real') THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 UPDATE rag.jobs j SET state='blocked',stage='terminal',ended_at=clock_timestamp(),revision=revision+1,safe_error_code='AUTHORIZATION_REVOKED'
 WHERE j.execution_mode=p_mode AND j.origin_session_id IS NOT NULL AND j.state IN ('queued','running') AND NOT EXISTS(
 SELECT 1 FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id JOIN security.memberships m ON m.user_id=a.user_id AND m.tenant_id=j.tenant_id
 JOIN security.tenants t ON t.tenant_id=m.tenant_id WHERE s.session_id=j.origin_session_id AND s.user_id=j.initiator_user_id AND a.active AND m.active AND t.active
 AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes'
 AND (m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access p JOIN security.managed_tenants mt ON mt.user_id=p.user_id WHERE p.user_id=a.user_id AND p.active AND p.is_padmin AND mt.tenant_id=j.tenant_id AND mt.active)));
 SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT tenant_id,job_id,document_id,origin_session_id,initiator_user_id,job_kind FROM rag.jobs WHERE execution_mode=p_mode AND origin_session_id IS NOT NULL AND (state='queued' OR (state='running' AND lease_expires_at<=clock_timestamp())) ORDER BY created_at,job_id LIMIT 100) x;
 RETURN result;
END;$body$;

ALTER FUNCTION security.document_cleanup(uuid,uuid,uuid,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_cleanup(uuid,uuid,uuid,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_cleanup(uuid,uuid,uuid,text) TO ai_web;

ALTER FUNCTION security.document_retry(uuid,uuid,uuid,uuid,bigint,bytea,uuid,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_retry(uuid,uuid,uuid,uuid,bigint,bytea,uuid,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_retry(uuid,uuid,uuid,uuid,bigint,bytea,uuid,text) TO ai_web;

ALTER FUNCTION security.document_pending(text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_pending(text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_pending(text) TO ai_web;

CREATE FUNCTION security.document_orphan_absent(p_session uuid,p_tenant uuid,p_document uuid,p_version uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 PERFORM security.document_manage(p_session,p_tenant,true);
 PERFORM pg_advisory_xact_lock(hashtextextended('tenants/'||p_tenant::text||'/documents/'||p_document::text||'/'||p_version::text||'/source',0));
 RETURN NOT EXISTS(SELECT 1 FROM rag.document_versions WHERE tenant_id=p_tenant AND document_id=p_document AND version_id=p_version);
END;$body$;
ALTER FUNCTION security.document_orphan_absent(uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_orphan_absent(uuid,uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_orphan_absent(uuid,uuid,uuid,uuid) TO ai_web;

CREATE FUNCTION security.document_admission_window(p_session uuid,p_tenant uuid,p_digest bytea)
RETURNS TABLE(allowed boolean,retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_start timestamptz;v_now timestamptz;v_count integer;
BEGIN
 PERFORM security.document_manage(p_session,p_tenant,true);
 IF p_digest IS NULL OR octet_length(p_digest)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 INSERT INTO security.login_windows VALUES('document_admission','principal',p_digest,clock_timestamp(),0) ON CONFLICT DO NOTHING;
 SELECT window_started_at,count INTO v_start,v_count FROM security.login_windows
 WHERE purpose='document_admission' AND key_kind='principal' AND key_digest=p_digest FOR UPDATE;
 PERFORM security.document_manage(p_session,p_tenant,true);v_now:=clock_timestamp();
 IF v_now>=v_start+interval '1 minute' THEN
  v_start:=v_now;v_count:=0;
  UPDATE security.login_windows SET window_started_at=v_start,count=0 WHERE purpose='document_admission' AND key_kind='principal' AND key_digest=p_digest;
 END IF;
 IF v_count>=10 THEN RETURN QUERY SELECT false,GREATEST(1,ceil(extract(epoch FROM v_start+interval '1 minute'-v_now))::integer);RETURN; END IF;
 UPDATE security.login_windows SET count=count+1 WHERE purpose='document_admission' AND key_kind='principal' AND key_digest=p_digest;
 RETURN QUERY SELECT true,0;
END; $body$;
ALTER FUNCTION security.document_admission_window(uuid,uuid,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_admission_window(uuid,uuid,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_admission_window(uuid,uuid,bytea) TO ai_web;

CREATE OR REPLACE FUNCTION rag.guard_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $body$
DECLARE fields text[];
BEGIN
 fields := CASE TG_TABLE_NAME
  WHEN 'document_versions' THEN ARRAY['tenant_id','document_id','version_id','version_no','source_sha256','media_type','byte_length','character_length','ingest_hmac','parser_revision','created_at']
  WHEN 'index_builds' THEN ARRAY['tenant_id','document_id','version_id','index_id','execution_mode','pipeline_revision','source_fingerprint','embedding_model','embedding_dimensions','schema_revision','created_at']
  WHEN 'jobs' THEN ARRAY['tenant_id','job_id','document_id','version_id','index_id','initiator_user_id','job_kind','execution_mode','retry_of','attempt','origin_session_id','created_at'] END;
 IF EXISTS(SELECT 1 FROM unnest(fields) f WHERE to_jsonb(OLD)->f IS DISTINCT FROM to_jsonb(NEW)->f) THEN
  RAISE EXCEPTION 'DOCUMENT_IDENTITY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='document_versions' AND NOT (to_jsonb(NEW)->>'payload_purged')::boolean AND
  (to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW)) THEN RAISE EXCEPTION 'SOURCE_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF (to_jsonb(OLD)->>'payload_purged')::boolean AND NOT (to_jsonb(NEW)->>'payload_purged')::boolean THEN
  RAISE EXCEPTION 'PAYLOAD_PURGE_IRREVERSIBLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;$body$;

CREATE OR REPLACE FUNCTION security.document_job_authorized(p_tenant uuid,p_document uuid,p_version uuid,p_index uuid DEFAULT NULL) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE job uuid; epoch bigint; claim bytea; tenant uuid;
BEGIN
 IF session_user<>'ai_index' THEN RETURN false; END IF;
 job:=nullif(current_setting('app.job_id',true),'')::uuid;
 epoch:=nullif(current_setting('app.job_epoch',true),'')::bigint;
 tenant:=nullif(current_setting('app.job_tenant_id',true),'')::uuid;
 IF current_setting('app.job_claim',true) !~ '^[0-9a-f]{64}$' THEN RETURN false; END IF;
 claim:=decode(current_setting('app.job_claim',true),'hex');
 IF job IS NULL OR epoch IS NULL OR tenant IS DISTINCT FROM p_tenant THEN RETURN false; END IF;
 RETURN EXISTS(SELECT 1 FROM security.job_authorizations a
  JOIN rag.jobs j ON (j.tenant_id,j.job_id)=(a.tenant_id,a.job_id)
  JOIN rag.index_builds i ON (i.tenant_id,i.index_id)=(a.tenant_id,a.index_id)
  JOIN rag.document_versions v ON (v.tenant_id,v.document_id,v.version_id)=(a.tenant_id,a.document_id,a.version_id)
  JOIN security.document_access d ON (d.tenant_id,d.document_id)=(a.tenant_id,a.document_id)
  JOIN security.accounts u ON u.user_id=a.initiator_user_id AND u.active
  JOIN security.tenants t ON t.tenant_id=a.tenant_id AND t.active
  JOIN security.memberships m ON (m.tenant_id,m.user_id)=(a.tenant_id,a.initiator_user_id) AND m.active
  WHERE (a.tenant_id,a.job_id,a.document_id,a.version_id)=(p_tenant,job,p_document,p_version)
   AND (p_index IS NULL OR a.index_id=p_index) AND a.action='internal_index' AND j.job_kind='internal_index'
   AND a.revoked_at IS NULL AND a.expires_at>statement_timestamp() AND a.lease_hash=claim AND a.lease_epoch=epoch
   AND j.state='running' AND j.lease_epoch=epoch AND j.lease_expires_at>statement_timestamp()
   AND d.deleted_at IS NULL AND NOT v.payload_purged AND NOT i.payload_purged AND i.state IN ('staging','building')
   AND (j.origin_session_id IS NULL OR (EXISTS(SELECT 1 FROM security.sessions s WHERE s.session_id=j.origin_session_id AND s.user_id=u.user_id AND s.auth_revision=u.auth_revision AND s.revoked_at IS NULL AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes') AND EXISTS(SELECT 1 FROM portal.agent_configs ac WHERE ac.tenant_id=p_tenant AND ac.agent_key='rules_rag' AND ac.enabled)))
   AND (m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id
     WHERE pa.user_id=u.user_id AND pa.active AND pa.is_padmin AND mt.tenant_id=a.tenant_id AND mt.active)));
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
END;$body$;
