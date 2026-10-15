-- Additive rollback approval and immutable publication metadata.
ALTER TABLE portal.asset_deployments ADD COLUMN deployment_kind text NOT NULL DEFAULT 'publish' CHECK(deployment_kind IN ('publish','rollback'));
ALTER TABLE portal.asset_deployments ADD COLUMN source_request_id uuid;
ALTER TABLE portal.asset_deployments ADD CONSTRAINT deployment_source FOREIGN KEY(tenant_id,source_request_id) REFERENCES portal.asset_deployments(tenant_id,request_id);
ALTER TABLE portal.asset_deployments ADD CONSTRAINT rollback_source CHECK((deployment_kind='publish' AND source_request_id IS NULL) OR (deployment_kind='rollback' AND source_request_id IS NOT NULL AND source_request_id<>request_id));
CREATE TABLE portal.asset_publication_events(
 tenant_id uuid NOT NULL,asset_id uuid NOT NULL,publication_revision bigint NOT NULL,
 request_id uuid NOT NULL,version_id uuid NOT NULL,asset_revision bigint NOT NULL,profile_hash text NOT NULL,config_hash text NOT NULL,
 status text NOT NULL CHECK(status IN ('published','retired')),event_kind text NOT NULL CHECK(event_kind IN ('publish','rollback','retire','approval_record','current_state')),
 actor_id uuid,occurred_at timestamptz NOT NULL,PRIMARY KEY(tenant_id,asset_id,publication_revision),
 FOREIGN KEY(tenant_id,request_id) REFERENCES portal.asset_deployments(tenant_id,request_id),
 FOREIGN KEY(tenant_id,version_id) REFERENCES portal.asset_versions(tenant_id,version_id));
-- Existing approvals prove atomic publication; missing retirement actors/events are not inferred.
INSERT INTO portal.asset_publication_events SELECT tenant_id,asset_id,publication_revision,request_id,version_id,(snapshot->'asset_binding'->>'revision')::bigint,snapshot->>'profile_hash',snapshot->'asset_binding'->>'config_hash','published','approval_record',decided_by,decided_at FROM portal.asset_deployments WHERE status='approved';
INSERT INTO portal.asset_publication_events SELECT tenant_id,asset_id,publication_revision,request_id,version_id,asset_revision,profile_hash,config_hash,status,'current_state',NULL,updated_at FROM portal.asset_publications ON CONFLICT DO NOTHING;
ALTER TABLE portal.asset_publication_events OWNER TO ai_owner;
ALTER TABLE portal.asset_publication_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.asset_publication_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.asset_publication_events FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT ON portal.asset_publication_events TO ai_policy_executor;
CREATE POLICY publication_event_manage ON portal.asset_publication_events TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND current_setting('app.operations_scope',true)='agent_admin' AND security.can_manage_current_tenant(tenant_id));
CREATE TRIGGER publication_event_immutable BEFORE UPDATE OR DELETE ON portal.asset_publication_events FOR EACH ROW EXECUTE FUNCTION portal.builder_assessment_immutable();
CREATE FUNCTION portal.asset_publication_record() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
DECLARE kind text;
BEGIN
 SELECT deployment_kind INTO kind FROM portal.asset_deployments WHERE tenant_id=NEW.tenant_id AND request_id=NEW.request_id;
 INSERT INTO portal.asset_publication_events VALUES(NEW.tenant_id,NEW.asset_id,NEW.publication_revision,NEW.request_id,NEW.version_id,NEW.asset_revision,NEW.profile_hash,NEW.config_hash,NEW.status,
 CASE WHEN NEW.status='retired' THEN 'retire' ELSE kind END,nullif(current_setting('app.user_id',true),'')::uuid,NEW.updated_at);
 RETURN NEW;
END;$body$;
ALTER FUNCTION portal.asset_publication_record() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.asset_publication_record() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER asset_publication_record AFTER INSERT OR UPDATE ON portal.asset_publications FOR EACH ROW EXECUTE FUNCTION portal.asset_publication_record();

