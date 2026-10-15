-- DP-05 owner-private uploads; old administrative capabilities stay unchanged.
ALTER TABLE security.document_access ADD COLUMN user_owned boolean NOT NULL DEFAULT false;
ALTER TABLE security.document_access ADD CONSTRAINT user_owned_private CHECK(NOT user_owned OR visibility='private');
GRANT SELECT,INSERT(user_owned) ON security.document_access TO ai_policy_executor;
GRANT SELECT(title) ON rag.document_versions TO ai_policy_executor;


CREATE OR REPLACE FUNCTION security.document_control_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE tenant uuid; doc uuid; visibility text;
BEGIN
 IF TG_TABLE_NAME='document_access' THEN
  IF TG_OP='UPDATE' AND (OLD.tenant_id,OLD.document_id,OLD.owner_user_id,OLD.visibility,OLD.created_at,OLD.user_owned)
     IS DISTINCT FROM (NEW.tenant_id,NEW.document_id,NEW.owner_user_id,NEW.visibility,NEW.created_at,NEW.user_owned) THEN
   RAISE EXCEPTION 'DOCUMENT_ACL_IMMUTABLE' USING ERRCODE='23514'; END IF;
  RETURN NEW;
 END IF;
 IF TG_TABLE_NAME='private_readers' THEN
  tenant:=coalesce(NEW.tenant_id,OLD.tenant_id); doc:=coalesce(NEW.document_id,OLD.document_id);
  SELECT a.visibility INTO visibility FROM security.document_access a WHERE (a.tenant_id,a.document_id)=(tenant,doc);
  IF visibility IS DISTINCT FROM 'private' OR EXISTS(SELECT 1 FROM rag.document_versions v WHERE (v.tenant_id,v.document_id)=(tenant,doc)) THEN
   RAISE EXCEPTION 'PRIVATE_READERS_FROZEN' USING ERRCODE='23514'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
 END IF;
 IF TG_TABLE_NAME='share_grants' THEN
  IF TG_OP='UPDATE' AND (OLD.grant_id,OLD.owner_tenant_id,OLD.document_id,OLD.version_id,OLD.recipient_tenant_id,OLD.issued_by,OLD.issued_at) IS DISTINCT FROM (NEW.grant_id,NEW.owner_tenant_id,NEW.document_id,NEW.version_id,NEW.recipient_tenant_id,NEW.issued_by,NEW.issued_at) THEN RAISE EXCEPTION 'SHARE_IDENTITY_IMMUTABLE' USING ERRCODE='23514'; END IF;
  IF NOT EXISTS(SELECT 1 FROM security.document_access a JOIN security.document_publications p
    ON (p.tenant_id,p.document_id)=(a.tenant_id,a.document_id)
    WHERE (a.tenant_id,a.document_id,p.version_id)=(NEW.owner_tenant_id,NEW.document_id,NEW.version_id)
     AND a.visibility='org' AND (NOT NEW.active OR (a.deleted_at IS NULL AND p.active))) THEN
   RAISE EXCEPTION 'SHARE_TARGET_UNAVAILABLE' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='document_publications' THEN
  IF TG_OP='UPDATE' AND (OLD.tenant_id,OLD.document_id,OLD.version_id) IS DISTINCT FROM (NEW.tenant_id,NEW.document_id,NEW.version_id) THEN RAISE EXCEPTION 'PUBLICATION_IDENTITY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='document_publications' AND NEW.active THEN
  IF NOT EXISTS(SELECT 1 FROM rag.index_builds i JOIN rag.document_versions v
    ON (v.tenant_id,v.document_id,v.version_id)=(i.tenant_id,i.document_id,i.version_id)
    WHERE (i.tenant_id,i.document_id,i.version_id,i.index_id)=(NEW.tenant_id,NEW.document_id,NEW.version_id,NEW.published_index_id)
     AND i.state='published' AND NOT i.payload_purged AND NOT v.payload_purged) THEN
   RAISE EXCEPTION 'PUBLICATION_TARGET_UNAVAILABLE' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END;$body$;

CREATE OR REPLACE FUNCTION security.user_document_authorize(p_session uuid,p_tenant uuid,p_lock boolean) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 RETURN security.run_authorize(p_session,p_tenant,p_lock);
END;$body$;

