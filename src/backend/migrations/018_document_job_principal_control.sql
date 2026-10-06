-- Index Jobs use saved admission and current principal, never HTTP session lifetime.
CREATE FUNCTION security.document_background_control(p_actor uuid,p_tenant uuid,p_job uuid,p_action text,p_epoch bigint DEFAULT NULL,p_claim bytea DEFAULT NULL,p_data jsonb DEFAULT '{}') RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;j rag.jobs%ROWTYPE;a security.document_access%ROWTYPE;i rag.index_builds%ROWTYPE;auth security.job_authorizations%ROWTYPE;new_epoch bigint;
BEGIN
 IF session_user<>'ai_index' OR p_action IS NULL OR p_action NOT IN ('claim','heartbeat','plan','fail','review') THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM security.execution_scope(p_tenant);PERFORM set_config('app.job_tenant_id',p_tenant::text,true);actor:=p_actor;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job;
 IF NOT FOUND THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 PERFORM user_id FROM security.accounts WHERE user_id=actor FOR SHARE;
 PERFORM tenant_id FROM security.tenants WHERE tenant_id=p_tenant FOR SHARE;
 PERFORM user_id FROM security.platform_access WHERE user_id=actor FOR SHARE;
 PERFORM user_id FROM security.memberships WHERE tenant_id=p_tenant AND user_id=actor FOR SHARE;
 PERFORM user_id FROM security.managed_tenants WHERE tenant_id=p_tenant AND user_id=actor FOR SHARE;
 SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=j.document_id FOR UPDATE;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 
 IF j.initiator_user_id IS DISTINCT FROM actor OR j.origin_session_id IS NULL OR j.job_kind<>'internal_index' OR a.deleted_at IS NOT NULL
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 IF p_action NOT IN ('fail','review') AND NOT EXISTS(
 SELECT 1 FROM security.accounts u JOIN security.tenants t ON t.tenant_id=p_tenant
 JOIN security.memberships m ON m.tenant_id=t.tenant_id AND m.user_id=u.user_id
 WHERE u.user_id=actor AND u.active AND t.active AND m.active
 AND (m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id
 WHERE pa.user_id=actor AND pa.active AND pa.is_padmin AND mt.tenant_id=p_tenant AND mt.active)))
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 IF p_action NOT IN ('fail','review') AND NOT EXISTS(SELECT 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' AND enabled)
 THEN RAISE EXCEPTION 'AGENT_DISABLED' USING ERRCODE='B0402'; END IF;
 SELECT * INTO i FROM rag.index_builds WHERE tenant_id=p_tenant AND index_id=j.index_id FOR UPDATE;
 IF p_action='claim' THEN
  IF j.execution_mode IS DISTINCT FROM p_data->>'mode' THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
  IF p_claim IS NULL OR octet_length(p_claim)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  IF j.state NOT IN ('queued','running') OR (j.state='running' AND j.lease_expires_at>clock_timestamp()) THEN RETURN NULL; END IF;
  new_epoch:=j.lease_epoch+1;
  UPDATE rag.jobs SET state='running',started_at=coalesce(started_at,clock_timestamp()),heartbeat_at=clock_timestamp(),lease_expires_at=LEAST(clock_timestamp()+interval '60 seconds',coalesce(started_at,clock_timestamp())+interval '300 seconds'),lease_epoch=new_epoch,revision=revision+1 WHERE tenant_id=p_tenant AND job_id=p_job;
  INSERT INTO security.job_authorizations(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,action,lease_hash,lease_epoch,expires_at)
  VALUES(p_tenant,p_job,j.document_id,j.version_id,j.index_id,actor,'internal_index',p_claim,new_epoch,LEAST(clock_timestamp()+interval '60 seconds',coalesce(j.started_at,clock_timestamp())+interval '300 seconds'))
  ON CONFLICT(tenant_id,job_id) DO UPDATE SET lease_hash=excluded.lease_hash,lease_epoch=excluded.lease_epoch,expires_at=excluded.expires_at,revoked_at=NULL;
  UPDATE rag.index_builds SET state='building',revision=revision+1 WHERE tenant_id=p_tenant AND index_id=j.index_id;
  RETURN jsonb_build_object('epoch',new_epoch,'document_id',j.document_id,'version_id',j.version_id,'index_id',j.index_id,'mode',j.execution_mode,'source_fingerprint',encode(i.source_fingerprint,'hex'));
 END IF;
 SELECT * INTO auth FROM security.job_authorizations WHERE tenant_id=p_tenant AND job_id=p_job;
 IF j.state<>'running' OR j.lease_epoch IS DISTINCT FROM p_epoch OR auth.lease_hash IS DISTINCT FROM p_claim OR p_claim IS NULL
 OR auth.revoked_at IS NOT NULL OR auth.expires_at<=clock_timestamp() OR j.lease_expires_at<=clock_timestamp() OR j.started_at+interval '300 seconds'<=clock_timestamp()
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 IF p_action='heartbeat' THEN
  UPDATE rag.jobs SET heartbeat_at=clock_timestamp(),lease_expires_at=LEAST(clock_timestamp()+interval '60 seconds',started_at+interval '300 seconds') WHERE tenant_id=p_tenant AND job_id=p_job;
  UPDATE security.job_authorizations SET expires_at=LEAST(clock_timestamp()+interval '60 seconds',j.started_at+interval '300 seconds') WHERE tenant_id=p_tenant AND job_id=p_job;
 ELSIF p_action='plan' THEN
  IF jsonb_typeof(p_data)<>'object' OR (p_data->>'batches')::integer NOT BETWEEN 1 AND 16 OR p_data->>'fingerprint'<>encode(i.source_fingerprint,'hex') THEN RAISE EXCEPTION 'PLAN_REJECTED' USING ERRCODE='A0422'; END IF;
  UPDATE rag.index_builds SET expected_batches=(p_data->>'batches')::integer,coverage=p_data->'coverage' WHERE tenant_id=p_tenant AND index_id=j.index_id;
  UPDATE rag.jobs SET stage='embed_batches' WHERE tenant_id=p_tenant AND job_id=p_job;
 ELSIF p_action IN ('fail','review') THEN
  UPDATE rag.jobs SET state=CASE WHEN p_action='review' THEN 'needs_review' ELSE 'failed' END,stage='terminal',safe_error_code=p_data->>'code',ended_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=p_tenant AND job_id=p_job;
  UPDATE rag.index_builds SET state='failed',revision=revision+1 WHERE tenant_id=p_tenant AND index_id=j.index_id;
 ELSE RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 RETURN jsonb_build_object('ok',true);
END;$body$;
ALTER FUNCTION security.document_background_control(uuid,uuid,uuid,text,bigint,bytea,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_background_control(uuid,uuid,uuid,text,bigint,bytea,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_background_control(uuid,uuid,uuid,text,bigint,bytea,jsonb) TO ai_index;

CREATE OR REPLACE FUNCTION security.document_worker_guard(p_tenant uuid,p_job uuid,p_epoch bigint,p_claim bytea) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE j rag.jobs%ROWTYPE;
BEGIN
 IF session_user<>'ai_index' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job;
 IF NOT FOUND THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 PERFORM set_config('app.job_id',p_job::text,true);PERFORM set_config('app.job_epoch',p_epoch::text,true);PERFORM set_config('app.job_tenant_id',p_tenant::text,true);PERFORM set_config('app.job_claim',encode(p_claim,'hex'),true);
 PERFORM user_id FROM security.accounts WHERE user_id=j.initiator_user_id FOR SHARE;
 PERFORM tenant_id FROM security.tenants WHERE tenant_id=p_tenant FOR SHARE;
 PERFORM user_id FROM security.platform_access WHERE user_id=j.initiator_user_id FOR SHARE;
 PERFORM user_id FROM security.memberships WHERE tenant_id=p_tenant AND user_id=j.initiator_user_id FOR SHARE;
 PERFORM user_id FROM security.managed_tenants WHERE tenant_id=p_tenant AND user_id=j.initiator_user_id FOR SHARE;
 PERFORM tenant_id FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' FOR SHARE;
 PERFORM document_id FROM security.document_access WHERE tenant_id=p_tenant AND document_id=j.document_id FOR UPDATE;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;

 IF NOT security.document_job_authorized(p_tenant,j.document_id,j.version_id,j.index_id)
 OR j.started_at+interval '300 seconds'<=clock_timestamp()
 OR NOT EXISTS(SELECT 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' AND enabled)
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 RETURN j.index_id;
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
   AND EXISTS(SELECT 1 FROM portal.agent_configs ac WHERE ac.tenant_id=p_tenant AND ac.agent_key='rules_rag' AND ac.enabled)
   AND (m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id
     WHERE pa.user_id=u.user_id AND pa.active AND pa.is_padmin AND mt.tenant_id=a.tenant_id AND mt.active)));
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
END;$body$;
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
 OR (j.job_kind='internal_cleanup' AND EXISTS(SELECT 1 FROM security.sessions s WHERE s.session_id=j.origin_session_id AND s.user_id=a.user_id AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes'))));
 SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT tenant_id,job_id,document_id,origin_session_id,initiator_user_id,job_kind FROM rag.jobs WHERE execution_mode=p_mode AND origin_session_id IS NOT NULL AND (state='queued' OR (state='running' AND lease_expires_at<=clock_timestamp())) ORDER BY created_at,job_id LIMIT 100) x;
 RETURN result;
END;$body$;