CREATE FUNCTION security.asset_rollback(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;role text;d portal.asset_deployments%ROWTYPE;source portal.asset_deployments%ROWTYPE;pub portal.asset_publications%ROWTYPE;
 proof jsonb;v jsonb;h text;items jsonb;next_id bigint;anchor bigint;left_event portal.asset_publication_events%ROWTYPE;right_event portal.asset_publication_events%ROWTYPE;
 a jsonb;b jsonb;fields jsonb:='[]';key text;av jsonb;bv jsonb;ids uuid[];v_status text;ready boolean;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('submit','decide','ready','history','compare') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' OR coalesce(p_mode,'') NOT IN ('mock','real') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action IN ('submit','decide'));
 SELECT effective_role INTO role FROM security.current_membership(p_session,p_tenant);
 IF p_action IN ('history','compare') THEN
 IF NOT EXISTS(SELECT 1 FROM portal.assets WHERE tenant_id=p_tenant AND asset_id=p_id) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF p_action='history' THEN
 IF p_body-ARRAY['cursor']<>'{}' OR (p_body ? 'cursor' AND (jsonb_typeof(p_body->'cursor') IS DISTINCT FROM 'number' OR coalesce(p_body->>'cursor','') !~ '^[1-9][0-9]*$')) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 anchor:=(p_body->>'cursor')::bigint;
 IF anchor IS NOT NULL AND NOT EXISTS(SELECT 1 FROM portal.asset_publication_events WHERE tenant_id=p_tenant AND asset_id=p_id AND publication_revision=anchor) THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.publication_revision DESC),'[]') INTO items FROM
 (SELECT publication_revision,request_id,version_id,asset_revision,profile_hash,config_hash,status,event_kind,actor_id,occurred_at FROM portal.asset_publication_events WHERE tenant_id=p_tenant AND asset_id=p_id AND (anchor IS NULL OR publication_revision<anchor) ORDER BY publication_revision DESC LIMIT 21) x;
 IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'publication_revision')::bigint;END IF;
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=p_id;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id,'current_publication_revision',coalesce(pub.publication_revision,0),'current_status',pub.status,
 'history_complete',(SELECT count(*)=coalesce(pub.publication_revision,0) FROM portal.asset_publication_events WHERE tenant_id=p_tenant AND asset_id=p_id));
 END IF;
 IF ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['left_revision','right_revision'] OR EXISTS(SELECT 1 FROM jsonb_each(p_body) x WHERE jsonb_typeof(x.value)<>'number' OR x.value::text !~ '^[1-9][0-9]*$') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 SELECT * INTO left_event FROM portal.asset_publication_events WHERE tenant_id=p_tenant AND asset_id=p_id AND publication_revision=(p_body->>'left_revision')::bigint;
 SELECT * INTO right_event FROM portal.asset_publication_events WHERE tenant_id=p_tenant AND asset_id=p_id AND publication_revision=(p_body->>'right_revision')::bigint;
 IF left_event.version_id IS NULL OR right_event.version_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 a:=security.builder_version(p_session,p_tenant,p_id,left_event.version_id);b:=security.builder_version(p_session,p_tenant,p_id,right_event.version_id);
 PERFORM security.builder_profile_validate(a->'config',a->'profile');PERFORM security.builder_profile_validate(b->'config',b->'profile');
 FOREACH key IN ARRAY ARRAY['name','description','system_prompt','developer_prompt','user_template','model_ref','document_refs'] LOOP
 av:=CASE WHEN key IN ('name','description') THEN a->'config'->key ELSE a->'profile'->key END;
 bv:=CASE WHEN key IN ('name','description') THEN b->'config'->key ELSE b->'profile'->key END;
 fields:=fields||jsonb_build_array(jsonb_build_object('field',key,'before',av,'after',bv,'changed',av IS DISTINCT FROM bv));
 END LOOP;
 RETURN jsonb_build_object('left_revision',left_event.publication_revision,'right_revision',right_event.publication_revision,'left_asset_revision',left_event.asset_revision,'right_asset_revision',right_event.asset_revision,'fields',fields);
 END IF;
 IF p_action='submit' THEN
 IF ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['client_request_id','expected_publication_revision','reason','source_request_id'] OR jsonb_typeof(p_body->'reason') IS DISTINCT FROM 'string' OR btrim(p_body->>'reason')='' OR char_length(p_body->>'reason')>500 OR jsonb_typeof(p_body->'expected_publication_revision') IS DISTINCT FROM 'number' OR coalesce(p_body->>'expected_publication_revision','') !~ '^[1-9][0-9]*$' OR coalesce(p_body->>'client_request_id','')='' OR coalesce(p_body->>'source_request_id','')='' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':deployment-queue:'||u::text,0));
 h:=encode(sha256(convert_to(p_body::text,'UTF8')),'hex');
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND requester_id=u AND client_request_id=(p_body->>'client_request_id')::uuid;
 IF FOUND THEN
 IF d.deployment_kind<>'rollback' OR d.request_hash<>h THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 RETURN jsonb_build_object('request_id',d.request_id,'status',d.status,'revision',d.revision,'publication_revision',d.publication_revision,'replayed',true);END IF;
 SELECT * INTO source FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=(p_body->>'source_request_id')::uuid AND status='approved';
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=source.asset_id;
 IF NOT FOUND OR pub.publication_revision<>(p_body->>'expected_publication_revision')::bigint OR (pub.status='published' AND pub.version_id=source.version_id) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 d:=source;
 ELSE
 IF p_action='decide' THEN SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=p_id AND deployment_kind='rollback' FOR UPDATE;
 ELSE SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=p_id AND deployment_kind='rollback';END IF;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 END IF;
 IF p_action='decide' THEN
 IF role<>'PADMIN' OR u=d.requester_id THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';END IF;
 IF ARRAY(SELECT jsonb_object_keys(p_body) ORDER BY 1)<>ARRAY['comment','decision','expected_revision','quality_reviewed','security_reviewed'] OR coalesce(p_body->>'decision','') NOT IN ('approve','reject') OR jsonb_typeof(p_body->'expected_revision') IS DISTINCT FROM 'number' OR coalesce(p_body->>'expected_revision','') !~ '^[12]$' OR jsonb_typeof(p_body->'comment') IS DISTINCT FROM 'string' OR btrim(p_body->>'comment')='' OR char_length(p_body->>'comment')>500 OR jsonb_typeof(p_body->'quality_reviewed') IS DISTINCT FROM 'boolean' OR jsonb_typeof(p_body->'security_reviewed') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 v_status:=CASE WHEN p_body->>'decision'='approve' THEN 'approved' ELSE 'rejected' END;
 IF d.status<>'pending' THEN
 IF d.status=v_status AND d.decided_by=u AND (d.decision-'expected_revision')=(p_body-'expected_revision') THEN RETURN jsonb_build_object('request_id',p_id,'status',d.status,'revision',d.revision,'publication_revision',d.publication_revision,'replayed',true);END IF;
 RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 IF d.revision<>(p_body->>'expected_revision')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 IF v_status='approved' AND (p_body->'quality_reviewed'<>'true' OR p_body->'security_reviewed'<>'true') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 END IF;
 IF p_action IN ('submit','ready') OR (p_action='decide' AND v_status='approved') THEN
 -- Historical latest-version/profile drift is expected; exact saved profile is revalidated.
 PERFORM share_id FROM portal.builder_evidence_shares WHERE tenant_id=p_tenant AND share_id=d.share_id FOR SHARE;
 proof:=security.builder_evidence_share(p_session,p_tenant,'detail',d.share_id,'{}',p_mode);
 v:=security.builder_version(p_session,p_tenant,d.asset_id,d.version_id);PERFORM security.builder_profile_validate(v->'config',v->'profile');
 ready:=proof->>'status'='submitted' AND proof->'snapshot'=d.snapshot AND d.snapshot->'evaluation'->'passed'='true'::jsonb AND d.snapshot->>'purpose'='generate'
 AND proof->'current_conditions'->'same_mode'='true'::jsonb AND proof->'current_conditions'->'same_policy'='true'::jsonb AND v->>'profile_hash'=d.snapshot->>'profile_hash' AND v->>'config_hash'=d.snapshot->'asset_binding'->>'config_hash';
 IF p_action='ready' THEN RETURN jsonb_build_object('ready',coalesce(ready,false));END IF;
 IF NOT coalesce(ready,false) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 END IF;
 IF p_action='submit' THEN
 IF (SELECT count(*) FROM portal.asset_deployments WHERE tenant_id=p_tenant AND requester_id=u AND status='pending')>=20 THEN RAISE EXCEPTION 'QUEUE_LIMIT' USING ERRCODE='D0429';END IF;
 INSERT INTO portal.asset_deployments(tenant_id,requester_id,client_request_id,share_id,asset_id,version_id,expected_publication_revision,request_hash,body,snapshot,deployment_kind,source_request_id)
 VALUES(p_tenant,u,(p_body->>'client_request_id')::uuid,source.share_id,source.asset_id,source.version_id,pub.publication_revision,h,
 jsonb_build_object('reason',p_body->>'reason','audience',pub.audience,'member_ids',to_jsonb(pub.member_ids)),source.snapshot,'rollback',source.request_id) RETURNING * INTO d;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(gen_random_uuid(),'tenant',p_tenant,u,'asset.rollback_submitted',d.request_id,'ok');
 RETURN jsonb_build_object('request_id',d.request_id,'status',d.status,'revision',1,'publication_revision',NULL,'replayed',false);
 END IF;
 IF v_status='approved' THEN
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':publication:'||d.asset_id::text,0));
 SELECT * INTO pub FROM portal.asset_publications WHERE tenant_id=p_tenant AND asset_id=d.asset_id FOR UPDATE;
 IF NOT FOUND OR pub.publication_revision<>d.expected_publication_revision OR pub.audience<>d.body->>'audience' OR to_jsonb(pub.member_ids)<>d.body->'member_ids' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 IF EXISTS(SELECT 1 FROM unnest(pub.member_ids) id WHERE NOT EXISTS(SELECT 1 FROM security.memberships m JOIN security.accounts a USING(user_id) WHERE m.tenant_id=p_tenant AND m.user_id=id AND m.active AND a.active)) THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';END IF;
 END IF;
 UPDATE portal.asset_deployments SET status=v_status,revision=2,decided_by=u,decided_at=clock_timestamp(),decision=p_body,publication_revision=CASE WHEN v_status='approved' THEN expected_publication_revision+1 ELSE NULL END WHERE tenant_id=p_tenant AND request_id=p_id;
 IF v_status='approved' THEN
 UPDATE portal.asset_publications SET version_id=d.version_id,publication_revision=pub.publication_revision+1,request_id=p_id,config=v->'config',profile=v->'profile',profile_hash=v->>'profile_hash',config_hash=v->>'config_hash',asset_revision=(v->>'revision')::bigint,status='published',execution_mode=p_mode,updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND asset_id=d.asset_id;
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result) VALUES(gen_random_uuid(),'tenant',p_tenant,u,'asset.rollback_'||v_status,p_id,'ok');
 RETURN jsonb_build_object('request_id',p_id,'status',v_status,'revision',2,'publication_revision',CASE WHEN v_status='approved' THEN d.expected_publication_revision+1 ELSE NULL END,'replayed',false);
