-- Admission and receipt lookup commit before parsing untrusted content.
CREATE FUNCTION security.document_upload_lookup(p_session uuid,p_tenant uuid,p_client uuid,p_hash bytea,p_document uuid,p_expected bigint,p_personal boolean,p_window bytea,p_request uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;replayed boolean;r security.operation_receipts%ROWTYPE;a record;
BEGIN
 IF p_personal IS NULL OR p_client IS NULL OR p_hash IS NULL OR octet_length(p_hash)<>32 OR p_window IS NULL OR octet_length(p_window)<>32 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_personal THEN
  actor:=security.user_document_authorize(p_session,p_tenant,true);
  replayed:=security.user_document_upload_preflight(p_session,p_tenant,p_client,p_hash,p_document,p_expected);
 ELSE
  actor:=security.document_manage(p_session,p_tenant,true);
  replayed:=security.document_upload_preflight(p_session,p_tenant,p_client,p_hash,p_document,p_expected);
 END IF;
 IF replayed THEN
  SELECT * INTO STRICT r FROM security.operation_receipts WHERE tenant_id=p_tenant AND initiator_user_id=actor AND operation_kind='upload' AND client_operation_id=p_client;
  IF p_request IS NOT NULL THEN
   IF p_personal THEN PERFORM security.user_document_request_trace(p_session,p_tenant,p_request,r.document_id,r.job_id);
   ELSE PERFORM security.document_request_trace(p_session,p_tenant,p_request,r.document_id,r.job_id);END IF;
  END IF;
  RETURN jsonb_build_object('document_id',r.document_id,'version_id',r.version_id,'index_id',r.index_id,'job_id',r.job_id,'replayed',true);
 END IF;
 IF p_personal THEN SELECT * INTO a FROM security.user_document_admission_window(p_session,p_tenant,p_window);
 ELSE SELECT * INTO a FROM security.document_admission_window(p_session,p_tenant,p_window);END IF;
 RETURN jsonb_build_object('new_upload',true,'allowed',a.allowed,'retry_after',a.retry_after);
END;$body$;
ALTER FUNCTION security.document_upload_lookup(uuid,uuid,uuid,bytea,uuid,bigint,boolean,bytea,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_upload_lookup(uuid,uuid,uuid,bytea,uuid,bigint,boolean,bytea,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_upload_lookup(uuid,uuid,uuid,bytea,uuid,bigint,boolean,bytea,uuid) TO ai_web;
