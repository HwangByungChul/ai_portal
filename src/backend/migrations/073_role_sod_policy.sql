-- DP-16: Role SOD (Separation of Duties) — extended role definitions and user-role grants.
-- Prerequisite: migrations 000-072 applied.
SET search_path = security, public;

-- DP-16: Role definition catalogue
CREATE TABLE IF NOT EXISTS security.role_definitions (
    role_code    TEXT  PRIMARY KEY,
    description  TEXT  NOT NULL,
    sod_excludes TEXT[] NOT NULL DEFAULT '{}'  -- roles that CANNOT coexist with this role
);

INSERT INTO security.role_definitions (role_code, description, sod_excludes) VALUES
    ('BUILDER',  'AI 자산 초안 작성자 (Builder)',              ARRAY['REVIEWER','DEPLOYER']),
    ('REVIEWER', 'AI 자산 심사자 (Reviewer)',                  ARRAY['BUILDER']),
    ('DEPLOYER', 'AI 자산 배포 담당자 (Deployer)',             ARRAY['BUILDER'])
ON CONFLICT (role_code) DO NOTHING;

-- DP-16: User ↔ Role grant ledger (tenant-scoped)
CREATE TABLE IF NOT EXISTS security.user_role_grants (
    grant_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL REFERENCES security.tenants(tenant_id) ON DELETE CASCADE,
    user_id     UUID        NOT NULL REFERENCES security.accounts(user_id)  ON DELETE CASCADE,
    role_code   TEXT        NOT NULL REFERENCES security.role_definitions(role_code),
    granted_by  UUID        NOT NULL REFERENCES security.accounts(user_id),
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ,
    revoked_at  TIMESTAMPTZ,
    revoke_note TEXT,
    CONSTRAINT user_role_grants_no_self_grant CHECK (user_id != granted_by),
    CONSTRAINT user_role_grants_unique UNIQUE (tenant_id, user_id, role_code)
);

ALTER TABLE security.user_role_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE security.user_role_grants FORCE ROW LEVEL SECURITY;

CREATE POLICY user_role_grants_isolation ON security.user_role_grants
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::uuid);

-- DP-16: SOD violation check
CREATE OR REPLACE FUNCTION security.check_role_sod(
    p_tenant_id UUID,
    p_user_id   UUID,
    p_role_code TEXT
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, pg_temp AS $$
DECLARE
    v_excludes  TEXT[];
    v_conflicts TEXT[];
BEGIN
    SELECT sod_excludes INTO v_excludes
    FROM security.role_definitions WHERE role_code = p_role_code;

    IF v_excludes IS NULL THEN RETURN; END IF;  -- unknown role, skip

    SELECT array_agg(g.role_code) INTO v_conflicts
    FROM security.user_role_grants g
    WHERE g.tenant_id = p_tenant_id
      AND g.user_id   = p_user_id
      AND g.role_code = ANY(v_excludes)
      AND g.revoked_at IS NULL
      AND (g.expires_at IS NULL OR g.expires_at > now());

    IF v_conflicts IS NOT NULL AND array_length(v_conflicts, 1) > 0 THEN
        RAISE EXCEPTION 'ROLE_SOD_CONFLICT' USING ERRCODE = 'A0409';
    END IF;
END;
$$;

-- DP-16: Grant role (PADMIN only, with SOD check)
CREATE OR REPLACE FUNCTION security.role_grant(
    p_session    UUID,
    p_tenant     UUID,
    p_target_uid UUID,
    p_role_code  TEXT,
    p_expires_at TIMESTAMPTZ DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE
    v_role      TEXT;
    v_granter   UUID;
    v_grant_id  UUID;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role, user_id INTO v_role, v_granter
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role != 'PADMIN' THEN RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403'; END IF;
    IF v_granter = p_target_uid THEN RAISE EXCEPTION 'SELF_GRANT_FORBIDDEN' USING ERRCODE = 'A0409'; END IF;

    PERFORM security.check_role_sod(p_tenant, p_target_uid, p_role_code);

    INSERT INTO security.user_role_grants
        (tenant_id, user_id, role_code, granted_by, expires_at)
    VALUES
        (p_tenant, p_target_uid, p_role_code, v_granter, p_expires_at)
    ON CONFLICT (tenant_id, user_id, role_code) DO UPDATE
        SET revoked_at = NULL, revoke_note = NULL,
            granted_by = EXCLUDED.granted_by,
            granted_at = now(),
            expires_at = EXCLUDED.expires_at
    RETURNING grant_id INTO v_grant_id;

    RETURN jsonb_build_object('grant_id', v_grant_id::text);
END;
$$;

-- DP-16: Revoke role (PADMIN only)
CREATE OR REPLACE FUNCTION security.role_revoke(
    p_session    UUID,
    p_tenant     UUID,
    p_target_uid UUID,
    p_role_code  TEXT,
    p_note       TEXT DEFAULT ''
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role INTO v_role
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role != 'PADMIN' THEN RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403'; END IF;

    UPDATE security.user_role_grants
    SET revoked_at = now(), revoke_note = p_note
    WHERE tenant_id = p_tenant AND user_id = p_target_uid
      AND role_code = p_role_code AND revoked_at IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'GRANT_NOT_FOUND' USING ERRCODE = 'A0404'; END IF;
    RETURN jsonb_build_object('ok', TRUE);
END;
$$;

-- DP-16: List roles for a user
CREATE OR REPLACE FUNCTION security.role_list_for_user(
    p_session UUID, p_tenant UUID, p_target_uid UUID
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT; v_rows JSONB;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role INTO v_role
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role NOT IN ('PADMIN','TADMIN') THEN RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403'; END IF;
    SELECT jsonb_agg(jsonb_build_object(
        'grant_id',   grant_id::text,
        'role_code',  role_code,
        'granted_at', granted_at,
        'expires_at', expires_at,
        'revoked_at', revoked_at
    ) ORDER BY granted_at DESC) INTO v_rows
    FROM security.user_role_grants
    WHERE tenant_id = p_tenant AND user_id = p_target_uid AND revoked_at IS NULL
      AND (expires_at IS NULL OR expires_at > now());
    RETURN jsonb_build_object('roles', COALESCE(v_rows, '[]'::jsonb));
END;
$$;

COMMENT ON TABLE security.user_role_grants IS 'DP-16: SOD-enforced extended role grant ledger (BUILDER/REVIEWER/DEPLOYER).';
