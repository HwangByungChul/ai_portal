-- DP-17: Data Import Approval Ledger
-- Prerequisite: migrations 000-073 applied.
SET search_path = security, public;

CREATE TABLE IF NOT EXISTS security.data_import_requests (
    import_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL REFERENCES security.tenants(tenant_id) ON DELETE CASCADE,
    requester_id    UUID        NOT NULL REFERENCES security.accounts(user_id),
    import_type     TEXT        NOT NULL CHECK (import_type IN ('model','document','dataset')),
    filename        TEXT        NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    mime_type       TEXT,
    sha256          TEXT        NOT NULL CHECK (length(sha256) = 64),
    file_size_bytes BIGINT,
    pii_scan        JSONB,      -- result of automated PII/pattern detection
    format_scan     JSONB,      -- allowed MIME/extension check
    malware_scan    JSONB,      -- hash-based quick scan result
    status          TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','scanning','review','approved','rejected')),
    reviewer_id     UUID        REFERENCES security.accounts(user_id),
    decided_at      TIMESTAMPTZ,
    decision_note   TEXT,
    cas_token       INT         NOT NULL DEFAULT 1,  -- optimistic concurrency
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT data_import_no_self_approve CHECK (
        reviewer_id IS NULL OR requester_id != reviewer_id
    )
);

ALTER TABLE security.data_import_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE security.data_import_requests FORCE ROW LEVEL SECURITY;

-- Requester sees own; PADMIN/TADMIN sees org-wide
CREATE POLICY data_import_requester ON security.data_import_requests
    USING (
        tenant_id = current_setting('app.tenant_id', TRUE)::uuid
        AND (
            requester_id = current_setting('app.user_id', TRUE)::uuid
            OR current_setting('app.effective_role', TRUE) IN ('PADMIN','TADMIN')
        )
    );

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION security.touch_data_import()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS trg_touch_data_import ON security.data_import_requests;
CREATE TRIGGER trg_touch_data_import
    BEFORE UPDATE ON security.data_import_requests
    FOR EACH ROW EXECUTE FUNCTION security.touch_data_import();

-- DP-17: Create import request
CREATE OR REPLACE FUNCTION security.data_import_create(
    p_session    UUID,
    p_tenant     UUID,
    p_type       TEXT,
    p_filename   TEXT,
    p_mime       TEXT,
    p_sha256     TEXT,
    p_file_size  BIGINT
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_uid UUID; v_id UUID;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT user_id INTO v_uid FROM security.active_sessions
    WHERE session_id = p_session AND tenant_id = p_tenant;

    INSERT INTO security.data_import_requests
        (tenant_id, requester_id, import_type, filename, mime_type, sha256, file_size_bytes)
    VALUES
        (p_tenant, v_uid, p_type, p_filename, p_mime, p_sha256, p_file_size)
    RETURNING import_id INTO v_id;

    RETURN jsonb_build_object('import_id', v_id::text, 'status', 'pending');
END;
$$;

-- DP-17: Update scan results (internal service call)
CREATE OR REPLACE FUNCTION security.data_import_set_scan(
    p_session   UUID,
    p_tenant    UUID,
    p_import_id UUID,
    p_pii       JSONB,
    p_format    JSONB,
    p_malware   JSONB,
    p_status    TEXT   -- 'review' or 'rejected'
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role INTO v_role FROM security.active_sessions
    WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role NOT IN ('PADMIN','TADMIN') THEN
        RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403';
    END IF;
    UPDATE security.data_import_requests
    SET pii_scan = p_pii, format_scan = p_format, malware_scan = p_malware,
        status = p_status, cas_token = cas_token + 1
    WHERE import_id = p_import_id AND tenant_id = p_tenant AND status = 'scanning';
    IF NOT FOUND THEN RAISE EXCEPTION 'IMPORT_NOT_FOUND' USING ERRCODE = 'A0404'; END IF;
    RETURN jsonb_build_object('ok', TRUE);
END;
$$;

-- DP-17: Approve or reject (PADMIN/TADMIN, no self-approve)
CREATE OR REPLACE FUNCTION security.data_import_decide(
    p_session    UUID,
    p_tenant     UUID,
    p_import_id  UUID,
    p_decision   TEXT,   -- 'approved' | 'rejected'
    p_note       TEXT,
    p_cas_token  INT
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT; v_reviewer UUID; v_requester UUID; v_cas INT;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role, user_id INTO v_role, v_reviewer
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role NOT IN ('PADMIN','TADMIN') THEN
        RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403';
    END IF;

    SELECT requester_id, cas_token INTO v_requester, v_cas
    FROM security.data_import_requests
    WHERE import_id = p_import_id AND tenant_id = p_tenant AND status = 'review';
    IF NOT FOUND THEN RAISE EXCEPTION 'IMPORT_NOT_FOUND' USING ERRCODE = 'A0404'; END IF;
    IF v_requester = v_reviewer THEN RAISE EXCEPTION 'SELF_APPROVE_FORBIDDEN' USING ERRCODE = 'A0409'; END IF;
    IF v_cas != p_cas_token THEN RAISE EXCEPTION 'IMPORT_CAS_CONFLICT' USING ERRCODE = 'A0409'; END IF;

    UPDATE security.data_import_requests
    SET status = p_decision, reviewer_id = v_reviewer,
        decided_at = now(), decision_note = p_note, cas_token = cas_token + 1
    WHERE import_id = p_import_id AND tenant_id = p_tenant;

    RETURN jsonb_build_object('ok', TRUE, 'decision', p_decision);
END;
$$;

-- DP-17: List imports (user sees own; admin sees all)
CREATE OR REPLACE FUNCTION security.data_import_list(
    p_session UUID, p_tenant UUID,
    p_status TEXT DEFAULT NULL,
    p_limit INT DEFAULT 20
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT; v_uid UUID; v_rows JSONB;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role, user_id INTO v_role, v_uid
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;

    SELECT jsonb_agg(jsonb_build_object(
        'import_id',   import_id::text,
        'import_type', import_type,
        'filename',    filename,
        'status',      status,
        'pii_scan',    pii_scan,
        'format_scan', format_scan,
        'malware_scan',malware_scan,
        'created_at',  created_at,
        'decided_at',  decided_at,
        'decision_note', decision_note
    ) ORDER BY created_at DESC) INTO v_rows
    FROM security.data_import_requests
    WHERE tenant_id = p_tenant
      AND (p_status IS NULL OR status = p_status)
      AND (v_role IN ('PADMIN','TADMIN') OR requester_id = v_uid)
    LIMIT p_limit;

    RETURN jsonb_build_object('items', COALESCE(v_rows, '[]'::jsonb));
END;
$$;

COMMENT ON TABLE security.data_import_requests IS 'DP-17: Data import approval ledger with auto-scan and SOD-enforced human decision.';
