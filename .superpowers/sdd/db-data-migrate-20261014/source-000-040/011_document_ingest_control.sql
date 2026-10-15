-- C03 fixed registration/Job capabilities; no raw content access for the policy executor.
ALTER TABLE rag.jobs ADD COLUMN origin_session_id uuid REFERENCES security.sessions;
ALTER TABLE rag.jobs ADD COLUMN started_at timestamptz;
GRANT INSERT ON rag.document_versions,rag.index_builds,rag.jobs TO ai_policy_executor;
GRANT SELECT(tenant_id,document_id,version_id,version_no,source_sha256,parser_revision,media_type,byte_length,character_length,payload_purged),UPDATE(title,source_object_key,source_mapping,payload_purged) ON rag.document_versions TO ai_policy_executor;
GRANT SELECT(tenant_id,document_id,version_id,index_id,execution_mode,pipeline_revision,source_fingerprint,embedding_model,embedding_dimensions,state,revision,expected_batches,completed_batches,checkpoint_summary,coverage,payload_purged),UPDATE(state,revision,expected_batches,completed_batches,checkpoint_summary,coverage,payload_purged) ON rag.index_builds TO ai_policy_executor;
GRANT SELECT ON rag.jobs TO ai_policy_executor;
GRANT UPDATE(state,stage,revision,safe_error_code,heartbeat_at,lease_epoch,lease_expires_at,ended_at,started_at) ON rag.jobs TO ai_policy_executor;
CREATE POLICY versions_register ON rag.document_versions FOR INSERT TO ai_policy_executor WITH CHECK(true);
CREATE POLICY versions_purge ON rag.document_versions FOR UPDATE TO ai_policy_executor USING(true) WITH CHECK(true);
CREATE POLICY indexes_control ON rag.index_builds TO ai_policy_executor USING(true) WITH CHECK(true);
CREATE POLICY jobs_control ON rag.jobs TO ai_policy_executor USING(true) WITH CHECK(true);

CREATE FUNCTION security.document_manage(p_session uuid,p_tenant uuid,p_lock boolean) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;
BEGIN
 actor:=security.run_authorize(p_session,p_tenant,p_lock);
 IF NOT security.can_manage_current_tenant(p_tenant) THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403'; END IF;
 RETURN actor;
END;$body$;

