-- AGENT_03 immutable server context and owner-only append-only human reviews.
-- Historical migrations and approved manifest snapshots are deliberately untouched.
GRANT SELECT(source_object_key,source_sha256,media_type,byte_length,character_length,parser_revision,source_mapping) ON rag.document_versions TO ai_policy_executor;

CREATE FUNCTION security.meeting_source_allowed(p_tenant uuid,p_document uuid,p_version uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
 SELECT session_user='ai_web' AND p_tenant=NULLIF(current_setting('app.tenant_id',true),'')::uuid
 AND security.can_read_agent(p_tenant) AND EXISTS(
 SELECT 1 FROM security.document_access a JOIN rag.document_versions v USING(tenant_id,document_id)
 WHERE (a.tenant_id,a.document_id,v.version_id)=(p_tenant,p_document,p_version) AND a.deleted_at IS NULL AND NOT v.payload_purged
 AND ((a.user_owned AND a.visibility='private' AND a.owner_user_id=NULLIF(current_setting('app.user_id',true),'')::uuid
 AND v.version_no=(SELECT max(x.version_no) FROM rag.document_versions x WHERE (x.tenant_id,x.document_id)=(v.tenant_id,v.document_id)))
 OR security.document_can_read(p_tenant,p_document,p_version)));
$$;

CREATE FUNCTION security.meeting_source(p_session uuid,p_tenant uuid,p_document uuid,p_version uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF NOT security.meeting_source_allowed(p_tenant,p_document,p_version) THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='D0404';END IF;
 SELECT jsonb_build_object('tenant_id',v.tenant_id,'document_id',v.document_id,'version_id',v.version_id,'version_no',v.version_no,'title',v.title,
 'source_object_key',v.source_object_key,'source_sha256',encode(v.source_sha256,'hex'),'media_type',v.media_type,'byte_length',v.byte_length,
 'character_length',v.character_length,'parser_revision',v.parser_revision,'source_mapping',v.source_mapping)
 INTO data FROM rag.document_versions v WHERE (v.tenant_id,v.document_id,v.version_id)=(p_tenant,p_document,p_version);
 RETURN data;
END;$$;

CREATE FUNCTION security.meeting_document_candidates(p_session uuid,p_tenant uuid,p_cursor uuid,p_limit integer,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE items jsonb;next_id uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 20 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY document_id),'[]') INTO items FROM (
 SELECT v.document_id,v.version_id,v.version_no,v.title,v.character_length,encode(v.source_sha256,'hex') AS source_sha256
 FROM rag.document_versions v WHERE v.tenant_id=p_tenant AND (p_cursor IS NULL OR v.document_id>p_cursor)
 AND security.meeting_source_allowed(v.tenant_id,v.document_id,v.version_id) ORDER BY v.document_id LIMIT p_limit+1) x;
 IF jsonb_array_length(items)>p_limit THEN items:=items-p_limit;next_id:=(items->(p_limit-1)->>'document_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
END;$$;

CREATE TABLE portal.meeting_run_contexts(
 tenant_id uuid NOT NULL,parent_id uuid NOT NULL,owner_id uuid NOT NULL,
 context jsonb NOT NULL CHECK(jsonb_typeof(context)='object' AND octet_length(context::text)<=262144),
 context_digest text NOT NULL CHECK(context_digest ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,parent_id),
 FOREIGN KEY(tenant_id,parent_id) REFERENCES portal.workflow_runs(tenant_id,run_id));
CREATE TABLE portal.meeting_quality_reviews(
 tenant_id uuid NOT NULL,parent_id uuid NOT NULL,owner_id uuid NOT NULL,review_id uuid NOT NULL DEFAULT gen_random_uuid(),
 client_request_id uuid NOT NULL,request_hash text NOT NULL,review_revision bigint NOT NULL CHECK(review_revision>0),
 run_revision bigint NOT NULL,result_digest text NOT NULL CHECK(result_digest ~ '^[0-9a-f]{64}$'),
 body jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,review_id),
 UNIQUE(tenant_id,owner_id,client_request_id),UNIQUE(tenant_id,parent_id,review_revision),
 FOREIGN KEY(tenant_id,parent_id) REFERENCES portal.meeting_run_contexts(tenant_id,parent_id));
ALTER TABLE portal.meeting_run_contexts OWNER TO ai_owner;
ALTER TABLE portal.meeting_quality_reviews OWNER TO ai_owner;
ALTER TABLE portal.meeting_run_contexts ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.meeting_run_contexts FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.meeting_quality_reviews ENABLE ROW LEVEL SECURITY;ALTER TABLE portal.meeting_quality_reviews FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.meeting_run_contexts,portal.meeting_quality_reviews FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.meeting_run_contexts,portal.meeting_quality_reviews TO ai_policy_executor;
CREATE POLICY meeting_context_owner ON portal.meeting_run_contexts TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_agent(tenant_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_agent(tenant_id));
CREATE POLICY meeting_quality_owner ON portal.meeting_quality_reviews TO ai_policy_executor
 USING(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_agent(tenant_id))
 WITH CHECK(tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND security.can_read_agent(tenant_id));
CREATE FUNCTION portal.meeting_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'MEETING_IMMUTABLE' USING ERRCODE='23514';END;$$;
ALTER FUNCTION portal.meeting_immutable() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.meeting_immutable() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER meeting_context_immutable BEFORE UPDATE OR DELETE ON portal.meeting_run_contexts FOR EACH ROW EXECUTE FUNCTION portal.meeting_immutable();
CREATE TRIGGER meeting_quality_immutable BEFORE UPDATE OR DELETE ON portal.meeting_quality_reviews FOR EACH ROW EXECUTE FUNCTION portal.meeting_immutable();

-- Match existing document mutation/provenance order: access, publication, version.
-- Access serializes latest-version inserts and publication replacement, including
-- absent publication rows. Locks last until the protected RPC transaction ends.
CREATE FUNCTION security.meeting_sources_guard(p_tenant uuid,p_documents jsonb,p_admission boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE doc jsonb;document uuid;version uuid;
BEGIN
 FOR doc IN SELECT value FROM jsonb_array_elements(p_documents)
 ORDER BY (value->>'document_id')::uuid,(value->>'version_id')::uuid LOOP
  document:=(doc->>'document_id')::uuid;version:=(doc->>'version_id')::uuid;
  PERFORM document_id FROM security.document_access WHERE tenant_id=p_tenant AND document_id=document FOR SHARE;
  PERFORM version_id FROM security.document_publications WHERE tenant_id=p_tenant AND document_id=document ORDER BY version_id FOR SHARE;
  PERFORM version_id FROM rag.document_versions WHERE tenant_id=p_tenant AND document_id=document AND version_id=version FOR SHARE;
  -- A fresh statement after any wait sees the winning mutation at READ COMMITTED.
  IF NOT security.meeting_source_allowed(p_tenant,document,version)
  OR NOT EXISTS(SELECT 1 FROM rag.document_versions v WHERE (v.tenant_id,v.document_id,v.version_id)=(p_tenant,document,version)
   AND encode(v.source_sha256,'hex')=doc->>'source_sha256' AND v.title=doc->>'title' AND v.source_mapping=doc->'source_mapping'
   AND (NOT p_admission OR v.character_length=char_length(doc->>'text') AND encode(sha256(convert_to(doc->>'text','UTF8')),'hex')=doc->>'source_sha256'))
  THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='D0404';END IF;
 END LOOP;
 RETURN true;
END;$$;
ALTER FUNCTION security.meeting_sources_guard(uuid,jsonb,boolean) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.meeting_sources_guard(uuid,jsonb,boolean) FROM PUBLIC,ai_web,ai_index,ai_meter;

CREATE FUNCTION security.meeting_context_guard(p_session uuid,p_tenant uuid,p_parent uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE saved portal.meeting_run_contexts%ROWTYPE;doc jsonb;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 SELECT * INTO saved FROM portal.meeting_run_contexts WHERE tenant_id=p_tenant AND parent_id=p_parent;
 IF NOT FOUND THEN RETURN NULL;END IF;
 PERFORM security.meeting_sources_guard(p_tenant,saved.context->'documents',false);
 RETURN saved.context;
END;$$;
CREATE FUNCTION security.meeting_context_read(p_session uuid,p_tenant uuid,p_parent uuid,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;
BEGIN
 data:=security.meeting_context_guard(p_session,p_tenant,p_parent);
 IF data IS NOT NULL THEN
  PERFORM security.workflow_version_guard(p_session,p_tenant,r.version_id,r.execution_mode,r.runtime_digest,r.budget_period)
  FROM portal.workflow_runs r WHERE r.tenant_id=p_tenant AND r.run_id=p_parent;
 END IF;RETURN data;
END;$$;

ALTER FUNCTION security.workflow_parent_guard(uuid,uuid,uuid,uuid,boolean) RENAME TO workflow_parent_guard_v048;
CREATE FUNCTION security.workflow_parent_guard(p_session uuid,p_tenant uuid,p_parent uuid,p_token uuid,p_active boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;
BEGIN
 data:=security.workflow_parent_guard_v048(p_session,p_tenant,p_parent,p_token,p_active);
 PERFORM security.meeting_context_guard(p_session,p_tenant,p_parent);RETURN data;
END;$$;

ALTER FUNCTION security.workflow_runtime(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid) RENAME TO workflow_runtime_v048;
CREATE FUNCTION security.workflow_runtime(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text,p_code text,p_token uuid,p_period date,p_trace uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE data jsonb;sealed jsonb;doc jsonb;u uuid;key text;bound text;saved jsonb;clean jsonb;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,p_action<>'read');
 IF p_action='admit' THEN
  SELECT v.use_case_id,(SELECT n->'config'->>'input_key' FROM jsonb_array_elements(v.definition->'nodes') n WHERE n->>'node_type'='input')
  INTO bound,key FROM portal.workflow_versions v WHERE v.tenant_id=p_tenant AND v.version_id=(p_body->>'version_id')::uuid;
  sealed:=p_body->'meeting_context';clean:=p_body-'meeting_context';
  IF bound='AGENT_03' THEN
   IF sealed IS NULL THEN
    sealed:=jsonb_build_object('source',jsonb_build_object('memo',p_body->'inputs'->>key,'meeting_date',NULL,'document_refs','[]'::jsonb),'documents','[]'::jsonb,'compiled',p_body->'inputs'->>key);
   END IF;
   IF jsonb_typeof(sealed) IS DISTINCT FROM 'object' OR sealed-ARRAY['source','documents','compiled']<>'{}'
   OR jsonb_typeof(sealed->'source') IS DISTINCT FROM 'object' OR (sealed->'source')-ARRAY['memo','meeting_date','document_refs']<>'{}'
   OR jsonb_typeof(sealed->'source'->'memo') IS DISTINCT FROM 'string' OR char_length(sealed->'source'->>'memo')>4000
   OR jsonb_typeof(sealed->'documents') IS DISTINCT FROM 'array' OR jsonb_array_length(sealed->'documents')>3
   OR jsonb_typeof(sealed->'source'->'document_refs') IS DISTINCT FROM 'array'
   OR jsonb_array_length(sealed->'source'->'document_refs')<>jsonb_array_length(sealed->'documents')
   OR jsonb_typeof(sealed->'compiled') IS DISTINCT FROM 'string' OR char_length(sealed->>'compiled') NOT BETWEEN 1 AND 4000
   OR sealed->>'compiled' IS DISTINCT FROM p_body->'inputs'->>key
   OR coalesce(sealed->'source'->>'meeting_date','')<>'' AND (sealed->'source'->>'meeting_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' OR (sealed->'source'->>'meeting_date')::date::text<>sealed->'source'->>'meeting_date')
   THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
   IF btrim(sealed->'source'->>'memo')='' AND jsonb_array_length(sealed->'documents')=0 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
   IF (SELECT count(DISTINCT value->>'version_id') FROM jsonb_array_elements(sealed->'documents'))<>jsonb_array_length(sealed->'documents')
   OR (SELECT count(DISTINCT value->>'document_id') FROM jsonb_array_elements(sealed->'documents'))<>jsonb_array_length(sealed->'documents') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
   FOR doc IN SELECT value FROM jsonb_array_elements(sealed->'documents') LOOP
    IF doc->>'source_ref' IS DISTINCT FROM 'document:'||(doc->>'version_id') OR doc->>'source_tenant_id' IS DISTINCT FROM p_tenant::text
    OR jsonb_typeof(doc->'text') IS DISTINCT FROM 'string'
    OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(sealed->'source'->'document_refs') ref WHERE ref->>'document_id'=doc->>'document_id' AND ref->>'version_id'=doc->>'version_id')
    THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='D0404';END IF;
   END LOOP;
   PERFORM security.meeting_sources_guard(p_tenant,sealed->'documents',true);
   PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||':workflow-capacity',0));
   SELECT c.context INTO saved FROM portal.workflow_runs r JOIN portal.meeting_run_contexts c ON (c.tenant_id,c.parent_id)=(r.tenant_id,r.run_id)
   WHERE r.tenant_id=p_tenant AND r.owner_id=u AND r.client_request_id=(p_body->>'client_request_id')::uuid;
   IF FOUND AND saved IS DISTINCT FROM sealed THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  ELSIF sealed IS NOT NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  data:=security.workflow_runtime_v048(p_session,p_tenant,p_action,p_id,clean,p_mode,p_code,p_token,p_period,p_trace);
  IF bound='AGENT_03' AND NOT (data->>'replayed')::boolean THEN
   INSERT INTO portal.meeting_run_contexts(tenant_id,parent_id,owner_id,context,context_digest)
   VALUES(p_tenant,(data->>'run_id')::uuid,u,sealed,encode(sha256(convert_to(sealed::text,'UTF8')),'hex'));
  END IF;RETURN data;
 END IF;
 IF p_action IN ('claim','heartbeat','step','checkpoint','finish') THEN PERFORM security.meeting_context_guard(p_session,p_tenant,p_id);END IF;
 IF p_action='read' THEN
  BEGIN PERFORM security.meeting_context_guard(p_session,p_tenant,p_id);
  EXCEPTION WHEN SQLSTATE 'D0404' THEN
   data:=security.workflow_runtime_v048(p_session,p_tenant,p_action,p_id,p_body,p_mode,p_code,p_token,p_period,p_trace);
   RETURN data||jsonb_build_object('result',NULL,'result_access','blocked');
  END;
 END IF;
 RETURN security.workflow_runtime_v048(p_session,p_tenant,p_action,p_id,p_body,p_mode,p_code,p_token,p_period,p_trace);
END;$$;

CREATE FUNCTION security.meeting_receipt_lookup(p_session uuid,p_tenant uuid,p_client uuid,p_source jsonb,p_mode text,p_code text,p_period date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE u uuid;parent uuid;saved jsonb;data jsonb;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,false);
 SELECT r.run_id,c.context->'source' INTO parent,saved FROM portal.workflow_runs r JOIN portal.meeting_run_contexts c ON (c.tenant_id,c.parent_id)=(r.tenant_id,r.run_id)
 WHERE r.tenant_id=p_tenant AND r.owner_id=u AND r.client_request_id=p_client;
 IF parent IS NULL THEN RETURN NULL;END IF;
 IF saved IS DISTINCT FROM p_source THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 data:=security.workflow_runtime(p_session,p_tenant,'read',parent,'{}',p_mode,p_code,NULL,p_period,gen_random_uuid());
 RETURN data||jsonb_build_object('replayed',true);
END;$$;
CREATE FUNCTION security.meeting_parent_for_child(p_session uuid,p_tenant uuid,p_child uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE parent uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 SELECT s.parent_id INTO parent FROM portal.workflow_steps s JOIN portal.meeting_run_contexts c ON (c.tenant_id,c.parent_id)=(s.tenant_id,s.parent_id)
 WHERE s.tenant_id=p_tenant AND s.child_run_id=p_child AND s.owner_id=NULLIF(current_setting('app.user_id',true),'')::uuid;
 RETURN parent;
END;$$;

CREATE FUNCTION security.meeting_quality_control(p_session uuid,p_tenant uuid,p_action text,p_parent uuid,p_body jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE u uuid;wr portal.workflow_runs%ROWTYPE;view jsonb;digest text;rev bigint;items jsonb;h text;old portal.meeting_quality_reviews%ROWTYPE;fresh portal.meeting_quality_reviews%ROWTYPE;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,p_action='review');
 PERFORM security.meeting_context_read(p_session,p_tenant,p_parent,'mock');
 SELECT * INTO wr FROM portal.workflow_runs WHERE tenant_id=p_tenant AND run_id=p_parent AND owner_id=u FOR SHARE;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM portal.meeting_run_contexts WHERE tenant_id=p_tenant AND parent_id=p_parent) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 view:=security.workflow_run_view(p_session,p_tenant,p_parent);
 IF wr.state<>'completed' OR view->>'result_access'<>'final' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 digest:=encode(sha256(convert_to(wr.result::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||p_parent::text||':meeting-quality',0));
 SELECT coalesce(max(review_revision),0) INTO rev FROM portal.meeting_quality_reviews WHERE tenant_id=p_tenant AND parent_id=p_parent;
 IF p_action='review' THEN
  IF ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['accuracy','client_request_id','comment','deadline','expected_review_revision','expected_run_revision','omission','owner','result_digest']
  OR EXISTS(SELECT 1 FROM unnest(ARRAY['accuracy','omission','owner','deadline']) k WHERE coalesce(p_body->>k,'') NOT IN ('acceptable','needs_review','not_assessed'))
  OR jsonb_typeof(p_body->'comment') IS DISTINCT FROM 'string' OR char_length(p_body->>'comment') NOT BETWEEN 1 AND 500 OR btrim(p_body->>'comment')='' OR p_body->>'comment'<>btrim(p_body->>'comment')
  OR coalesce(p_body->>'expected_review_revision','') !~ '^(0|[1-9][0-9]*)$' OR coalesce(p_body->>'expected_run_revision','') !~ '^[1-9][0-9]*$'
  THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  h:=encode(sha256(convert_to(jsonb_build_object('parent',p_parent,'body',p_body)::text,'UTF8')),'hex');
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||(p_body->>'client_request_id')||':meeting-review-receipt',0));
  SELECT * INTO old FROM portal.meeting_quality_reviews WHERE tenant_id=p_tenant AND owner_id=u AND client_request_id=(p_body->>'client_request_id')::uuid;
  IF FOUND THEN
   IF old.request_hash<>h THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
  ELSE
   IF wr.revision<>(p_body->>'expected_run_revision')::bigint OR rev<>(p_body->>'expected_review_revision')::bigint OR digest IS DISTINCT FROM p_body->>'result_digest' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
   INSERT INTO portal.meeting_quality_reviews(tenant_id,parent_id,owner_id,client_request_id,request_hash,review_revision,run_revision,result_digest,body)
   VALUES(p_tenant,p_parent,u,(p_body->>'client_request_id')::uuid,h,rev+1,wr.revision,digest,p_body) RETURNING * INTO fresh;
   INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result)
   VALUES(gen_random_uuid(),'tenant',p_tenant,u,'meeting.quality_review',p_parent,'ok');rev:=rev+1;
  END IF;
 ELSIF p_action<>'read' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_revision DESC),'[]') INTO items FROM (
 SELECT review_id,review_revision,run_revision,result_digest,body-ARRAY['client_request_id','expected_review_revision','expected_run_revision','result_digest'] AS ratings,created_at
 FROM portal.meeting_quality_reviews WHERE tenant_id=p_tenant AND parent_id=p_parent ORDER BY review_revision DESC LIMIT 20) x;
 RETURN jsonb_build_object('run_id',p_parent,'run_revision',wr.revision,'result_digest',digest,'review_revision',rev,'items',items,'history_limit',20,'replayed',old.review_id IS NOT NULL,'review_id',coalesce(old.review_id,fresh.review_id));
