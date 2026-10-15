-- Explicit minimal evidence sharing. Personal trial/case/evaluation policies are unchanged.
CREATE TABLE portal.builder_evidence_shares(
 tenant_id uuid NOT NULL,share_id uuid NOT NULL DEFAULT gen_random_uuid(),requester_id uuid NOT NULL,
 client_request_id uuid NOT NULL,request_hash text NOT NULL,snapshot jsonb NOT NULL,snapshot_hash text NOT NULL,
 status text NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted','withdrawn')),
 revision bigint NOT NULL DEFAULT 1,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),withdrawn_at timestamptz,
 PRIMARY KEY(tenant_id,share_id),UNIQUE(tenant_id,requester_id,client_request_id),
 FOREIGN KEY(tenant_id,requester_id) REFERENCES security.memberships(tenant_id,user_id),
 CHECK(jsonb_typeof(snapshot)='object' AND octet_length(snapshot::text)<=32000),
 CHECK((status='submitted' AND revision=1 AND withdrawn_at IS NULL) OR (status='withdrawn' AND revision=2 AND withdrawn_at IS NOT NULL)));
ALTER TABLE portal.builder_evidence_shares OWNER TO ai_owner;
ALTER TABLE portal.builder_evidence_shares ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_evidence_shares FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.builder_evidence_shares FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.builder_evidence_shares TO ai_policy_executor;
GRANT UPDATE(status,revision,withdrawn_at) ON portal.builder_evidence_shares TO ai_policy_executor;
CREATE POLICY builder_share_access ON portal.builder_evidence_shares TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id)
 AND (requester_id=nullif(current_setting('app.user_id',true),'')::uuid OR EXISTS(
 SELECT 1 FROM security.current_membership(nullif(current_setting('app.session_id',true),'')::uuid,tenant_id) m WHERE m.effective_role='PADMIN')))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND requester_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE INDEX builder_shares_queue ON portal.builder_evidence_shares(tenant_id,created_at DESC,share_id DESC);
CREATE FUNCTION portal.builder_share_sealed() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'SHARE_SEALED' USING ERRCODE='23514';END IF;
 IF (to_jsonb(NEW)-ARRAY['status','revision','withdrawn_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','revision','withdrawn_at'])
 OR OLD.status<>'submitted' OR NEW.status<>'withdrawn' OR NEW.revision<>2 OR NEW.withdrawn_at IS NULL
 THEN RAISE EXCEPTION 'SHARE_SEALED' USING ERRCODE='23514';END IF;
 RETURN NEW;
END;$body$;
ALTER FUNCTION portal.builder_share_sealed() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.builder_share_sealed() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER builder_share_sealed BEFORE UPDATE OR DELETE ON portal.builder_evidence_shares FOR EACH ROW EXECUTE FUNCTION portal.builder_share_sealed();