CREATE FUNCTION security.document_register(p_session uuid,p_tenant uuid,p_client uuid,p_hash bytea,p_doc uuid,p_version uuid,p_index uuid,p_job uuid,p_existing boolean,p_expected bigint,p_owner uuid,p_visibility text,p_readers uuid[],p_title text,p_media text,p_sha bytea,p_bytes integer,p_chars integer,p_source_fp bytea,p_mode text,p_mapping jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid; receipt security.operation_receipts%ROWTYPE;access security.document_access%ROWTYPE;v_no integer;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,true);
 IF p_hash IS NULL OR octet_length(p_hash)<>32 OR p_source_fp IS NULL OR octet_length(p_source_fp)<>32 OR p_client IS NULL
 OR p_visibility IS NULL OR p_visibility NOT IN ('org','private') OR p_mode IS NULL OR p_mode NOT IN ('mock','real')
 OR p_existing IS NULL OR p_readers IS NULL OR cardinality(p_readers)>20 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||actor::text||p_client::text,0));
 SELECT * INTO receipt FROM security.operation_receipts WHERE tenant_id=p_tenant AND initiator_user_id=actor AND operation_kind='upload' AND client_operation_id=p_client;
 IF FOUND THEN
  IF receipt.request_hash IS DISTINCT FROM p_hash THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
  RETURN jsonb_build_object('document_id',receipt.document_id,'version_id',receipt.version_id,'index_id',receipt.index_id,'job_id',receipt.job_id,'replayed',true);
 END IF;
 IF p_existing THEN
  SELECT * INTO access FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_doc FOR UPDATE;
  IF NOT FOUND OR access.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
  IF access.visibility='private' AND access.owner_user_id<>actor AND NOT EXISTS(SELECT 1 FROM security.private_readers WHERE tenant_id=p_tenant AND document_id=p_doc AND user_id=actor)
  THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
  IF access.acl_revision IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  SELECT coalesce(max(version_no),0)+1 INTO v_no FROM rag.document_versions WHERE tenant_id=p_tenant AND document_id=p_doc;
  UPDATE security.document_access SET acl_revision=acl_revision+1 WHERE tenant_id=p_tenant AND document_id=p_doc;
 ELSE
  IF p_owner IS NULL OR (p_visibility='org' AND (p_owner<>actor OR cardinality(p_readers)<>0))
  OR EXISTS(SELECT 1 FROM unnest(array_append(p_readers,p_owner)) u WHERE NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts a ON a.user_id=m.user_id WHERE m.tenant_id=p_tenant AND m.user_id=u AND m.active AND a.active))
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  INSERT INTO security.document_access(tenant_id,document_id,owner_user_id,visibility) VALUES(p_tenant,p_doc,p_owner,p_visibility);
  INSERT INTO security.private_readers SELECT p_tenant,p_doc,u FROM (SELECT DISTINCT unnest(p_readers) u) x;
  v_no:=1;
 END IF;
 INSERT INTO rag.document_versions(tenant_id,document_id,version_id,version_no,title,source_object_key,source_sha256,media_type,byte_length,character_length,ingest_hmac,parser_revision,source_mapping)
 VALUES(p_tenant,p_doc,p_version,v_no,p_title,'tenants/'||p_tenant::text||'/documents/'||p_doc::text||'/'||p_version::text||'/source',p_sha,p_media,p_bytes,p_chars,p_hash,'source-map-v1',p_mapping);
 INSERT INTO rag.index_builds(tenant_id,document_id,version_id,index_id,execution_mode,pipeline_revision,source_fingerprint) VALUES(p_tenant,p_doc,p_version,p_index,p_mode,'rules-v1',p_source_fp);
 INSERT INTO rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,execution_mode,origin_session_id) VALUES(p_tenant,p_job,p_doc,p_version,p_index,actor,'internal_index',p_mode,p_session);
 INSERT INTO security.operation_receipts(tenant_id,initiator_user_id,operation_kind,client_operation_id,request_hash,document_id,version_id,index_id,job_id) VALUES(p_tenant,actor,'upload',p_client,p_hash,p_doc,p_version,p_index,p_job);
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions) VALUES(gen_random_uuid(),'tenant',p_tenant,actor,'document.upload',p_doc,'success',jsonb_build_object('version_no',v_no));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN jsonb_build_object('document_id',p_doc,'version_id',p_version,'index_id',p_index,'job_id',p_job,'replayed',false);
END;$body$;

CREATE FUNCTION security.document_job_control(p_session uuid,p_tenant uuid,p_job uuid,p_action text,p_epoch bigint DEFAULT NULL,p_claim bytea DEFAULT NULL,p_data jsonb DEFAULT '{}') RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;j rag.jobs%ROWTYPE;a security.document_access%ROWTYPE;i rag.index_builds%ROWTYPE;auth security.job_authorizations%ROWTYPE;new_epoch bigint;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,p_action<>'view');
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job;
 IF NOT FOUND THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 IF p_action='view' THEN RETURN jsonb_build_object('job_id',j.job_id,'document_id',j.document_id,'version_id',j.version_id,'index_id',j.index_id,'job_kind',j.job_kind,'execution_mode',j.execution_mode,'state',j.state,'stage',j.stage,'revision',j.revision,'safe_error_code',j.safe_error_code,'created_at',j.created_at,'ended_at',j.ended_at,'retry_allowed',j.job_kind='internal_index' AND j.state IN ('failed','blocked','interrupted'),'safe_reason',CASE WHEN j.state='needs_review' THEN 'INDEX_NEEDS_REVIEW' ELSE j.safe_error_code END,'publication_state',CASE WHEN EXISTS(SELECT 1 FROM security.document_publications p WHERE p.tenant_id=j.tenant_id AND p.document_id=j.document_id AND p.version_id=j.version_id AND p.active) THEN 'published' ELSE 'unpublished' END,'cleanup_state',CASE WHEN j.job_kind='internal_cleanup' AND j.state='completed' THEN 'completed' WHEN j.job_kind='internal_cleanup' THEN 'pending' ELSE 'not_required' END); END IF;
 SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=j.document_id FOR UPDATE;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 
 IF j.initiator_user_id<>actor OR j.origin_session_id IS DISTINCT FROM p_session OR j.job_kind<>'internal_index' OR a.deleted_at IS NOT NULL
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

