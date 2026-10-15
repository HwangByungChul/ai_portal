-- C04 exact-version sharing. No payload SELECT added to the control role.
CREATE FUNCTION security.document_share_targets(p_session uuid,p_tenant uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 PERFORM security.document_manage(p_session,p_tenant,false);
 RETURN jsonb_build_object('items',coalesce((SELECT jsonb_agg(jsonb_build_object('tenant_id',tenant_id,'display_name',display_name) ORDER BY tenant_id) FROM security.tenants WHERE active AND tenant_id<>p_tenant AND fixture_label IN ('A','B')),'[]'::jsonb));
END;$body$;

CREATE FUNCTION security.document_share_control(p_session uuid,p_tenant uuid,p_document uuid,p_version uuid,p_action text,p_recipient uuid,p_grant uuid,p_expected bigint,p_request uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE actor uuid;a security.document_access%ROWTYPE;p security.document_publications%ROWTYPE;g security.share_grants%ROWTYPE;items jsonb;
BEGIN
 actor:=security.document_manage(p_session,p_tenant,true);
 IF p_action IS NULL OR p_action NOT IN ('list','issue','revoke') THEN RAISE EXCEPTION 'INVALID_ACTION' USING ERRCODE='A0422'; END IF;
 IF p_action='revoke' THEN
  SELECT * INTO g FROM security.share_grants WHERE owner_tenant_id=p_tenant AND grant_id=p_grant;
  IF NOT FOUND THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
  p_document:=g.document_id;p_version:=g.version_id;
 END IF;
 SELECT * INTO a FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document FOR UPDATE;
 IF NOT FOUND OR a.visibility<>'org' OR a.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 SELECT * INTO p FROM security.document_publications WHERE tenant_id=p_tenant AND document_id=p_document AND version_id=p_version FOR UPDATE;
 IF NOT FOUND OR (p_action<>'revoke' AND NOT p.active) THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404'; END IF;
 PERFORM security.document_manage(p_session,p_tenant,false);
 IF p_action='list' THEN
  SELECT coalesce(jsonb_agg(jsonb_build_object('grant_id',grant_id,'recipient_tenant_id',recipient_tenant_id,'active',active,'revision',revision,'issued_at',issued_at,'revoked_at',revoked_at) ORDER BY grant_id),'[]'::jsonb) INTO items FROM security.share_grants WHERE owner_tenant_id=p_tenant AND document_id=p_document AND version_id=p_version;
  RETURN jsonb_build_object('document_id',p_document,'version_id',p_version,'publication_revision',p.revision,'items',items);
 END IF;
 IF p_expected IS NULL OR p_expected<1 OR p_request IS NULL THEN RAISE EXCEPTION 'INVALID_ARGUMENT' USING ERRCODE='A0422'; END IF;
 IF p_action='issue' THEN
  PERFORM tenant_id FROM security.tenants WHERE tenant_id=p_recipient AND active AND tenant_id<>p_tenant AND fixture_label IN ('A','B') FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_RECIPIENT' USING ERRCODE='A0422'; END IF;
  SELECT * INTO g FROM security.share_grants WHERE owner_tenant_id=p_tenant AND document_id=p_document AND version_id=p_version AND recipient_tenant_id=p_recipient AND active FOR UPDATE;
  IF FOUND THEN RETURN jsonb_build_object('grant_id',g.grant_id,'recipient_tenant_id',g.recipient_tenant_id,'active',g.active,'revision',g.revision,'replayed',true); END IF;
  IF p.revision<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  INSERT INTO security.share_grants(grant_id,owner_tenant_id,document_id,version_id,recipient_tenant_id,issued_by) VALUES(gen_random_uuid(),p_tenant,p_document,p_version,p_recipient,actor) RETURNING * INTO g;
 ELSE
  SELECT * INTO g FROM security.share_grants WHERE grant_id=p_grant AND owner_tenant_id=p_tenant FOR UPDATE;
  IF NOT g.active THEN RETURN jsonb_build_object('grant_id',g.grant_id,'active',false,'revision',g.revision,'revoked_at',g.revoked_at,'replayed',true); END IF;
  IF g.revision<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
  UPDATE security.share_grants SET active=false,revoked_at=clock_timestamp(),revision=revision+1 WHERE grant_id=p_grant RETURNING * INTO g;
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions) VALUES(p_request,'tenant',p_tenant,actor,'document.share.'||p_action,g.grant_id,'ok',jsonb_build_object('revision',g.revision));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN jsonb_build_object('grant_id',g.grant_id,'recipient_tenant_id',g.recipient_tenant_id,'active',g.active,'revision',g.revision,'revoked_at',g.revoked_at,'replayed',false);
END;$body$;
ALTER FUNCTION security.document_share_targets(uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.document_share_control(uuid,uuid,uuid,uuid,text,uuid,uuid,bigint,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_share_targets(uuid,uuid),security.document_share_control(uuid,uuid,uuid,uuid,text,uuid,uuid,bigint,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_share_targets(uuid,uuid),security.document_share_control(uuid,uuid,uuid,uuid,text,uuid,uuid,bigint,uuid) TO ai_web;
CREATE POLICY audit_document_share ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK(session_user='ai_web' AND scope_kind='tenant' AND actor_id=nullif(current_setting('app.user_id',true),'')::uuid AND tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND security.can_manage_current_tenant(tenant_id) AND action IN ('document.share.issue','document.share.revoke'));