END;$body$;
ALTER FUNCTION security.asset_rollback(uuid,uuid,text,uuid,jsonb,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.asset_rollback(uuid,uuid,text,uuid,jsonb,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.asset_rollback(uuid,uuid,text,uuid,jsonb,text) TO ai_web;

ALTER FUNCTION security.asset_deployment(uuid,uuid,text,uuid,jsonb,text) RENAME TO asset_deployment_v1;
REVOKE EXECUTE ON FUNCTION security.asset_deployment_v1(uuid,uuid,text,uuid,jsonb,text) FROM ai_web;
CREATE FUNCTION security.asset_deployment(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE d portal.asset_deployments%ROWTYPE;data jsonb;row jsonb;items jsonb:='[]';ready boolean;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'agent_admin',p_action IN ('submit','decide','retire'));
 IF p_action='decide' THEN
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=p_id;
 IF d.deployment_kind='rollback' THEN RETURN security.asset_rollback(p_session,p_tenant,'decide',p_id,p_body,p_mode);END IF;
 END IF;
 data:=security.asset_deployment_v1(p_session,p_tenant,p_action,p_id,p_body,p_mode);
 IF p_action='list' THEN
 FOR row IN SELECT value FROM jsonb_array_elements(data->'items') LOOP
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=(row->>'request_id')::uuid;
 items:=items||jsonb_build_array(row||jsonb_build_object('deployment_kind',d.deployment_kind,'source_request_id',d.source_request_id));
 END LOOP;RETURN data||jsonb_build_object('items',items);
 END IF;
 IF p_action='detail' THEN
 SELECT * INTO d FROM portal.asset_deployments WHERE tenant_id=p_tenant AND request_id=p_id;
 IF d.deployment_kind='rollback' AND d.status='pending' THEN
 BEGIN ready:=coalesce((security.asset_rollback(p_session,p_tenant,'ready',p_id,'{}',p_mode)->>'ready')::boolean,false);
 EXCEPTION WHEN SQLSTATE 'A0404' OR SQLSTATE 'D0404' OR SQLSTATE 'A0409' THEN ready:=false;END;
 END IF;
 RETURN data||jsonb_build_object('deployment_kind',d.deployment_kind,'source_request_id',d.source_request_id,'rollback_ready',coalesce(ready,false));
 END IF;RETURN data;
END;$body$;
ALTER FUNCTION security.asset_deployment(uuid,uuid,text,uuid,jsonb,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.asset_deployment(uuid,uuid,text,uuid,jsonb,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.asset_deployment(uuid,uuid,text,uuid,jsonb,text) TO ai_web;
