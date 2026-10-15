-- Separate approval/publication contracts; personal evidence stays owner-only.
CREATE TABLE portal.asset_deployments(
 tenant_id uuid NOT NULL,request_id uuid NOT NULL DEFAULT gen_random_uuid(),requester_id uuid NOT NULL,client_request_id uuid NOT NULL,
 share_id uuid NOT NULL,asset_id uuid NOT NULL,version_id uuid NOT NULL,expected_publication_revision bigint NOT NULL CHECK(expected_publication_revision>=0),
 request_hash text NOT NULL,body jsonb NOT NULL,snapshot jsonb NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),revision bigint NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),decided_by uuid,decided_at timestamptz,decision jsonb,
 publication_revision bigint,PRIMARY KEY(tenant_id,request_id),UNIQUE(tenant_id,requester_id,client_request_id),
 FOREIGN KEY(tenant_id,share_id) REFERENCES portal.builder_evidence_shares(tenant_id,share_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.asset_versions(tenant_id,version_id),
 CHECK((status='pending' AND revision=1 AND decided_by IS NULL AND decided_at IS NULL AND decision IS NULL AND publication_revision IS NULL)
 OR (status IN ('approved','rejected') AND revision=2 AND decided_by IS NOT NULL AND decided_by<>requester_id AND decided_at IS NOT NULL AND decision IS NOT NULL
 AND ((status='approved' AND publication_revision=expected_publication_revision+1) OR (status='rejected' AND publication_revision IS NULL)))));
CREATE TABLE portal.asset_publications(
 tenant_id uuid NOT NULL,asset_id uuid NOT NULL,version_id uuid NOT NULL,publication_revision bigint NOT NULL CHECK(publication_revision>0),
 request_id uuid NOT NULL,config jsonb NOT NULL,profile jsonb NOT NULL,profile_hash text NOT NULL,config_hash text NOT NULL,asset_revision bigint NOT NULL,
 audience text NOT NULL CHECK(audience IN ('all','restricted')),member_ids uuid[] NOT NULL,execution_mode text NOT NULL CHECK(execution_mode IN ('mock','real')),
 status text NOT NULL DEFAULT 'published' CHECK(status IN ('published','retired')),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,asset_id),FOREIGN KEY(tenant_id,request_id) REFERENCES portal.asset_deployments(tenant_id,request_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.asset_versions(tenant_id,version_id),
 CHECK(cardinality(member_ids)<=200 AND array_position(member_ids,NULL) IS NULL AND (audience<>'all' OR cardinality(member_ids)=0)));
ALTER TABLE portal.asset_deployments OWNER TO ai_owner;
ALTER TABLE portal.asset_publications OWNER TO ai_owner;
ALTER TABLE portal.asset_deployments ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.asset_deployments FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.asset_publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.asset_publications FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.asset_deployments,portal.asset_publications FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.asset_deployments TO ai_policy_executor;
GRANT UPDATE(status,revision,decided_by,decided_at,decision,publication_revision) ON portal.asset_deployments TO ai_policy_executor;
GRANT SELECT,INSERT,UPDATE ON portal.asset_publications TO ai_policy_executor;
CREATE POLICY asset_deployment_manage ON portal.asset_deployments TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id)
 AND (requester_id=nullif(current_setting('app.user_id',true),'')::uuid OR EXISTS(SELECT 1 FROM security.current_membership(nullif(current_setting('app.session_id',true),'')::uuid,tenant_id) m WHERE m.effective_role='PADMIN')))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY asset_publication_read ON portal.asset_publications FOR SELECT TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND security.can_read_own_conversation(tenant_id,nullif(current_setting('app.user_id',true),'')::uuid)
 AND (security.can_manage_current_tenant(tenant_id) OR audience='all' OR nullif(current_setting('app.user_id',true),'')::uuid=ANY(member_ids)));
