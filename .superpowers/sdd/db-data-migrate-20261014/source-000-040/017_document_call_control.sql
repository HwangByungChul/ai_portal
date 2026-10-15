-- Release only an unfired embedding reservation using the saved Job capability.
-- Revocation/stop must not prevent budget cleanup; this grants no content access.
CREATE FUNCTION security.document_embedding_release(p_tenant uuid,p_job uuid,p_epoch bigint,p_worker bytea,p_call uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE c ops.call_attempts%ROWTYPE;j rag.jobs%ROWTYPE;a security.job_authorizations%ROWTYPE;
BEGIN
 IF session_user<>'ai_index' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM security.execution_scope(p_tenant);
 SELECT * INTO c FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND job_id=p_job AND operation='embed_document' AND execution_epoch=p_epoch;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM budget_id FROM ops.project_budget WHERE budget_id=c.budget_id FOR UPDATE;
 PERFORM tenant_id FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=c.budget_id FOR UPDATE;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 SELECT * INTO a FROM security.job_authorizations WHERE tenant_id=p_tenant AND job_id=p_job FOR SHARE;
 IF p_worker IS NULL OR octet_length(p_worker)<>32 OR j.lease_epoch IS DISTINCT FROM p_epoch
 OR a.lease_epoch IS DISTINCT FROM p_epoch OR a.lease_hash IS DISTINCT FROM p_worker
 OR c.index_id IS DISTINCT FROM j.index_id THEN RETURN false; END IF;
 RETURN security.call_release_internal(p_tenant,p_call);
END;$body$;
ALTER FUNCTION security.document_embedding_release(uuid,uuid,bigint,bytea,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_embedding_release(uuid,uuid,bigint,bytea,uuid) FROM PUBLIC,ai_web,ai_meter,ai_index;
GRANT EXECUTE ON FUNCTION security.document_embedding_release(uuid,uuid,bigint,bytea,uuid) TO ai_index;

-- SELECT FOR SHARE also applies UPDATE USING policies. Permit only the
-- current authorized Job's metadata lock; WITH CHECK false forbids row writes.
CREATE POLICY agent_job_control_lock ON portal.agent_configs FOR UPDATE TO ai_policy_executor
 USING(session_user='ai_index' AND tenant_id::text=current_setting('app.job_tenant_id',true)
 AND EXISTS(SELECT 1 FROM rag.jobs j WHERE j.tenant_id=agent_configs.tenant_id
 AND j.job_id=NULLIF(current_setting('app.job_id',true),'')::uuid
 AND security.document_job_authorized(j.tenant_id,j.document_id,j.version_id,j.index_id)))
 WITH CHECK(false);

-- Recheck current policy before publishing an index after provider I/O.
CREATE OR REPLACE FUNCTION security.document_publish(p_tenant uuid,p_job uuid,p_epoch bigint,p_claim bytea,p_counts jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE idx uuid;j rag.jobs%ROWTYPE;i rag.index_builds%ROWTYPE;project ops.project_budget%ROWTYPE;tenant ops.tenant_budgets%ROWTYPE;current_config bigint;
BEGIN
 PERFORM security.execution_scope(p_tenant);
 IF p_counts IS NULL OR jsonb_typeof(p_counts)<>'object' OR NOT(p_counts ?& ARRAY['chunks','entities','relations','evidence']) OR p_counts-ARRAY['chunks','entities','relations','evidence']::text[]<>'{}'::jsonb OR EXISTS(SELECT 1 FROM jsonb_each(p_counts) WHERE value::text !~ '^[0-9]{1,4}$') THEN RAISE EXCEPTION 'INDEX_INCOMPLETE' USING ERRCODE='A0422'; END IF;
 idx:=security.document_worker_guard(p_tenant,p_job,p_epoch,p_claim);
 -- Serialize publication with current stop/budget policy; settled usage survives rejection.
 SELECT * INTO project FROM ops.project_budget WHERE budget_id=(SELECT budget_id FROM ops.call_attempts WHERE tenant_id=p_tenant AND index_id=idx AND operation='embed_document' AND state='settled' ORDER BY created_at DESC LIMIT 1) FOR UPDATE;
 SELECT * INTO tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=project.budget_id FOR UPDATE;
 SELECT config_version INTO current_config FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' FOR SHARE;
 IF project.budget_id IS NULL OR tenant.budget_id IS NULL THEN RAISE EXCEPTION 'BUDGET_NOT_READY' USING ERRCODE='B0404'; END IF;
 IF project.stopped OR project.stop_latch OR tenant.stopped THEN RAISE EXCEPTION 'PROJECT_STOPPED' USING ERRCODE='B0405'; END IF;
 IF EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND index_id=idx AND operation='embed_document' AND state<>'released_no_dispatch' AND config_revision IS DISTINCT FROM current_config) THEN RAISE EXCEPTION 'CONFIG_CHANGED' USING ERRCODE='B0403'; END IF;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job;
 SELECT * INTO i FROM rag.index_builds WHERE tenant_id=p_tenant AND index_id=idx FOR UPDATE;
 IF (p_counts->>'chunks')::integer NOT BETWEEN 1 AND 128 OR (p_counts->>'entities')::integer>512 OR (p_counts->>'relations')::integer>1024 OR (p_counts->>'evidence')::integer>512 OR EXISTS(SELECT 1 FROM rag.chunks c WHERE c.tenant_id=p_tenant AND c.index_id=idx AND NOT c.payload_purged AND NOT EXISTS(SELECT 1 FROM ops.call_attempts call WHERE call.tenant_id=c.tenant_id AND call.call_id=c.call_id AND call.index_id=idx AND call.batch_ordinal=c.batch_ordinal AND call.mode=i.execution_mode AND call.state='settled' AND call.operation='embed_document' AND NOT call.slot_held AND NOT call.cost_overrun)) OR i.expected_batches=0 OR i.completed_batches<>i.expected_batches OR (SELECT count(*) FROM jsonb_object_keys(i.checkpoint_summary))<>i.expected_batches
 OR (SELECT count(*) FROM rag.chunks WHERE tenant_id=p_tenant AND index_id=idx AND NOT payload_purged)<>(p_counts->>'chunks')::integer
 OR (SELECT count(*) FROM rag.entities WHERE tenant_id=p_tenant AND index_id=idx AND NOT payload_purged)<>(p_counts->>'entities')::integer
 OR (SELECT count(*) FROM rag.relations WHERE tenant_id=p_tenant AND index_id=idx AND NOT payload_purged)<>(p_counts->>'relations')::integer
 OR (SELECT count(*) FROM rag.evidence WHERE tenant_id=p_tenant AND index_id=idx AND NOT payload_purged)<>(p_counts->>'evidence')::integer
 THEN RAISE EXCEPTION 'INDEX_INCOMPLETE' USING ERRCODE='A0422'; END IF;
 UPDATE rag.index_builds SET state='published',revision=revision+1 WHERE tenant_id=p_tenant AND index_id=idx;
 INSERT INTO security.document_publications(tenant_id,document_id,version_id,published_index_id,active) VALUES(p_tenant,j.document_id,j.version_id,idx,true)
 ON CONFLICT(tenant_id,document_id,version_id) DO UPDATE SET published_index_id=excluded.published_index_id,active=true,revision=document_publications.revision+1;
 UPDATE rag.jobs SET state='completed',stage='terminal',ended_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=p_tenant AND job_id=p_job;
 UPDATE security.job_authorizations SET revoked_at=clock_timestamp() WHERE tenant_id=p_tenant AND job_id=p_job;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions) VALUES(gen_random_uuid(),'tenant',p_tenant,j.initiator_user_id,'document.publish',j.document_id,'success',jsonb_build_object('epoch',p_epoch));
 RETURN true;
END;$body$;
