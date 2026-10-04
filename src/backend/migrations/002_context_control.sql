CREATE FUNCTION security.can_read_own_conversation(row_tenant uuid,row_owner uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE ctx_session uuid; ctx_user uuid; ctx_tenant uuid;
BEGIN
 IF session_user <> 'ai_web' THEN RETURN false; END IF;
 BEGIN
  ctx_session := NULLIF(current_setting('app.session_id',true),'')::uuid;
  ctx_user := NULLIF(current_setting('app.user_id',true),'')::uuid;
  ctx_tenant := NULLIF(current_setting('app.tenant_id',true),'')::uuid;
 EXCEPTION WHEN invalid_text_representation THEN RETURN false;
 END;
 IF ctx_session IS NULL OR ctx_user IS NULL OR ctx_tenant IS NULL THEN RETURN false; END IF;
 RETURN EXISTS (
  SELECT 1 FROM security.sessions s
  JOIN security.accounts a ON a.user_id=s.user_id
  JOIN security.memberships m ON m.user_id=a.user_id
  JOIN security.tenants t ON t.tenant_id=m.tenant_id
  WHERE s.session_id=ctx_session AND a.user_id=ctx_user
   AND m.tenant_id=ctx_tenant AND m.tenant_id=row_tenant AND a.user_id=row_owner
   AND a.active AND m.active AND t.active AND s.revoked_at IS NULL
   AND s.auth_revision=a.auth_revision AND clock_timestamp()<s.expires_at
   AND clock_timestamp()<s.last_activity_at+interval '30 minutes'
 );
END; $body$;

CREATE FUNCTION security.can_read_agent(row_tenant uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE ctx_user uuid;
BEGIN
 IF session_user <> 'ai_web' THEN RETURN false; END IF;
 BEGIN ctx_user := NULLIF(current_setting('app.user_id',true),'')::uuid;
 EXCEPTION WHEN invalid_text_representation THEN RETURN false;
 END;
 RETURN security.can_read_own_conversation(row_tenant,ctx_user);
END; $body$;

CREATE FUNCTION security.session_validate(p_token_hash bytea)
RETURNS TABLE(session_id uuid,user_id uuid,display_name text,csrf_secret text,
              expires_at timestamptz,auth_revision bigint)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT s.session_id,a.user_id,a.display_name,s.csrf_secret,s.expires_at,s.auth_revision
 FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id
 WHERE octet_length(p_token_hash)=32 AND s.token_hash=p_token_hash
 AND a.active AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL
 AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes';
END; $body$;

CREATE FUNCTION security.current_membership(p_session_id uuid,p_tenant uuid)
RETURNS TABLE(membership_id uuid,revision bigint,effective_role text,can_manage boolean)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT m.membership_id,m.revision,
 CASE WHEN COALESCE(p.active AND p.is_padmin,false) THEN 'PADMIN' ELSE m.role END,
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

CREATE FUNCTION security.can_manage_current_tenant(row_tenant uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE ctx_session uuid;
BEGIN
 IF session_user <> 'ai_web' OR NOT security.can_read_agent(row_tenant) THEN RETURN false; END IF;
 BEGIN ctx_session := NULLIF(current_setting('app.session_id',true),'')::uuid;
 EXCEPTION WHEN invalid_text_representation THEN RETURN false;
 END;
 RETURN EXISTS (SELECT 1 FROM security.current_membership(ctx_session,row_tenant) m WHERE m.can_manage);
END; $body$;

ALTER FUNCTION security.can_read_own_conversation(uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.can_read_agent(uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.session_validate(bytea) OWNER TO ai_policy_executor;
ALTER FUNCTION security.current_membership(uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.can_manage_current_tenant(uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA security FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT USAGE ON SCHEMA security,portal,ops TO ai_web;
GRANT USAGE ON SCHEMA ops TO ai_policy_executor;
GRANT SELECT(period,mode,stopped,stop_latch,revision) ON ops.project_budget TO ai_policy_executor;
GRANT INSERT(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,safe_reason,revisions)
 ON ops.audit_events TO ai_policy_executor;
GRANT SELECT,INSERT ON portal.conversations TO ai_web;
GRANT UPDATE(updated_at) ON portal.conversations TO ai_web;
GRANT SELECT ON portal.agent_configs TO ai_web;
GRANT SELECT(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,safe_reason,revisions,created_at)
 ON ops.audit_events TO ai_web;
GRANT EXECUTE ON FUNCTION security.can_read_own_conversation(uuid,uuid),security.can_read_agent(uuid),
 security.can_manage_current_tenant(uuid),security.session_validate(bytea),
 security.current_membership(uuid,uuid) TO ai_web;
CREATE POLICY conversation_owner ON portal.conversations TO ai_web
 USING (security.can_read_own_conversation(tenant_id,owner_user_id))
 WITH CHECK (security.can_read_own_conversation(tenant_id,owner_user_id));
CREATE POLICY agent_member ON portal.agent_configs FOR SELECT TO ai_web
 USING (security.can_read_agent(tenant_id));
CREATE POLICY audit_tenant_read ON ops.audit_events FOR SELECT TO ai_web
 USING (scope_kind='tenant' AND security.can_manage_current_tenant(tenant_id));
CREATE POLICY audit_control_insert ON ops.audit_events FOR INSERT TO ai_policy_executor
 WITH CHECK (scope_kind IN ('auth','platform') OR
             (scope_kind='tenant' AND security.can_manage_current_tenant(tenant_id)));