CREATE FUNCTION security.document_admin_list(p_session uuid,p_tenant uuid,p_kind text,p_cursor uuid,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE result jsonb;
BEGIN
 PERFORM security.document_manage(p_session,p_tenant,false);
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 OR p_kind NOT IN ('documents','jobs') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_kind='documents' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT a.document_id,v.version_id,i.index_id,a.visibility,a.acl_revision AS revision,
 CASE WHEN a.deleted_at IS NULL THEN 'active' ELSE 'deleted' END AS access_state,
 CASE WHEN i.state='published' THEN 'completed' ELSE coalesce(j.state,'not_started') END AS processing_state,
 CASE WHEN p.active THEN 'published' ELSE 'unpublished' END AS publication_state,
 CASE WHEN a.deleted_at IS NULL THEN 'not_required' WHEN EXISTS(SELECT 1 FROM rag.jobs cj WHERE cj.tenant_id=a.tenant_id AND cj.document_id=a.document_id AND cj.job_kind='internal_cleanup' AND cj.state='completed') THEN 'completed' ELSE 'pending' END AS cleanup_state,
 coalesce(security.document_can_read(a.tenant_id,a.document_id,v.version_id,i.index_id),false) AS can_read_content
 FROM security.document_access a LEFT JOIN LATERAL(SELECT version_id,version_no FROM rag.document_versions WHERE tenant_id=a.tenant_id AND document_id=a.document_id ORDER BY version_no DESC LIMIT 1) v ON true
 LEFT JOIN LATERAL(SELECT index_id,state FROM rag.index_builds WHERE tenant_id=a.tenant_id AND document_id=a.document_id AND version_id=v.version_id ORDER BY created_at DESC LIMIT 1) i ON true
 LEFT JOIN LATERAL(SELECT state FROM rag.jobs WHERE tenant_id=a.tenant_id AND index_id=i.index_id AND job_kind='internal_index' ORDER BY created_at DESC LIMIT 1) j ON true
 LEFT JOIN security.document_publications p ON (p.tenant_id,p.document_id,p.version_id)=(a.tenant_id,a.document_id,v.version_id)
 WHERE a.tenant_id=p_tenant AND (p_cursor IS NULL OR a.document_id>p_cursor) ORDER BY a.document_id LIMIT p_limit) x;
 ELSE
  SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT job_id,document_id,version_id,index_id,job_kind,execution_mode,state,stage,revision,safe_error_code,created_at,ended_at FROM rag.jobs WHERE tenant_id=p_tenant AND (p_cursor IS NULL OR job_id>p_cursor) ORDER BY job_id LIMIT p_limit) x;
 END IF;
 RETURN jsonb_build_object('items',result,'next_cursor',CASE WHEN jsonb_array_length(result)=p_limit THEN result->(p_limit-1)->>CASE WHEN p_kind='documents' THEN 'document_id' ELSE 'job_id' END ELSE NULL END);
END;$body$;