ALTER FUNCTION security.user_document_authorize(uuid,uuid,boolean) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_authorize(uuid,uuid,boolean) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_authorize(uuid,uuid,boolean) TO ai_web;

CREATE OR REPLACE FUNCTION security.user_document_upload_preflight(p_session uuid,p_tenant uuid,p_client uuid,p_hash bytea,p_document uuid,p_expected bigint) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;r security.operation_receipts%ROWTYPE;a security.document_access%ROWTYPE;
BEGIN
 actor:=security.user_document_authorize(p_session,p_tenant,true);
 IF p_document IS NOT NULL OR p_expected IS NOT NULL OR p_client IS NULL OR p_hash IS NULL OR octet_length(p_hash)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||actor::text||p_client::text,0));
 SELECT * INTO r FROM security.operation_receipts WHERE tenant_id=p_tenant AND initiator_user_id=actor AND operation_kind='upload' AND client_operation_id=p_client;
 IF FOUND THEN
  IF r.request_hash IS DISTINCT FROM p_hash THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
  IF NOT EXISTS(SELECT 1 FROM security.document_access WHERE tenant_id=p_tenant AND document_id=r.document_id AND user_owned AND owner_user_id=actor AND deleted_at IS NULL) THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
  RETURN true;
 END IF;
 IF p_document IS NOT NULL THEN
  SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document FOR UPDATE;
  IF NOT FOUND OR a.deleted_at IS NOT NULL OR (a.visibility='private' AND a.owner_user_id<>actor AND NOT EXISTS(SELECT 1 FROM security.private_readers WHERE tenant_id=p_tenant AND document_id=p_document AND user_id=actor)) THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
  IF a.acl_revision IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 END IF;
 RETURN false;
END;$body$;

ALTER FUNCTION security.user_document_upload_preflight(uuid,uuid,uuid,bytea,uuid,bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_upload_preflight(uuid,uuid,uuid,bytea,uuid,bigint) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_upload_preflight(uuid,uuid,uuid,bytea,uuid,bigint) TO ai_web;

CREATE OR REPLACE FUNCTION security.user_document_register(p_session uuid,p_tenant uuid,p_client uuid,p_hash bytea,p_doc uuid,p_version uuid,p_index uuid,p_job uuid,p_existing boolean,p_expected bigint,p_owner uuid,p_visibility text,p_readers uuid[],p_title text,p_media text,p_sha bytea,p_bytes integer,p_chars integer,p_source_fp bytea,p_mode text,p_mapping jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid; receipt security.operation_receipts%ROWTYPE;access security.document_access%ROWTYPE;v_no integer;
BEGIN
 actor:=security.user_document_authorize(p_session,p_tenant,true);
 IF p_existing IS DISTINCT FROM false OR p_expected IS NOT NULL OR p_owner IS DISTINCT FROM actor OR p_visibility IS DISTINCT FROM 'private' OR p_readers IS NULL OR cardinality(p_readers)<>0 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_hash IS NULL OR octet_length(p_hash)<>32 OR p_source_fp IS NULL OR octet_length(p_source_fp)<>32 OR p_client IS NULL
 OR p_visibility IS NULL OR p_visibility NOT IN ('org','private') OR p_mode IS NULL OR p_mode NOT IN ('mock','real')
 OR p_existing IS NULL OR p_readers IS NULL OR cardinality(p_readers)>20 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||actor::text||p_client::text,0));
 SELECT * INTO receipt FROM security.operation_receipts WHERE tenant_id=p_tenant AND initiator_user_id=actor AND operation_kind='upload' AND client_operation_id=p_client;
 IF FOUND THEN
  IF receipt.request_hash IS DISTINCT FROM p_hash THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
  IF NOT EXISTS(SELECT 1 FROM security.document_access WHERE tenant_id=p_tenant AND document_id=receipt.document_id AND user_owned AND owner_user_id=actor AND deleted_at IS NULL) THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
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
  INSERT INTO security.document_access(tenant_id,document_id,owner_user_id,visibility,user_owned) VALUES(p_tenant,p_doc,actor,'private',true);
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

