-- HTTP request identity to accepted document Jobs, without titles or source payloads.
CREATE FUNCTION security.document_request_trace(p_session uuid,p_tenant uuid,p_request uuid,p_document uuid,p_job uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid; jobs jsonb; kind text;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,true);
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
ALTER FUNCTION security.document_request_trace(uuid,uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_request_trace(uuid,uuid,uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_request_trace(uuid,uuid,uuid,uuid,uuid) TO ai_web;
CREATE POLICY audit_document_request_trace ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(
 session_user='ai_web' AND scope_kind='tenant' AND action='document.request.accepted'
 AND actor_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND security.can_manage_current_tenant(tenant_id));