CREATE FUNCTION security.builder_evidence_share(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;v jsonb;e portal.builder_evaluations%ROWTYPE;s portal.builder_evidence_shares%ROWTYPE;
 a portal.assets%ROWTYPE;h text;snap jsonb;checks jsonb;items jsonb;anchor timestamptz;next_id uuid;is_owner boolean;version jsonb;policy bigint;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('submit','list','detail','withdraw') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR p_mode IS NULL OR p_mode NOT IN ('mock','real') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action IN ('submit','withdraw'));
 IF p_action='list' THEN
 IF p_body-ARRAY['cursor']<>'{}'::jsonb THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_body->>'cursor' IS NOT NULL THEN SELECT created_at INTO anchor FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND share_id=(p_body->>'cursor')::uuid;
 IF anchor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.share_id DESC),'[]') INTO items FROM
 (SELECT share_id,status,revision,requester_id,created_at,snapshot->'asset_binding' AS asset_binding
 FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND (anchor IS NULL OR (created_at,share_id)<(anchor,(p_body->>'cursor')::uuid))
 ORDER BY created_at DESC,share_id DESC LIMIT 21) x;
 IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'share_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
 END IF;
 IF p_action='submit' THEN
 IF ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['client_request_id','consent','evaluation_id','run_id']
 OR p_body->'consent' IS DISTINCT FROM 'true'::jsonb
 OR coalesce(p_body->>'client_request_id','')='' OR coalesce(p_body->>'run_id','')='' OR coalesce(p_body->>'evaluation_id','')=''
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 v:=security.builder_trial_evidence(p_session,p_tenant,(p_body->>'run_id')::uuid);
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 IF v->>'content_status'<>'final' OR v->>'execution_mode' IS DISTINCT FROM p_mode THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 SELECT * INTO e FROM portal.builder_evaluations WHERE tenant_id=p_tenant AND evaluation_id=(p_body->>'evaluation_id')::uuid;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF e.run_id<>(p_body->>'run_id')::uuid OR e.result_hash IS DISTINCT FROM v->>'result_hash'
 THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 SELECT * INTO a FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=(v->'asset_binding'->>'asset_id')::uuid FOR SHARE;
 IF a.latest_revision<>(v->'asset_binding'->>'revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('rule',x->>'rule','passed',x->'passed')),'[]') INTO checks FROM jsonb_array_elements(e.checks) x;
 snap:=jsonb_build_object('contract','approval-evidence-v1','asset_binding',v->'asset_binding','run_id',v->'run_id',
 'execution_mode',v->'execution_mode','purpose',v->'purpose','model_ref',v->'model_ref','policy_revision',v->'config_version',
 'profile_hash',v->'profile_hash','composition_hash',v->'composition_hash','result_hash',v->'result_hash','question_hash',v->'question_hash',
 'sources',v->'sources','evaluation',jsonb_build_object('evaluation_id',e.evaluation_id,'case_id',e.case_id,'case_hash',e.case_hash,'result_hash',e.result_hash,
 'engine',e.engine,'passed',e.passed,'checks',checks,'created_at',e.created_at));
 h:=encode(sha256(convert_to(p_body::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||(p_body->>'client_request_id'),0));
 SELECT * INTO s FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND requester_id=u AND client_request_id=(p_body->>'client_request_id')::uuid;
 IF FOUND THEN
 IF s.request_hash<>h THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 RETURN jsonb_build_object('share_id',s.share_id,'status',s.status,'revision',s.revision,'snapshot_hash',s.snapshot_hash,'replayed',true);END IF;
 IF (SELECT count(*) FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND requester_id=u AND status='submitted')>=20 THEN RAISE EXCEPTION 'QUEUE_LIMIT' USING ERRCODE='D0429';END IF;
 INSERT INTO portal.builder_evidence_shares(tenant_id,requester_id,client_request_id,request_hash,snapshot,snapshot_hash)
 VALUES(p_tenant,u,(p_body->>'client_request_id')::uuid,h,snap,encode(sha256(convert_to(snap::text,'UTF8')),'hex')) RETURNING * INTO s;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result)
 VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.evidence_shared',s.share_id,'ok');
 RETURN jsonb_build_object('share_id',s.share_id,'status',s.status,'revision',s.revision,'snapshot_hash',s.snapshot_hash,'replayed',false);
 END IF;
 IF p_action='withdraw' THEN
 SELECT * INTO s FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND share_id=p_id FOR UPDATE;
 ELSE SELECT * INTO s FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND share_id=p_id;END IF;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 is_owner:=s.requester_id=u;
 IF p_action='withdraw' THEN
 IF NOT is_owner THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';END IF;
 IF ARRAY(SELECT jsonb_object_keys(p_body))<>ARRAY['expected_revision'] OR coalesce(p_body->>'expected_revision','') !~ '^[12]$'
 OR jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF s.status='withdrawn' THEN RETURN jsonb_build_object('share_id',s.share_id,'status',s.status,'revision',s.revision,'replayed',true);END IF;
 IF s.revision<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 UPDATE portal.builder_evidence_shares SET status='withdrawn',revision=2,withdrawn_at=clock_timestamp() WHERE tenant_id=p_tenant AND share_id=p_id;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result)
 VALUES(gen_random_uuid(),'tenant',p_tenant,u,'builder.evidence_withdrawn',p_id,'ok');
 RETURN jsonb_build_object('share_id',p_id,'status','withdrawn','revision',2,'replayed',false);
 END IF;
 IF p_body<>'{}'::jsonb THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF s.status='submitted' THEN
 PERFORM security.rag_sources_guard(p_session,p_tenant,s.snapshot->>'execution_mode',s.snapshot->'sources');
 version:=security.builder_version(p_session,p_tenant,(s.snapshot->'asset_binding'->>'asset_id')::uuid,(s.snapshot->'asset_binding'->>'version_id')::uuid);
 PERFORM security.builder_profile_validate(version->'config',version->'profile');
 SELECT * INTO a FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=(s.snapshot->'asset_binding'->>'asset_id')::uuid;
 SELECT config_version INTO policy FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=version->'config'->>'execution_kind';
 END IF;
 RETURN jsonb_build_object('share_id',s.share_id,'requester_id',s.requester_id,'status',s.status,'revision',s.revision,'created_at',s.created_at,'withdrawn_at',s.withdrawn_at,
 'can_withdraw',is_owner AND s.status='submitted','snapshot',CASE WHEN s.status='submitted' THEN s.snapshot ELSE NULL END,
 'snapshot_hash',CASE WHEN s.status='submitted' THEN s.snapshot_hash ELSE NULL END,
 'current_conditions',CASE WHEN s.status='submitted' THEN jsonb_build_object('latest_version',a.latest_revision=(s.snapshot->'asset_binding'->>'revision')::bigint,
 'same_profile',version->>'profile_hash'=s.snapshot->>'profile_hash','same_mode',p_mode=s.snapshot->>'execution_mode','same_policy',policy=(s.snapshot->>'policy_revision')::bigint) ELSE NULL END);
END;$body$;
ALTER FUNCTION security.builder_evidence_share(uuid,uuid,text,uuid,jsonb,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_evidence_share(uuid,uuid,text,uuid,jsonb,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_evidence_share(uuid,uuid,text,uuid,jsonb,text) TO ai_web;