CREATE POLICY asset_publication_write ON portal.asset_publications FOR ALL TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE INDEX asset_deployment_queue ON portal.asset_deployments(tenant_id,created_at DESC,request_id DESC);
CREATE FUNCTION portal.asset_deployment_sealed() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'DEPLOYMENT_SEALED' USING ERRCODE='23514';END IF;
 IF (to_jsonb(NEW)-ARRAY['status','revision','decided_by','decided_at','decision','publication_revision']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','revision','decided_by','decided_at','decision','publication_revision'])
 OR OLD.status<>'pending' OR NEW.status='pending' THEN RAISE EXCEPTION 'DEPLOYMENT_SEALED' USING ERRCODE='23514';END IF;RETURN NEW;
END;$body$;
ALTER FUNCTION portal.asset_deployment_sealed() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.asset_deployment_sealed() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER asset_deployment_sealed BEFORE UPDATE OR DELETE ON portal.asset_deployments FOR EACH ROW EXECUTE FUNCTION portal.asset_deployment_sealed();
CREATE FUNCTION portal.asset_publication_sealed() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'PUBLICATION_SEALED' USING ERRCODE='23514';END IF;
 IF TG_OP='UPDATE' AND NEW.status='retired' AND OLD.status='published' AND NEW.publication_revision=OLD.publication_revision+1
 AND (to_jsonb(NEW)-ARRAY['status','publication_revision','updated_at'])=(to_jsonb(OLD)-ARRAY['status','publication_revision','updated_at']) THEN RETURN NEW;END IF;
 IF NEW.status<>'published' OR (TG_OP='UPDATE' AND (NEW.request_id=OLD.request_id OR NEW.publication_revision<>OLD.publication_revision+1))
 OR NOT EXISTS(SELECT 1 FROM portal.asset_deployments d WHERE d.tenant_id=NEW.tenant_id AND d.request_id=NEW.request_id AND d.asset_id=NEW.asset_id AND d.version_id=NEW.version_id AND d.status='approved' AND d.publication_revision=NEW.publication_revision)
 OR NOT EXISTS(SELECT 1 FROM portal.asset_versions v JOIN portal.builder_profiles p USING(tenant_id,version_id) WHERE v.tenant_id=NEW.tenant_id AND v.version_id=NEW.version_id AND v.asset_id=NEW.asset_id AND v.config=NEW.config AND v.config_hash=NEW.config_hash AND v.revision=NEW.asset_revision AND p.profile=NEW.profile AND p.profile_hash=NEW.profile_hash)
 THEN RAISE EXCEPTION 'PUBLICATION_SEALED' USING ERRCODE='23514';END IF;RETURN NEW;
END;$body$;
ALTER FUNCTION portal.asset_publication_sealed() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.asset_publication_sealed() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER asset_publication_sealed BEFORE INSERT OR UPDATE OR DELETE ON portal.asset_publications FOR EACH ROW EXECUTE FUNCTION portal.asset_publication_sealed();

CREATE FUNCTION security.asset_deployment(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;role text;d portal.asset_deployments%ROWTYPE;pub portal.asset_publications%ROWTYPE;proof jsonb;v jsonb;h text;ids uuid[];latest bigint;anchor timestamptz;items jsonb;next_id uuid;v_status text;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('submit','list','detail','decide','publication','retire') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR coalesce(p_mode,'') NOT IN ('mock','real') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action IN ('submit','decide','retire'));
 SELECT effective_role INTO role FROM security.current_membership(p_session,p_tenant);
 IF p_action IN ('publication','retire') THEN
 IF p_id IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF NOT EXISTS(SELECT 1 FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=p_id) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF p_action='retire' THEN
 IF role<>'PADMIN' THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':publication:'||p_id::text,0));
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=p_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF ARRAY(SELECT jsonb_object_keys(p_body))<>ARRAY['expected_revision'] OR jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number'
 OR coalesce(p_body->>'expected_revision','') !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF pub.status='retired' AND (p_body->>'expected_revision')::bigint IN (pub.publication_revision-1,pub.publication_revision) THEN
 RETURN jsonb_build_object('asset_id',p_id,'status','retired','publication_revision',pub.publication_revision,'replayed',true);END IF;
 IF pub.publication_revision<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 UPDATE portal.asset_publications SET status='retired',publication_revision=publication_revision+1,updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND asset_id=p_id;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(gen_random_uuid(),'tenant',p_tenant,u,'asset.retired',p_id,'ok');
 RETURN jsonb_build_object('asset_id',p_id,'status','retired','publication_revision',pub.publication_revision+1,'replayed',false);
 END IF;
 IF p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=p_id;
 RETURN jsonb_build_object('asset_id',p_id,'status',coalesce(pub.status,'unpublished'),'publication_revision',coalesce(pub.publication_revision,0),'version_id',pub.version_id);
 END IF;
 IF p_action='list' THEN
 IF p_body-ARRAY['cursor']<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_body->>'cursor' IS NOT NULL THEN SELECT created_at INTO anchor FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=(p_body->>'cursor')::uuid;
 IF anchor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.request_id DESC),'[]') INTO items FROM
 (SELECT request_id,status,revision,requester_id,asset_id,version_id,created_at,snapshot->'asset_binding'->'revision' AS asset_revision
 FROM portal.asset_deployments WHERE tenant_id=p_tenant AND (anchor IS NULL OR (created_at,request_id)<(anchor,(p_body->>'cursor')::uuid)) ORDER BY created_at DESC,request_id DESC LIMIT 21) x;
 IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'request_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
 END IF;
 IF p_action='submit' THEN
 IF ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['audience','client_request_id','expected_publication_revision','member_ids','reason','share_id']
 OR coalesce(p_body->>'client_request_id','')='' OR coalesce(p_body->>'share_id','')=''
 OR jsonb_typeof(p_body->'expected_publication_revision') IS DISTINCT FROM 'number' OR coalesce(p_body->>'expected_publication_revision','') !~ '^(0|[1-9][0-9]*)$'
 OR coalesce(p_body->>'audience','') NOT IN ('all','restricted') OR jsonb_typeof(p_body->'member_ids') IS DISTINCT FROM 'array'
 OR jsonb_typeof(p_body->'reason') IS DISTINCT FROM 'string' OR btrim(p_body->>'reason')='' OR char_length(p_body->>'reason')>500
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF jsonb_array_length(p_body->'member_ids')>200 OR (p_body->>'audience'='all' AND p_body->'member_ids'<>'[]')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_body->'member_ids') x WHERE jsonb_typeof(x)<>'string') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT coalesce(array_agg(value::uuid),'{}') INTO ids FROM jsonb_array_elements_text(p_body->'member_ids');
 IF (SELECT count(DISTINCT x) FROM unnest(ids) x)<>cardinality(ids) OR EXISTS(SELECT 1 FROM unnest(ids) id WHERE NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts a ON a.user_id=m.user_id WHERE m.tenant_id=p_tenant AND m.user_id=id AND m.active AND a.active)) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 PERFORM share_id FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND share_id=(p_body->>'share_id')::uuid FOR SHARE;
 proof:=security.builder_evidence_share(p_session,p_tenant,'detail',(p_body->>'share_id')::uuid,'{}',p_mode);
 IF proof->>'requester_id' IS DISTINCT FROM u::text THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF proof->>'status'<>'submitted' OR proof->'current_conditions' IS NULL OR EXISTS(SELECT 1 FROM jsonb_each(proof->'current_conditions') x WHERE x.value<>'true')
 THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 h:=encode(sha256(convert_to(p_body::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':deployment-queue:'||u::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||u::text||(p_body->>'client_request_id'),0));
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND requester_id=u AND client_request_id=(p_body->>'client_request_id')::uuid;
 IF FOUND THEN
 IF d.request_hash<>h THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 RETURN jsonb_build_object('request_id',d.request_id,'status',d.status,'revision',d.revision,'publication_revision',d.publication_revision,'replayed',true);END IF;
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=(proof->'snapshot'->'asset_binding'->>'asset_id')::uuid;
 IF coalesce(pub.publication_revision,0)<>(p_body->>'expected_publication_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 IF (SELECT count(*) FROM portal.asset_deployments WHERE tenant_id=p_tenant AND requester_id=u AND status='pending')>=20 THEN RAISE EXCEPTION 'QUEUE_LIMIT' USING ERRCODE='D0429';END IF;
 INSERT INTO portal.asset_deployments(tenant_id,requester_id,client_request_id,share_id,asset_id,version_id,expected_publication_revision,request_hash,body,snapshot)
 VALUES(p_tenant,u,(p_body->>'client_request_id')::uuid,(p_body->>'share_id')::uuid,(proof->'snapshot'->'asset_binding'->>'asset_id')::uuid,(proof->'snapshot'->'asset_binding'->>'version_id')::uuid,(p_body->>'expected_publication_revision')::bigint,h,p_body,proof->'snapshot') RETURNING * INTO d;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(gen_random_uuid(),'tenant',p_tenant,u,'asset.deployment_submitted',d.request_id,'ok');
 RETURN jsonb_build_object('request_id',d.request_id,'status',d.status,'revision',d.revision,'publication_revision',NULL,'replayed',false);
 END IF;
 IF p_action='decide' THEN
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=p_id FOR UPDATE;
 ELSE
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=p_id;
 END IF;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF p_action='detail' THEN
 IF p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=d.asset_id;
 RETURN (to_jsonb(d)-ARRAY['tenant_id','client_request_id','request_hash','snapshot'])||jsonb_build_object('can_decide',role='PADMIN' AND u<>d.requester_id AND d.status='pending','current_publication_revision',coalesce(pub.publication_revision,0),'publication_status',pub.status);
 END IF;
 IF role<>'PADMIN' OR u=d.requester_id THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';END IF;
 IF ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['comment','decision','expected_revision','quality_reviewed','security_reviewed']
 OR coalesce(p_body->>'decision','') NOT IN ('approve','reject') OR jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number'
 OR coalesce(p_body->>'expected_revision','') !~ '^[12]$' OR jsonb_typeof(p_body->'comment') IS DISTINCT FROM 'string' OR btrim(p_body->>'comment')='' OR char_length(p_body->>'comment')>500
 OR jsonb_typeof(p_body->'quality_reviewed') IS DISTINCT FROM 'boolean' OR jsonb_typeof(p_body->'security_reviewed') IS DISTINCT FROM 'boolean'
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 v_status:=CASE WHEN p_body->>'decision'='approve' THEN 'approved' ELSE 'rejected' END;
 IF v_status='approved' AND d.status='pending' THEN
 IF p_body->'quality_reviewed'<>'true' OR p_body->'security_reviewed'<>'true' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 PERFORM share_id FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND share_id=d.share_id FOR SHARE;
 proof:=security.builder_evidence_share(p_session,p_tenant,'detail',d.share_id,'{}',p_mode);
 IF proof->>'status'<>'submitted' OR proof->'snapshot' IS DISTINCT FROM d.snapshot OR EXISTS(SELECT 1 FROM jsonb_each(proof->'current_conditions') x WHERE x.value<>'true')
 OR d.snapshot->'evaluation'->'passed' IS DISTINCT FROM 'true'::jsonb OR d.snapshot->>'purpose'<>'generate'
 THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 SELECT latest_revision INTO latest FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=d.asset_id FOR UPDATE;
 IF latest<>(d.snapshot->'asset_binding'->>'revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 v:=security.builder_version(p_session,p_tenant,d.asset_id,d.version_id);PERFORM security.builder_profile_validate(v->'config',v->'profile');
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':publication:'||d.asset_id::text,0));
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=d.asset_id FOR UPDATE;
 IF coalesce(pub.publication_revision,0)<>d.expected_publication_revision THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(d.body->'member_ids') id WHERE NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts a ON a.user_id=m.user_id WHERE m.tenant_id=p_tenant AND m.user_id=id::uuid AND m.active AND a.active)) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 END IF;
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=p_id FOR UPDATE;
 IF d.status<>'pending' THEN
 IF d.status=v_status AND d.decided_by=u AND (d.decision-'expected_revision')=(p_body-'expected_revision') THEN RETURN jsonb_build_object('request_id',p_id,'status',d.status,'revision',d.revision,'publication_revision',d.publication_revision,'replayed',true);END IF;
 RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 IF d.revision<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 UPDATE portal.asset_deployments SET status=v_status,revision=2,decided_by=u,decided_at=clock_timestamp(),decision=p_body,publication_revision=CASE WHEN v_status='approved' THEN expected_publication_revision+1 ELSE NULL END WHERE tenant_id=p_tenant AND request_id=p_id;
 IF v_status='approved' THEN
 SELECT coalesce(array_agg(value::uuid),'{}') INTO ids FROM jsonb_array_elements_text(d.body->'member_ids');
 INSERT INTO portal.asset_publications(tenant_id,asset_id,version_id,publication_revision,request_id,config,profile,profile_hash,config_hash,asset_revision,audience,member_ids,execution_mode)
 VALUES(p_tenant,d.asset_id,d.version_id,d.expected_publication_revision+1,p_id,v->'config',v->'profile',v->>'profile_hash',v->>'config_hash',(v->>'revision')::bigint,d.body->>'audience',ids,p_mode)
 ON CONFLICT(tenant_id,asset_id) DO UPDATE SET version_id=EXCLUDED.version_id,publication_revision=EXCLUDED.publication_revision,request_id=EXCLUDED.request_id,config=EXCLUDED.config,profile=EXCLUDED.profile,profile_hash=EXCLUDED.profile_hash,config_hash=EXCLUDED.config_hash,asset_revision=EXCLUDED.asset_revision,audience=EXCLUDED.audience,member_ids=EXCLUDED.member_ids,execution_mode=EXCLUDED.execution_mode,status='published',updated_at=clock_timestamp();
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(gen_random_uuid(),'tenant',p_tenant,u,'asset.deployment_'||v_status,p_id,'ok');
 RETURN jsonb_build_object('request_id',p_id,'status',v_status,'revision',2,'publication_revision',CASE WHEN v_status='approved' THEN d.expected_publication_revision+1 ELSE NULL END,'replayed',false);
END;$body$;
ALTER FUNCTION security.asset_deployment(uuid,uuid,text,uuid,jsonb,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.asset_deployment(uuid,uuid,text,uuid,jsonb,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.asset_deployment(uuid,uuid,text,uuid,jsonb,text) TO ai_web;
