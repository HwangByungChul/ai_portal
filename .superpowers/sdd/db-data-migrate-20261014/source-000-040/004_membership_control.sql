-- A04 additive migration; preserve checksums of 000 through 003.
CREATE OR REPLACE FUNCTION security.current_membership(p_session_id uuid,p_tenant uuid)
RETURNS TABLE(membership_id uuid,revision bigint,effective_role text,can_manage boolean)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT m.membership_id,m.revision,
 CASE WHEN COALESCE(p.active AND p.is_padmin,false) AND COALESCE(mt.active,false) THEN 'PADMIN' ELSE m.role END,
 (m.role='TADMIN' OR (COALESCE(p.active AND p.is_padmin,false) AND COALESCE(mt.active,false)))
 FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id
 JOIN security.memberships m ON m.user_id=a.user_id
 JOIN security.tenants t ON t.tenant_id=m.tenant_id
 LEFT JOIN security.platform_access p ON p.user_id=a.user_id
 LEFT JOIN security.managed_tenants mt ON mt.user_id=a.user_id AND mt.tenant_id=m.tenant_id
 WHERE s.session_id=p_session_id AND m.tenant_id=p_tenant AND a.active AND m.active AND t.active
 AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL
 AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes';
END; $body$;


CREATE FUNCTION security.list_memberships(p_session uuid,p_tenant uuid,p_cursor uuid,p_limit integer)
RETURNS TABLE(user_id uuid,display_name text,role text,active boolean,revision bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF NOT security.can_manage_current_tenant(p_tenant)
    OR NULLIF(current_setting('app.session_id',true),'')::uuid IS DISTINCT FROM p_session THEN
  RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';
 END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN
  RAISE EXCEPTION 'LIMIT_REJECTED' USING ERRCODE='A0422';
 END IF;
 RETURN QUERY SELECT m.user_id,a.display_name,
  CASE WHEN COALESCE(p.active AND p.is_padmin,false) AND COALESCE(mt.active,false) THEN 'PADMIN' ELSE m.role END,
  m.active,m.revision
 FROM security.memberships m JOIN security.accounts a ON a.user_id=m.user_id
 LEFT JOIN security.platform_access p ON p.user_id=m.user_id
 LEFT JOIN security.managed_tenants mt ON mt.user_id=m.user_id AND mt.tenant_id=m.tenant_id
 WHERE m.tenant_id=p_tenant AND (p_cursor IS NULL OR m.user_id>p_cursor)
 ORDER BY m.user_id LIMIT p_limit+1;
END; $body$;

CREATE FUNCTION security.record_http_read_window(p_session uuid,p_tenant uuid,p_digest bytea)
RETURNS TABLE(allowed boolean,retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_start timestamptz;v_now timestamptz;v_count integer;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF NOT security.can_manage_current_tenant(p_tenant)
    OR NULLIF(current_setting('app.session_id',true),'')::uuid IS DISTINCT FROM p_session THEN
  RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';
 END IF;
 IF p_digest IS NULL OR octet_length(p_digest)<>32 THEN
  RAISE EXCEPTION 'DIGEST_REJECTED' USING ERRCODE='A0422';
 END IF;
 INSERT INTO security.login_windows(purpose,key_kind,key_digest,window_started_at,count)
 VALUES('http_read','principal',p_digest,clock_timestamp(),0) ON CONFLICT DO NOTHING;
 SELECT w.window_started_at,w.count INTO v_start,v_count FROM security.login_windows w
 WHERE w.purpose='http_read' AND w.key_kind='principal' AND w.key_digest=p_digest FOR UPDATE;
 -- Recheck after a competing quota transaction finishes; no cached authority.
 IF NOT security.can_manage_current_tenant(p_tenant) THEN
  RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403';
 END IF;
 v_now:=clock_timestamp();
 IF v_now>=v_start+interval '1 minute' THEN
  v_start:=v_now;v_count:=0;
  UPDATE security.login_windows w SET window_started_at=v_start,count=0
   WHERE w.purpose='http_read' AND w.key_kind='principal' AND w.key_digest=p_digest;
 END IF;
 IF v_count>=120 THEN
  RETURN QUERY SELECT false,GREATEST(1,ceil(extract(epoch FROM v_start+interval '1 minute'-v_now))::integer);
  RETURN;
 END IF;
 UPDATE security.login_windows w SET count=w.count+1
 WHERE w.purpose='http_read' AND w.key_kind='principal' AND w.key_digest=p_digest;
 RETURN QUERY SELECT true,0;
END; $body$;

CREATE FUNCTION security.mutate_membership(p_session uuid,p_tenant uuid,p_target uuid,p_operation text,
 p_active boolean,p_role text,p_expected bigint,p_request uuid)
RETURNS TABLE(user_id uuid,display_name text,role text,active boolean,revision bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_current text;v_manage boolean;v_target security.memberships%ROWTYPE;v_padmin boolean;
BEGIN
 IF session_user<>'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_expected IS NULL OR p_expected<1 OR p_request IS NULL OR p_target IS NULL
 OR p_operation IS NULL OR p_operation NOT IN ('active','role')
 OR (p_operation='active' AND (p_active IS NULL OR p_role IS NOT NULL))
 OR (p_operation='role' AND (p_role IS NULL OR p_role NOT IN ('USER','TADMIN') OR p_active IS NOT NULL)) THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
 END IF;
 SELECT s.user_id INTO v_user FROM security.sessions s WHERE s.session_id=p_session;
 IF NOT FOUND THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 IF NULLIF(current_setting('app.session_id',true),'')::uuid IS DISTINCT FROM p_session
 OR NULLIF(current_setting('app.user_id',true),'')::uuid IS DISTINCT FROM v_user
 OR NULLIF(current_setting('app.tenant_id',true),'')::uuid IS DISTINCT FROM p_tenant THEN
  RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403';
 END IF;
 -- Accounts precede session locks, matching session issuance in migration 003.
 -- Shared account/tenant/platform locks protect revocation, session UPDATE avoids
 -- simultaneous SHARE-to-UPDATE upgrades when successful mutations touch idle.
 PERFORM a.user_id FROM security.accounts a WHERE a.user_id IN (v_user,p_target) ORDER BY a.user_id FOR SHARE;
 PERFORM t.tenant_id FROM security.tenants t WHERE t.tenant_id=p_tenant FOR SHARE;
 PERFORM p.user_id FROM security.platform_access p WHERE p.user_id IN (v_user,p_target) ORDER BY p.user_id FOR SHARE;
 PERFORM s.session_id FROM security.sessions s WHERE s.session_id=p_session FOR UPDATE;
 PERFORM m.user_id FROM security.memberships m WHERE m.tenant_id=p_tenant AND m.user_id IN (v_user,p_target)
 ORDER BY m.user_id FOR UPDATE;
 PERFORM mt.user_id FROM security.managed_tenants mt WHERE mt.tenant_id=p_tenant AND mt.user_id IN (v_user,p_target)
 ORDER BY mt.user_id FOR SHARE;
 IF NOT EXISTS(SELECT 1 FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id
  WHERE s.session_id=p_session AND a.active AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL
  AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes') THEN
  RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401';
 END IF;
 SELECT c.effective_role,c.can_manage INTO v_current,v_manage FROM security.current_membership(p_session,p_tenant) c;
 IF NOT FOUND OR NOT v_manage THEN RAISE EXCEPTION 'MANAGEMENT_DENIED' USING ERRCODE='A0403'; END IF;
 SELECT m.* INTO v_target FROM security.memberships m WHERE m.tenant_id=p_tenant AND m.user_id=p_target;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 -- Protect platform administrator identities even when their global access is inactive
 -- or they are not assigned to this tenant. Tenant APIs cannot alter platform staff.
 SELECT COALESCE(bool_or(p.is_padmin),false) INTO v_padmin FROM security.platform_access p WHERE p.user_id=p_target;
 IF p_target=v_user OR v_padmin OR (v_current<>'PADMIN' AND (p_operation='role' OR v_target.role<>'USER')) THEN
  RAISE EXCEPTION 'TARGET_DENIED' USING ERRCODE='A0403';
 END IF;
 IF v_target.revision<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 UPDATE security.memberships m SET active=CASE WHEN p_operation='active' THEN p_active ELSE m.active END,
 role=CASE WHEN p_operation='role' THEN p_role ELSE m.role END,revision=m.revision+1
 WHERE m.tenant_id=p_tenant AND m.user_id=p_target AND m.revision=p_expected;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,'membership_'||p_operation,p_target,'ok',
        jsonb_build_object('expected_revision',p_expected,'revision',p_expected+1));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN QUERY SELECT m.user_id,a.display_name,m.role,m.active,m.revision FROM security.memberships m
 JOIN security.accounts a ON a.user_id=m.user_id WHERE m.tenant_id=p_tenant AND m.user_id=p_target;
END; $body$;

ALTER FUNCTION security.list_memberships(uuid,uuid,uuid,integer) OWNER TO ai_policy_executor;
ALTER FUNCTION security.record_http_read_window(uuid,uuid,bytea) OWNER TO ai_policy_executor;
ALTER FUNCTION security.mutate_membership(uuid,uuid,uuid,text,boolean,text,bigint,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.list_memberships(uuid,uuid,uuid,integer),
 security.record_http_read_window(uuid,uuid,bytea),
 security.mutate_membership(uuid,uuid,uuid,text,boolean,text,bigint,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.list_memberships(uuid,uuid,uuid,integer),
 security.record_http_read_window(uuid,uuid,bytea),
 security.mutate_membership(uuid,uuid,uuid,text,boolean,text,bigint,uuid) TO ai_web;
