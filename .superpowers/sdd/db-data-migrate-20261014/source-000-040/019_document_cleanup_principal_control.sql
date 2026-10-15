-- Saved deletion admission grants only bounded, metadata-only cleanup.
CREATE FUNCTION security.document_cleanup_background(p_actor uuid,p_tenant uuid,p_document uuid,p_job uuid,p_action text,p_mode text,p_epoch bigint DEFAULT NULL,p_claim bytea DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE j rag.jobs%ROWTYPE; a security.document_access%ROWTYPE; cap security.job_authorizations%ROWTYPE; versions jsonb; epoch bigint;
BEGIN
 IF session_user<>'ai_index' OR p_action IS NULL OR p_action NOT IN ('claim','purge','heartbeat','finish','release') OR p_mode IS NULL OR p_mode NOT IN ('mock','real') THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM security.execution_scope(p_tenant); PERFORM set_config('app.job_tenant_id',p_tenant::text,true);
 PERFORM user_id FROM security.accounts WHERE user_id=p_actor FOR SHARE;
 PERFORM tenant_id FROM security.tenants WHERE tenant_id=p_tenant FOR SHARE;
 PERFORM user_id FROM security.platform_access WHERE user_id=p_actor FOR SHARE;
 PERFORM user_id FROM security.memberships WHERE tenant_id=p_tenant AND user_id=p_actor FOR SHARE;
 PERFORM user_id FROM security.managed_tenants WHERE tenant_id=p_tenant AND user_id=p_actor FOR SHARE;
 SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document FOR UPDATE;
 IF NOT FOUND OR a.deleted_at IS NULL THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 IF p_action<>'release' AND NOT EXISTS(SELECT 1 FROM security.accounts u JOIN security.tenants t ON t.tenant_id=p_tenant JOIN security.memberships m ON m.tenant_id=t.tenant_id AND m.user_id=u.user_id WHERE u.user_id=p_actor AND u.active AND t.active AND m.active AND (m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id WHERE pa.user_id=p_actor AND pa.active AND pa.is_padmin AND mt.tenant_id=p_tenant AND mt.active))) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 IF p_job IS NULL AND p_action='claim' THEN
  SELECT job_id INTO p_job FROM rag.jobs WHERE tenant_id=p_tenant AND document_id=p_document AND initiator_user_id=p_actor AND job_kind='internal_cleanup' AND execution_mode=p_mode AND (state='queued' OR (state='running' AND lease_expires_at<=clock_timestamp())) ORDER BY created_at,job_id LIMIT 1;
 END IF;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 IF NOT FOUND OR j.document_id IS DISTINCT FROM p_document OR j.initiator_user_id IS DISTINCT FROM p_actor OR j.job_kind<>'internal_cleanup' OR j.execution_mode IS DISTINCT FROM p_mode OR j.origin_session_id IS NULL THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 IF p_action='claim' THEN
  IF p_claim IS NULL OR octet_length(p_claim)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  IF j.state NOT IN ('queued','running') OR EXISTS(SELECT 1 FROM rag.jobs WHERE tenant_id=p_tenant AND document_id=p_document AND job_kind='internal_cleanup' AND state='running' AND lease_expires_at>clock_timestamp()) THEN RETURN NULL; END IF;
  epoch:=j.lease_epoch+1;
  UPDATE rag.jobs SET state='running',started_at=clock_timestamp(),heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+interval '60 seconds',lease_epoch=epoch,revision=revision+1 WHERE tenant_id=p_tenant AND job_id=p_job;
  INSERT INTO security.job_authorizations(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,action,deletion_revision,lease_hash,lease_epoch,expires_at) VALUES(p_tenant,p_job,p_document,j.version_id,j.index_id,p_actor,'internal_cleanup',a.acl_revision,p_claim,epoch,clock_timestamp()+interval '60 seconds') ON CONFLICT(tenant_id,job_id) DO UPDATE SET deletion_revision=excluded.deletion_revision,lease_hash=excluded.lease_hash,lease_epoch=excluded.lease_epoch,expires_at=excluded.expires_at,revoked_at=NULL;
  RETURN jsonb_build_object('job_id',p_job,'epoch',epoch);
 END IF;
 SELECT * INTO cap FROM security.job_authorizations WHERE tenant_id=p_tenant AND job_id=p_job;
 IF NOT FOUND OR cap.action<>'internal_cleanup' OR cap.deletion_revision IS DISTINCT FROM a.acl_revision OR cap.revoked_at IS NOT NULL OR cap.expires_at<=clock_timestamp() OR cap.lease_hash IS DISTINCT FROM p_claim OR p_claim IS NULL OR cap.lease_epoch IS DISTINCT FROM p_epoch OR j.lease_epoch IS DISTINCT FROM p_epoch OR j.state<>'running' OR j.lease_expires_at<=clock_timestamp() OR j.started_at+interval '300 seconds'<=clock_timestamp() THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 IF p_action='purge' THEN
  SELECT coalesce(jsonb_agg(version_id),'[]') INTO versions FROM rag.document_versions WHERE tenant_id=p_tenant AND document_id=p_document;
  UPDATE rag.chunks SET text=NULL,location=NULL,embedding=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id IN (SELECT index_id FROM rag.index_builds WHERE tenant_id=p_tenant AND document_id=p_document);
  UPDATE rag.entities SET label=NULL,properties=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id IN (SELECT index_id FROM rag.index_builds WHERE tenant_id=p_tenant AND document_id=p_document);
  UPDATE rag.relations SET properties=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id IN (SELECT index_id FROM rag.index_builds WHERE tenant_id=p_tenant AND document_id=p_document);
  UPDATE rag.evidence SET exact_quote=NULL,payload_purged=true WHERE tenant_id=p_tenant AND index_id IN (SELECT index_id FROM rag.index_builds WHERE tenant_id=p_tenant AND document_id=p_document);
  UPDATE rag.index_builds SET payload_purged=true WHERE tenant_id=p_tenant AND document_id=p_document;
  UPDATE rag.document_versions SET title=NULL,source_object_key=NULL,source_mapping=NULL,payload_purged=true WHERE tenant_id=p_tenant AND document_id=p_document;
  RETURN jsonb_build_object('version_ids',versions,'cleanup_state','pending');
 ELSIF p_action='heartbeat' THEN
  UPDATE rag.jobs SET heartbeat_at=clock_timestamp(),lease_expires_at=LEAST(clock_timestamp()+interval '60 seconds',started_at+interval '300 seconds') WHERE tenant_id=p_tenant AND job_id=p_job;
  UPDATE security.job_authorizations SET expires_at=LEAST(clock_timestamp()+interval '60 seconds',j.started_at+interval '300 seconds') WHERE tenant_id=p_tenant AND job_id=p_job;
 ELSIF p_action='finish' THEN
  IF EXISTS(SELECT 1 FROM rag.document_versions WHERE tenant_id=p_tenant AND document_id=p_document AND NOT payload_purged) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
  UPDATE rag.jobs SET state='completed',stage='terminal',ended_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=p_tenant AND document_id=p_document AND job_kind='internal_cleanup' AND initiator_user_id=p_actor AND execution_mode=p_mode AND (state='queued' OR job_id=p_job);
  UPDATE security.job_authorizations SET revoked_at=clock_timestamp() WHERE tenant_id=p_tenant AND job_id=p_job;
 ELSIF p_action='release' THEN
  UPDATE rag.jobs SET state='queued',lease_expires_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=p_tenant AND job_id=p_job;
  UPDATE security.job_authorizations SET revoked_at=clock_timestamp() WHERE tenant_id=p_tenant AND job_id=p_job;
 END IF;
 RETURN jsonb_build_object('cleanup_state',CASE WHEN p_action='finish' THEN 'completed' ELSE 'pending' END);