ALTER FUNCTION security.user_document_register(uuid,uuid,uuid,bytea,uuid,uuid,uuid,uuid,boolean,bigint,uuid,text,uuid[],text,text,bytea,integer,integer,bytea,text,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_register(uuid,uuid,uuid,bytea,uuid,uuid,uuid,uuid,boolean,bigint,uuid,text,uuid[],text,text,bytea,integer,integer,bytea,text,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_register(uuid,uuid,uuid,bytea,uuid,uuid,uuid,uuid,boolean,bigint,uuid,text,uuid[],text,text,bytea,integer,integer,bytea,text,jsonb) TO ai_web;

CREATE OR REPLACE FUNCTION security.user_document_admission_window(p_session uuid,p_tenant uuid,p_digest bytea)
RETURNS TABLE(allowed boolean,retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_start timestamptz;v_now timestamptz;v_count integer;
BEGIN
 PERFORM security.user_document_authorize(p_session,p_tenant,true);
 IF p_digest IS NULL OR octet_length(p_digest)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 INSERT INTO security.login_windows VALUES('document_admission','principal',p_digest,clock_timestamp(),0) ON CONFLICT DO NOTHING;
 SELECT window_started_at,count INTO v_start,v_count FROM security.login_windows
 WHERE purpose='document_admission' AND key_kind='principal' AND key_digest=p_digest FOR UPDATE;
 PERFORM security.user_document_authorize(p_session,p_tenant,true);v_now:=clock_timestamp();
 IF v_now>=v_start+interval '1 minute' THEN
  v_start:=v_now;v_count:=0;
  UPDATE security.login_windows SET window_started_at=v_start,count=0 WHERE purpose='document_admission' AND key_kind='principal' AND key_digest=p_digest;
 END IF;
 IF v_count>=10 THEN RETURN QUERY SELECT false,GREATEST(1,ceil(extract(epoch FROM v_start+interval '1 minute'-v_now))::integer);RETURN; END IF;
 UPDATE security.login_windows SET count=count+1 WHERE purpose='document_admission' AND key_kind='principal' AND key_digest=p_digest;
 RETURN QUERY SELECT true,0;
END; $body$;

ALTER FUNCTION security.user_document_admission_window(uuid,uuid,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_admission_window(uuid,uuid,bytea) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_admission_window(uuid,uuid,bytea) TO ai_web;

CREATE OR REPLACE FUNCTION security.user_document_delete(p_session uuid,p_tenant uuid,p_document uuid,p_expected bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;a security.document_access%ROWTYPE;
BEGIN
 actor:=security.user_document_authorize(p_session,p_tenant,true);
 SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document AND user_owned AND owner_user_id=actor FOR UPDATE;
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

ALTER FUNCTION security.user_document_delete(uuid,uuid,uuid,bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_delete(uuid,uuid,uuid,bigint) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_delete(uuid,uuid,uuid,bigint) TO ai_web;

CREATE OR REPLACE FUNCTION security.user_document_request_trace(p_session uuid,p_tenant uuid,p_request uuid,p_document uuid,p_job uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid; jobs jsonb; kind text;
BEGIN
 actor:=security.user_document_authorize(p_session,p_tenant,true);
 IF NOT EXISTS(SELECT 1 FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document AND user_owned AND owner_user_id=actor) THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 IF session_user<>'ai_web' OR p_request IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 kind:=CASE WHEN p_job IS NULL THEN 'internal_cleanup' ELSE 'internal_index' END;
 SELECT jsonb_agg(j.job_id ORDER BY j.job_id) INTO jobs FROM rag.jobs j
 WHERE j.tenant_id=p_tenant AND j.document_id=p_document AND j.initiator_user_id=actor
 AND j.job_kind=kind AND (p_job IS NULL OR j.job_id=p_job);
 IF jobs IS NULL THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,actor,'document.request.accepted',p_document,'success',jsonb_build_object('job_ids',jobs));
 RETURN true;
END;$body$;

ALTER FUNCTION security.user_document_request_trace(uuid,uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_request_trace(uuid,uuid,uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_request_trace(uuid,uuid,uuid,uuid,uuid) TO ai_web;

CREATE OR REPLACE FUNCTION security.user_document_list(p_session uuid,p_tenant uuid,p_kind text,p_cursor uuid,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE result jsonb; actor uuid;
BEGIN
 actor:=security.user_document_authorize(p_session,p_tenant,false);
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 OR p_kind NOT IN ('documents','jobs') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF p_kind='documents' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT a.document_id,v.version_id,i.index_id,v.title,a.visibility,a.acl_revision AS revision,
 CASE WHEN a.deleted_at IS NULL THEN 'active' ELSE 'deleted' END AS access_state,
 CASE WHEN i.state='published' THEN 'completed' ELSE coalesce(j.state,'not_started') END AS processing_state,
 CASE WHEN p.active THEN 'published' ELSE 'unpublished' END AS publication_state,
 CASE WHEN a.deleted_at IS NULL THEN 'not_required' WHEN EXISTS(SELECT 1 FROM rag.jobs cj WHERE cj.tenant_id=a.tenant_id AND cj.document_id=a.document_id AND cj.job_kind='internal_cleanup' AND cj.state='completed') THEN 'completed' ELSE 'pending' END AS cleanup_state,
 coalesce(security.document_can_read(a.tenant_id,a.document_id,v.version_id,i.index_id),false) AS can_read_content
 FROM security.document_access a LEFT JOIN LATERAL(SELECT version_id,version_no,title FROM rag.document_versions WHERE tenant_id=a.tenant_id AND document_id=a.document_id ORDER BY version_no DESC LIMIT 1) v ON true
 LEFT JOIN LATERAL(SELECT index_id,state FROM rag.index_builds WHERE tenant_id=a.tenant_id AND document_id=a.document_id AND version_id=v.version_id ORDER BY created_at DESC LIMIT 1) i ON true
 LEFT JOIN LATERAL(SELECT state FROM rag.jobs WHERE tenant_id=a.tenant_id AND index_id=i.index_id AND job_kind='internal_index' ORDER BY created_at DESC LIMIT 1) j ON true
 LEFT JOIN security.document_publications p ON (p.tenant_id,p.document_id,p.version_id)=(a.tenant_id,a.document_id,v.version_id)
 WHERE a.tenant_id=p_tenant AND a.user_owned AND a.owner_user_id=actor AND (p_cursor IS NULL OR a.document_id>p_cursor) ORDER BY a.document_id LIMIT p_limit) x;
 ELSE
  SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT job_id,document_id,version_id,index_id,job_kind,execution_mode,state,stage,revision,safe_error_code,created_at,ended_at FROM rag.jobs WHERE tenant_id=p_tenant AND EXISTS(SELECT 1 FROM security.document_access a WHERE a.tenant_id=rag.jobs.tenant_id AND a.document_id=rag.jobs.document_id AND a.user_owned AND a.owner_user_id=actor) AND (p_cursor IS NULL OR job_id>p_cursor) ORDER BY job_id LIMIT p_limit) x;
 END IF;
 RETURN jsonb_build_object('items',result,'next_cursor',CASE WHEN jsonb_array_length(result)=p_limit THEN result->(p_limit-1)->>CASE WHEN p_kind='documents' THEN 'document_id' ELSE 'job_id' END ELSE NULL END);
END;$body$;

ALTER FUNCTION security.user_document_list(uuid,uuid,text,uuid,integer) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_list(uuid,uuid,text,uuid,integer) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_list(uuid,uuid,text,uuid,integer) TO ai_web;

CREATE OR REPLACE FUNCTION security.user_document_job_view(p_session uuid,p_tenant uuid,p_job uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid; j rag.jobs%ROWTYPE;
BEGIN
 actor:=security.user_document_authorize(p_session,p_tenant,false);
 SELECT * INTO j FROM rag.jobs WHERE tenant_id=p_tenant AND job_id=p_job AND EXISTS(SELECT 1 FROM security.document_access a WHERE a.tenant_id=p_tenant AND a.document_id=rag.jobs.document_id AND a.user_owned AND a.owner_user_id=actor);
 IF NOT FOUND THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 RETURN jsonb_build_object('job_id',j.job_id,'document_id',j.document_id,'version_id',j.version_id,'index_id',j.index_id,'job_kind',j.job_kind,'execution_mode',j.execution_mode,'state',j.state,'stage',j.stage,'revision',j.revision,'safe_error_code',j.safe_error_code,'created_at',j.created_at,'ended_at',j.ended_at,'retry_allowed',false,'safe_reason',CASE WHEN j.state='needs_review' THEN 'INDEX_NEEDS_REVIEW' ELSE j.safe_error_code END,'publication_state',CASE WHEN EXISTS(SELECT 1 FROM security.document_publications p WHERE p.tenant_id=j.tenant_id AND p.document_id=j.document_id AND p.version_id=j.version_id AND p.active) THEN 'published' ELSE 'unpublished' END,'cleanup_state',CASE WHEN j.job_kind='internal_cleanup' AND j.state='completed' THEN 'completed' WHEN j.job_kind='internal_cleanup' THEN 'pending' ELSE 'not_required' END);
END;$body$;

ALTER FUNCTION security.user_document_job_view(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.user_document_job_view(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.user_document_job_view(uuid,uuid,uuid) TO ai_web;

CREATE POLICY audit_user_document ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(
 session_user='ai_web' AND scope_kind='tenant' AND action IN ('document.upload','document.delete','document.request.accepted')
 AND actor_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND EXISTS(SELECT 1 FROM security.document_access d WHERE d.tenant_id=audit_events.tenant_id AND d.document_id=audit_events.opaque_target_id AND d.user_owned AND d.owner_user_id=audit_events.actor_id));

CREATE OR REPLACE FUNCTION security.document_background_control(p_actor uuid,p_tenant uuid,p_job uuid,p_action text,p_epoch bigint DEFAULT NULL,p_claim bytea DEFAULT NULL,p_data jsonb DEFAULT '{}') RETURNS jsonb
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
 AND ((a.user_owned AND a.visibility='private' AND a.owner_user_id=p_actor) OR m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id
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

CREATE OR REPLACE FUNCTION security.document_cleanup_background(p_actor uuid,p_tenant uuid,p_document uuid,p_job uuid,p_action text,p_mode text,p_epoch bigint DEFAULT NULL,p_claim bytea DEFAULT NULL) RETURNS jsonb
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
 IF p_action<>'release' AND NOT EXISTS(SELECT 1 FROM security.accounts u JOIN security.tenants t ON t.tenant_id=p_tenant JOIN security.memberships m ON m.tenant_id=t.tenant_id AND m.user_id=u.user_id WHERE u.user_id=p_actor AND u.active AND t.active AND m.active AND ((a.user_owned AND a.visibility='private' AND a.owner_user_id=p_actor) OR m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id WHERE pa.user_id=p_actor AND pa.active AND pa.is_padmin AND mt.tenant_id=p_tenant AND mt.active))) THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
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
   AND ((d.user_owned AND d.visibility='private' AND d.owner_user_id=u.user_id) OR m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id
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
 AND (EXISTS(SELECT 1 FROM security.document_access ud WHERE ud.tenant_id=j.tenant_id AND ud.document_id=j.document_id AND ud.user_owned AND ud.visibility='private' AND ud.owner_user_id=j.initiator_user_id) OR m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access p JOIN security.managed_tenants mt ON mt.user_id=p.user_id WHERE p.user_id=a.user_id AND p.active AND p.is_padmin AND mt.tenant_id=j.tenant_id AND mt.active))
 AND ((j.job_kind='internal_index' AND EXISTS(SELECT 1 FROM security.document_access d WHERE d.tenant_id=j.tenant_id AND d.document_id=j.document_id AND d.deleted_at IS NULL))
 OR (j.job_kind='internal_cleanup' AND EXISTS(SELECT 1 FROM security.document_access d WHERE d.tenant_id=j.tenant_id AND d.document_id=j.document_id AND d.deleted_at IS NOT NULL))));
 SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT tenant_id,job_id,document_id,origin_session_id,initiator_user_id,job_kind FROM rag.jobs WHERE execution_mode=p_mode AND origin_session_id IS NOT NULL AND (state='queued' OR (state='running' AND lease_expires_at<=clock_timestamp())) ORDER BY created_at,job_id LIMIT 100) x;
 RETURN result;
END;$body$;
