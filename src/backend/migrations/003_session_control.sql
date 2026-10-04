-- A03 additive controls. Applied A02 migration checksums must stay unchanged.
CREATE FUNCTION security.load_login_credential(p_login text) RETURNS TABLE(user_id uuid,password_hash text,active boolean,auth_revision bigint,display_name text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$

BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT a.user_id,a.password_hash,a.active,a.auth_revision,a.display_name
 FROM security.accounts a WHERE a.login_id=p_login;
END; $body$;

CREATE FUNCTION security.record_login_window(p_purpose text,p_kind text,p_digest bytea,p_limit integer,p_increment boolean) RETURNS TABLE(allowed boolean,retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_start timestamptz;v_now timestamptz;v_count integer;
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF NOT ((p_purpose='login_input' AND p_kind='login' AND p_limit=5) OR
          (p_purpose='login_ip' AND p_kind='ip' AND p_limit=30))
    OR p_digest IS NULL OR octet_length(p_digest)<>32 OR p_increment IS NULL THEN
  RAISE EXCEPTION 'WINDOW_ARGUMENT_REJECTED' USING ERRCODE='22023';
 END IF;
 INSERT INTO security.login_windows(purpose,key_kind,key_digest,window_started_at,count)
 VALUES(p_purpose,p_kind,p_digest,clock_timestamp(),0) ON CONFLICT DO NOTHING;
 SELECT w.window_started_at,w.count INTO v_start,v_count FROM security.login_windows w
 WHERE w.purpose=p_purpose AND w.key_kind=p_kind AND w.key_digest=p_digest FOR UPDATE;
 v_now:=clock_timestamp();
 IF v_now>=v_start+interval '15 minutes' THEN
  v_start:=v_now;v_count:=0;
  UPDATE security.login_windows w SET window_started_at=v_start,count=0
   WHERE w.purpose=p_purpose AND w.key_kind=p_kind AND w.key_digest=p_digest;
 END IF;
 IF v_count>=p_limit THEN
  RETURN QUERY SELECT false,GREATEST(1,ceil(extract(epoch FROM v_start+interval '15 minutes'-v_now))::integer);
  RETURN;
 END IF;
 IF p_increment THEN
  UPDATE security.login_windows w SET count=w.count+1
   WHERE w.purpose=p_purpose AND w.key_kind=p_kind AND w.key_digest=p_digest;
 END IF;
 RETURN QUERY SELECT true,0;
END; $body$;

CREATE FUNCTION security.reset_login_input_window(p_digest bytea) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$

BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 UPDATE security.login_windows w SET count=0
 WHERE w.purpose='login_input' AND w.key_kind='login' AND w.key_digest=p_digest;
END; $body$;

CREATE FUNCTION security.session_create_or_revoke(p_user uuid,p_revision bigint,p_new_hash bytea,p_csrf text,p_old_hash bytea) RETURNS TABLE(session_id uuid,expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_active boolean;v_revision bigint;v_now timestamptz;v_id uuid;
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_new_hash IS NULL OR octet_length(p_new_hash)<>32 OR p_csrf IS NULL OR p_csrf !~ '^[A-Za-z0-9_-]{43}$'
  OR (p_old_hash IS NOT NULL AND octet_length(p_old_hash)<>32) THEN
  RAISE EXCEPTION 'SESSION_ARGUMENT_REJECTED' USING ERRCODE='22023';
 END IF;
 SELECT a.active,a.auth_revision INTO v_active,v_revision FROM security.accounts a WHERE a.user_id=p_user FOR SHARE;
 IF NOT FOUND OR NOT v_active OR v_revision<>p_revision THEN RETURN; END IF;
 v_now:=clock_timestamp();v_id:=gen_random_uuid();
 UPDATE security.sessions s SET revoked_at=COALESCE(s.revoked_at,v_now) WHERE s.token_hash=p_old_hash;
 INSERT INTO security.sessions(session_id,token_hash,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at)
 VALUES(v_id,p_new_hash,p_user,v_revision,p_csrf,v_now,v_now,v_now+interval '8 hours');
 INSERT INTO ops.audit_events(event_id,scope_kind,actor_id,action,opaque_target_id,result)
 VALUES(gen_random_uuid(),'auth',p_user,'login',v_id,'ok');
 RETURN QUERY SELECT v_id,v_now+interval '8 hours';
END; $body$;

CREATE FUNCTION security.session_revoke(p_hash bytea) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_session uuid;v_user uuid;
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 UPDATE security.sessions s SET revoked_at=clock_timestamp()
 WHERE s.token_hash=p_hash AND s.revoked_at IS NULL RETURNING s.session_id,s.user_id INTO v_session,v_user;
 IF FOUND THEN
  INSERT INTO ops.audit_events(event_id,scope_kind,actor_id,action,opaque_target_id,result)
  VALUES(gen_random_uuid(),'auth',v_user,'logout',v_session,'ok');
 END IF;
 RETURN true;
END; $body$;

CREATE FUNCTION security.touch_session(p_session uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE ctx_user uuid;ctx_session uuid;
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 BEGIN
  ctx_user:=NULLIF(current_setting('app.user_id',true),'')::uuid;
  ctx_session:=NULLIF(current_setting('app.session_id',true),'')::uuid;
 EXCEPTION WHEN invalid_text_representation THEN RETURN false;
 END;
 IF ctx_session IS DISTINCT FROM p_session OR ctx_user IS NULL THEN RETURN false; END IF;
 UPDATE security.sessions s SET last_activity_at=GREATEST(s.last_activity_at,clock_timestamp())
 FROM security.accounts a WHERE a.user_id=s.user_id AND a.user_id=ctx_user AND s.session_id=p_session
 AND a.active AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL
 AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes';
 RETURN FOUND;
END; $body$;

CREATE FUNCTION security.list_own_tenants(p_session uuid) RETURNS TABLE(tenant_id uuid,display_name text,effective_role text,can_manage boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$

BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT t.tenant_id,t.display_name,c.effective_role,c.can_manage
 FROM security.memberships m JOIN security.tenants t ON t.tenant_id=m.tenant_id
 JOIN security.sessions s ON s.user_id=m.user_id AND s.session_id=p_session
 CROSS JOIN LATERAL security.current_membership(p_session,t.tenant_id) c
 ORDER BY t.tenant_id;
END; $body$;

CREATE FUNCTION security.session_capabilities(p_session uuid,p_period date,p_mode text) RETURNS TABLE(can_view_platform_usage boolean,can_change_platform_availability boolean,availability_enabled boolean,availability_revision bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_read boolean;v_write boolean;v_enabled boolean;v_revision bigint;
BEGIN
 IF session_user <> 'ai_web' THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 SELECT a.user_id INTO v_user FROM security.sessions s JOIN security.accounts a ON a.user_id=s.user_id
 WHERE s.session_id=p_session AND a.active AND s.auth_revision=a.auth_revision AND s.revoked_at IS NULL
 AND clock_timestamp()<s.expires_at AND clock_timestamp()<s.last_activity_at+interval '30 minutes';
 IF NOT FOUND THEN RETURN; END IF;
 SELECT COALESCE(p.active AND p.is_padmin AND 'global_usage_read'=ANY(p.permissions),false),
        COALESCE(p.active AND p.is_padmin AND 'global_stop_write'=ANY(p.permissions),false)
 INTO v_read,v_write FROM security.platform_access p WHERE p.user_id=v_user;
 v_read:=COALESCE(v_read,false);v_write:=COALESCE(v_write,false);
 IF v_write THEN
  SELECT NOT (b.stopped OR b.stop_latch),b.revision INTO v_enabled,v_revision
  FROM ops.project_budget b WHERE b.period=p_period AND b.mode=p_mode;
  IF NOT FOUND THEN RAISE EXCEPTION 'BUDGET_STATE_UNAVAILABLE' USING ERRCODE='P0002'; END IF;
 END IF;
 RETURN QUERY SELECT v_read,v_write,v_enabled,v_revision;
END; $body$;
ALTER FUNCTION security.load_login_credential(text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.load_login_credential(text) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.load_login_credential(text) TO ai_web;
ALTER FUNCTION security.record_login_window(text,text,bytea,integer,boolean) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.record_login_window(text,text,bytea,integer,boolean) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.record_login_window(text,text,bytea,integer,boolean) TO ai_web;
ALTER FUNCTION security.reset_login_input_window(bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.reset_login_input_window(bytea) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.reset_login_input_window(bytea) TO ai_web;
ALTER FUNCTION security.session_create_or_revoke(uuid,bigint,bytea,text,bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.session_create_or_revoke(uuid,bigint,bytea,text,bytea) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.session_create_or_revoke(uuid,bigint,bytea,text,bytea) TO ai_web;
ALTER FUNCTION security.session_revoke(bytea) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.session_revoke(bytea) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.session_revoke(bytea) TO ai_web;
ALTER FUNCTION security.touch_session(uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.touch_session(uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.touch_session(uuid) TO ai_web;
ALTER FUNCTION security.list_own_tenants(uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.list_own_tenants(uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.list_own_tenants(uuid) TO ai_web;
ALTER FUNCTION security.session_capabilities(uuid,date,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.session_capabilities(uuid,date,text) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.session_capabilities(uuid,date,text) TO ai_web;