CREATE FUNCTION security.document_worker_guard(p_tenant uuid,p_job uuid,p_epoch bigint,p_claim bytea) RETURNS uuid
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
 PERFORM session_id FROM security.sessions WHERE session_id=j.origin_session_id FOR SHARE;
 PERFORM user_id FROM security.memberships WHERE tenant_id=p_tenant AND user_id=j.initiator_user_id FOR SHARE;
 PERFORM user_id FROM security.managed_tenants WHERE tenant_id=p_tenant AND user_id=j.initiator_user_id FOR SHARE;
 PERFORM tenant_id FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' FOR SHARE;
 PERFORM document_id FROM security.document_access WHERE tenant_id=p_tenant AND document_id=j.document_id FOR UPDATE;
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;

 IF NOT security.document_job_authorized(p_tenant,j.document_id,j.version_id,j.index_id)
 OR NOT EXISTS(SELECT 1 FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id WHERE s.session_id=j.origin_session_id AND s.user_id=j.initiator_user_id AND s.revoked_at IS NULL AND s.auth_revision=a.auth_revision AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes')
 OR j.started_at+interval '300 seconds'<=clock_timestamp()
 OR NOT EXISTS(SELECT 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' AND enabled)
 THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 RETURN j.index_id;
END;$body$;

-- Metadata-only checkpoint, atomically called after scoped payload INSERTs.
GRANT SELECT(tenant_id,index_id,ordinal,batch_ordinal,call_id,payload_purged,source_sha256),UPDATE(text,location,embedding,payload_purged) ON rag.chunks TO ai_policy_executor;
GRANT SELECT(tenant_id,index_id,entity_id,payload_purged),UPDATE(label,properties,payload_purged) ON rag.entities TO ai_policy_executor;
GRANT SELECT(tenant_id,index_id,relation_id,payload_purged),UPDATE(properties,payload_purged) ON rag.relations TO ai_policy_executor;
GRANT SELECT(tenant_id,index_id,evidence_id,payload_purged),UPDATE(exact_quote,payload_purged) ON rag.evidence TO ai_policy_executor;
CREATE POLICY chunks_control ON rag.chunks TO ai_policy_executor USING(true) WITH CHECK(true);
CREATE POLICY entities_control ON rag.entities TO ai_policy_executor USING(true) WITH CHECK(true);
CREATE POLICY relations_control ON rag.relations TO ai_policy_executor USING(true) WITH CHECK(true);
CREATE POLICY evidence_control ON rag.evidence TO ai_policy_executor USING(true) WITH CHECK(true);

CREATE FUNCTION security.document_checkpoint(p_tenant uuid,p_job uuid,p_epoch bigint,p_claim bytea,p_batch integer,p_fingerprint text,p_count integer,p_call uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE idx uuid;i rag.index_builds%ROWTYPE;key text;
BEGIN
 PERFORM security.execution_scope(p_tenant);idx:=security.document_worker_guard(p_tenant,p_job,p_epoch,p_claim);key:=p_batch::text;
 SELECT * INTO i FROM rag.index_builds WHERE tenant_id=p_tenant AND index_id=idx FOR UPDATE;
 IF p_batch IS NULL OR p_batch NOT BETWEEN 0 AND i.expected_batches-1 OR p_count IS NULL OR p_count NOT BETWEEN 1 AND 8 OR p_fingerprint IS NULL OR p_fingerprint !~ '^[0-9a-f]{64}$'
 OR (SELECT count(*) FROM rag.chunks WHERE tenant_id=p_tenant AND index_id=idx AND batch_ordinal=p_batch AND call_id=p_call AND NOT payload_purged)<>p_count
 THEN RAISE EXCEPTION 'CHECKPOINT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF i.checkpoint_summary ? key THEN RETURN i.checkpoint_summary->key->>'fingerprint'=p_fingerprint; END IF;
 IF NOT EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND call_id=p_call AND state='settled' AND NOT slot_held AND NOT cost_overrun AND mode=i.execution_mode AND input_fingerprint=decode(p_fingerprint,'hex') AND operation='embed_document') THEN RAISE EXCEPTION 'CALL_UNSETTLED' USING ERRCODE='B0410'; END IF;
 UPDATE rag.index_builds SET checkpoint_summary=checkpoint_summary||jsonb_build_object(key,jsonb_build_object('fingerprint',p_fingerprint,'call_id',p_call,'chunks',p_count)),completed_batches=completed_batches+1,revision=revision+1 WHERE tenant_id=p_tenant AND index_id=idx;
 RETURN true;
END;$body$;

CREATE FUNCTION security.document_publish(p_tenant uuid,p_job uuid,p_epoch bigint,p_claim bytea,p_counts jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE idx uuid;j rag.jobs%ROWTYPE;i rag.index_builds%ROWTYPE;
BEGIN
 PERFORM security.execution_scope(p_tenant);
 IF p_counts IS NULL OR jsonb_typeof(p_counts)<>'object' OR NOT(p_counts ?& ARRAY['chunks','entities','relations','evidence']) OR p_counts-ARRAY['chunks','entities','relations','evidence']::text[]<>'{}'::jsonb OR EXISTS(SELECT 1 FROM jsonb_each(p_counts) WHERE value::text !~ '^[0-9]{1,4}$') THEN RAISE EXCEPTION 'INDEX_INCOMPLETE' USING ERRCODE='A0422'; END IF;
 idx:=security.document_worker_guard(p_tenant,p_job,p_epoch,p_claim);
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

CREATE FUNCTION security.document_delete(p_session uuid,p_tenant uuid,p_document uuid,p_expected bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;a security.document_access%ROWTYPE;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,true);
 SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 IF a.deleted_at IS NOT NULL THEN RETURN jsonb_build_object('access_state','deleted','cleanup_state','pending','revision',a.acl_revision); END IF;
 IF a.acl_revision IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 UPDATE security.document_access SET deleted_at=clock_timestamp(),acl_revision=acl_revision+1 WHERE tenant_id=p_tenant AND document_id=p_document;
 UPDATE security.document_publications SET active=false,revision=revision+1 WHERE tenant_id=p_tenant AND document_id=p_document;
 UPDATE security.share_grants SET active=false,revoked_at=clock_timestamp(),revision=revision+1 WHERE owner_tenant_id=p_tenant AND document_id=p_document;
 UPDATE security.job_authorizations SET revoked_at=clock_timestamp() WHERE tenant_id=p_tenant AND document_id=p_document;
 UPDATE rag.jobs SET state='interrupted',stage='terminal',ended_at=clock_timestamp(),revision=revision+1,safe_error_code='DOCUMENT_DELETED' WHERE tenant_id=p_tenant AND document_id=p_document AND state IN ('queued','running');
 INSERT INTO rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,execution_mode,state,stage,origin_session_id)
 SELECT p_tenant,gen_random_uuid(),p_document,v.version_id,v.index_id,actor,'internal_cleanup',v.execution_mode,'queued','cleanup',p_session
 FROM rag.index_builds v WHERE tenant_id=p_tenant AND document_id=p_document;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions) VALUES(gen_random_uuid(),'tenant',p_tenant,actor,'document.delete',p_document,'success',jsonb_build_object('revision',a.acl_revision+1));
 RETURN jsonb_build_object('access_state','deleted','cleanup_state','pending','revision',a.acl_revision+1);
END;$body$;

-- Every capability owned by NOLOGIN policy executor; raw LOGIN grants remain unchanged.

ALTER FUNCTION security.document_manage(uuid,uuid,boolean) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_manage(uuid,uuid,boolean) FROM PUBLIC,ai_web,ai_index,ai_meter;

ALTER FUNCTION security.document_register(uuid,uuid,uuid,bytea,uuid,uuid,uuid,uuid,boolean,bigint,uuid,text,uuid[],text,text,bytea,integer,integer,bytea,text,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_register(uuid,uuid,uuid,bytea,uuid,uuid,uuid,uuid,boolean,bigint,uuid,text,uuid[],text,text,bytea,integer,integer,bytea,text,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_register(uuid,uuid,uuid,bytea,uuid,uuid,uuid,uuid,boolean,bigint,uuid,text,uuid[],text,text,bytea,integer,integer,bytea,text,jsonb) TO ai_web;

ALTER FUNCTION security.document_job_control(uuid,uuid,uuid,text,bigint,bytea,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_job_control(uuid,uuid,uuid,text,bigint,bytea,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_job_control(uuid,uuid,uuid,text,bigint,bytea,jsonb) TO ai_web;

ALTER FUNCTION security.document_admin_list(uuid,uuid,text,uuid,integer) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_admin_list(uuid,uuid,text,uuid,integer) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_admin_list(uuid,uuid,text,uuid,integer) TO ai_web;

ALTER FUNCTION security.document_worker_guard(uuid,uuid,bigint,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_worker_guard(uuid,uuid,bigint,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_worker_guard(uuid,uuid,bigint,bytea) TO ai_index;

ALTER FUNCTION security.document_checkpoint(uuid,uuid,bigint,bytea,integer,text,integer,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_checkpoint(uuid,uuid,bigint,bytea,integer,text,integer,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_checkpoint(uuid,uuid,bigint,bytea,integer,text,integer,uuid) TO ai_index;

ALTER FUNCTION security.document_publish(uuid,uuid,bigint,bytea,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_publish(uuid,uuid,bigint,bytea,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_publish(uuid,uuid,bigint,bytea,jsonb) TO ai_index;

ALTER FUNCTION security.document_delete(uuid,uuid,uuid,bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_delete(uuid,uuid,uuid,bigint) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_delete(uuid,uuid,uuid,bigint) TO ai_web;

GRANT EXECUTE ON FUNCTION security.document_manage(uuid,uuid,boolean) TO ai_web;

GRANT SELECT ON rag.index_builds TO ai_policy_executor;

GRANT USAGE ON SCHEMA security TO ai_index;

CREATE POLICY agent_job_control_metadata ON portal.agent_configs FOR SELECT TO ai_policy_executor USING(session_user='ai_index' AND tenant_id::text=current_setting('app.job_tenant_id',true));

CREATE POLICY audit_document_job_publish ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(
 session_user='ai_index' AND scope_kind='tenant' AND action='document.publish' AND tenant_id::text=current_setting('app.job_tenant_id',true)
 AND EXISTS(SELECT 1 FROM rag.jobs j WHERE j.tenant_id=audit_events.tenant_id AND j.job_id::text=current_setting('app.job_id',true)
 AND j.initiator_user_id=audit_events.actor_id AND j.document_id=audit_events.opaque_target_id AND j.state='completed'
 AND j.lease_epoch::text=current_setting('app.job_epoch',true)));

CREATE FUNCTION security.document_upload_preflight(p_session uuid,p_tenant uuid,p_client uuid,p_hash bytea,p_document uuid,p_expected bigint) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;r security.operation_receipts%ROWTYPE;a security.document_access%ROWTYPE;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,true);
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||actor::text||p_client::text,0));
 SELECT * INTO r FROM security.operation_receipts WHERE tenant_id=p_tenant AND initiator_user_id=actor AND operation_kind='upload' AND client_operation_id=p_client;
 IF FOUND THEN
  IF r.request_hash IS DISTINCT FROM p_hash THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
  RETURN true;
 END IF;
 IF p_document IS NOT NULL THEN
  SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document FOR UPDATE;
  IF NOT FOUND OR a.deleted_at IS NOT NULL OR (a.visibility='private' AND a.owner_user_id<>actor AND NOT EXISTS(SELECT 1 FROM security.private_readers WHERE tenant_id=p_tenant AND document_id=p_document AND user_id=actor)) THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
  IF a.acl_revision IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 END IF;
 RETURN false;
END;$body$;
ALTER FUNCTION security.document_upload_preflight(uuid,uuid,uuid,bytea,uuid,bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_upload_preflight(uuid,uuid,uuid,bytea,uuid,bigint) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_upload_preflight(uuid,uuid,uuid,bytea,uuid,bigint) TO ai_web;