END;$$;

ALTER FUNCTION security.meeting_source_allowed(uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.meeting_source(uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.meeting_document_candidates(uuid,uuid,uuid,integer,text) OWNER TO ai_policy_executor;
ALTER FUNCTION security.meeting_context_guard(uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.meeting_context_read(uuid,uuid,uuid,text) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_parent_guard(uuid,uuid,uuid,uuid,boolean) OWNER TO ai_policy_executor;
ALTER FUNCTION security.workflow_runtime(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.meeting_quality_control(uuid,uuid,text,uuid,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.meeting_source_allowed(uuid,uuid,uuid),security.meeting_source(uuid,uuid,uuid,uuid),security.meeting_document_candidates(uuid,uuid,uuid,integer,text),security.meeting_context_guard(uuid,uuid,uuid),security.meeting_context_read(uuid,uuid,uuid,text),security.meeting_quality_control(uuid,uuid,text,uuid,jsonb),security.workflow_parent_guard_v048(uuid,uuid,uuid,uuid,boolean),security.workflow_runtime_v048(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid),security.workflow_parent_guard(uuid,uuid,uuid,uuid,boolean),security.workflow_runtime(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.meeting_source(uuid,uuid,uuid,uuid),security.meeting_document_candidates(uuid,uuid,uuid,integer,text),security.meeting_context_read(uuid,uuid,uuid,text),security.meeting_quality_control(uuid,uuid,text,uuid,jsonb),security.workflow_runtime(uuid,uuid,text,uuid,jsonb,text,text,uuid,date,uuid) TO ai_web;

ALTER FUNCTION security.meeting_receipt_lookup(uuid,uuid,uuid,jsonb,text,text,date) OWNER TO ai_policy_executor;
ALTER FUNCTION security.meeting_parent_for_child(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.meeting_receipt_lookup(uuid,uuid,uuid,jsonb,text,text,date),security.meeting_parent_for_child(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.meeting_receipt_lookup(uuid,uuid,uuid,jsonb,text,text,date),security.meeting_parent_for_child(uuid,uuid,uuid) TO ai_web;
CREATE POLICY audit_meeting_quality ON ops.audit_events FOR INSERT TO ai_policy_executor
 WITH CHECK(session_user='ai_web' AND scope_kind='tenant' AND action='meeting.quality_review'
 AND tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid AND actor_id=NULLIF(current_setting('app.user_id',true),'')::uuid
 AND EXISTS(SELECT 1 FROM portal.meeting_run_contexts c WHERE c.tenant_id=audit_events.tenant_id AND c.parent_id=audit_events.opaque_target_id AND c.owner_id=audit_events.actor_id));
CREATE FUNCTION security.meeting_context_summary(p_session uuid,p_tenant uuid,p_parent uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$
DECLARE saved jsonb;doc jsonb;items jsonb:='[]';available boolean;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 SELECT context INTO saved FROM portal.meeting_run_contexts WHERE tenant_id=p_tenant AND parent_id=p_parent;
 IF NOT FOUND THEN RETURN NULL;END IF;
 FOR doc IN SELECT value FROM jsonb_array_elements(saved->'documents') LOOP
  available:=security.meeting_source_allowed(p_tenant,(doc->>'document_id')::uuid,(doc->>'version_id')::uuid)
   AND EXISTS(SELECT 1 FROM rag.document_versions v WHERE (v.tenant_id,v.document_id,v.version_id)=(p_tenant,(doc->>'document_id')::uuid,(doc->>'version_id')::uuid) AND encode(v.source_sha256,'hex')=doc->>'source_sha256');
  items:=items||jsonb_build_array(jsonb_build_object('document_id',doc->>'document_id','version_id',doc->>'version_id','source_ref',doc->>'source_ref',
   'source_sha256',doc->>'source_sha256','title',CASE WHEN available THEN doc->>'title' ELSE NULL END,'current_available',available));
 END LOOP;
 RETURN jsonb_build_object('meeting_date',saved->'source'->'meeting_date','memo_character_count',char_length(saved->'source'->>'memo'),'aggregate_character_count',char_length(saved->>'compiled'),'documents',items);
END;$$;
ALTER FUNCTION security.meeting_context_summary(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.meeting_context_summary(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.meeting_context_summary(uuid,uuid,uuid) TO ai_web;