END;$body$;
ALTER FUNCTION security.document_cleanup_background(uuid,uuid,uuid,uuid,text,text,bigint,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_cleanup_background(uuid,uuid,uuid,uuid,text,text,bigint,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_cleanup_background(uuid,uuid,uuid,uuid,text,text,bigint,bytea) TO ai_index;

CREATE OR REPLACE FUNCTION security.document_pending(p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE result jsonb;
BEGIN
 IF session_user<>'ai_web' OR p_mode NOT IN ('mock','real') THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 UPDATE rag.jobs j SET state='blocked',stage='terminal',ended_at=clock_timestamp(),revision=revision+1,safe_error_code='AUTHORIZATION_REVOKED'
 WHERE j.execution_mode=p_mode AND j.origin_session_id IS NOT NULL AND j.state IN ('queued','running') AND NOT EXISTS(
 SELECT 1 FROM security.accounts a JOIN security.memberships m ON m.user_id=a.user_id AND m.tenant_id=j.tenant_id
 JOIN security.tenants t ON t.tenant_id=m.tenant_id
 WHERE a.user_id=j.initiator_user_id AND a.active AND m.active AND t.active
 AND (m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access p JOIN security.managed_tenants mt ON mt.user_id=p.user_id WHERE p.user_id=a.user_id AND p.active AND p.is_padmin AND mt.tenant_id=j.tenant_id AND mt.active))
 AND ((j.job_kind='internal_index' AND EXISTS(SELECT 1 FROM security.document_access d WHERE d.tenant_id=j.tenant_id AND d.document_id=j.document_id AND d.deleted_at IS NULL))
 OR (j.job_kind='internal_cleanup' AND EXISTS(SELECT 1 FROM security.document_access d WHERE d.tenant_id=j.tenant_id AND d.document_id=j.document_id AND d.deleted_at IS NOT NULL))));
 SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT tenant_id,job_id,document_id,origin_session_id,initiator_user_id,job_kind FROM rag.jobs WHERE execution_mode=p_mode AND origin_session_id IS NOT NULL AND (state='queued' OR (state='running' AND lease_expires_at<=clock_timestamp())) ORDER BY created_at,job_id LIMIT 100) x;
 RETURN result;
END;$body$;
