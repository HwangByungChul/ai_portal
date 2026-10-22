-- DP-13 Model Registry: Persistent DB-backed model catalogue.
-- Prerequisite: migrations 000-070 applied with checksums intact.
-- credential_ref stores ONLY the environment-variable key name (e.g. OPENAI_API_KEY).
-- Actual secrets MUST NOT be stored in this table.
SET search_path = security, public;

CREATE TABLE IF NOT EXISTS security.model_registry_db (
    model_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        REFERENCES security.tenants(tenant_id) ON DELETE CASCADE,
    provider_key    TEXT        NOT NULL CHECK (provider_key IN ('openai','anthropic','google','mock')),
    model_name      TEXT        NOT NULL,
    display_name    TEXT        NOT NULL CHECK (length(display_name) BETWEEN 1 AND 80),
    context_window  INT         NOT NULL DEFAULT 128000 CHECK (context_window > 0),
    max_output      INT         NOT NULL DEFAULT 4096   CHECK (max_output > 0),
    price_input_usd NUMERIC(14, 8) NOT NULL DEFAULT 0 CHECK (price_input_usd >= 0),
    price_out_usd   NUMERIC(14, 8) NOT NULL DEFAULT 0 CHECK (price_out_usd >= 0),
    credential_ref  TEXT        NOT NULL DEFAULT 'OPENAI_API_KEY',
    active          BOOLEAN     NOT NULL DEFAULT FALSE,
    is_default      BOOLEAN     NOT NULL DEFAULT FALSE,
    capabilities    TEXT[]      NOT NULL DEFAULT ARRAY['chat','streaming'],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at      TIMESTAMPTZ,
    CONSTRAINT model_registry_db_unique_entry UNIQUE (tenant_id, provider_key, model_name)
);

-- Only one active default per tenant
CREATE UNIQUE INDEX IF NOT EXISTS model_registry_db_default_idx
    ON security.model_registry_db (tenant_id)
    WHERE is_default AND active AND retired_at IS NULL;

-- RLS
ALTER TABLE security.model_registry_db ENABLE ROW LEVEL SECURITY;
ALTER TABLE security.model_registry_db FORCE ROW LEVEL SECURITY;

CREATE POLICY model_registry_db_isolation ON security.model_registry_db
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::uuid);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION security.touch_model_registry_db()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS trg_touch_model_registry_db ON security.model_registry_db;
CREATE TRIGGER trg_touch_model_registry_db
    BEFORE UPDATE ON security.model_registry_db
    FOR EACH ROW EXECUTE FUNCTION security.touch_model_registry_db();

-- DP-13: List active models for user selection (public endpoint)
CREATE OR REPLACE FUNCTION security.model_registry_list(
    p_session UUID, p_tenant UUID
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_rows JSONB;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT jsonb_agg(jsonb_build_object(
        'model_id',      model_id::text,
        'provider_key',  provider_key,
        'model_name',    model_name,
        'display_name',  display_name,
        'context_window', context_window,
        'max_output',    max_output,
        'capabilities',  to_jsonb(capabilities),
        'is_default',    is_default
    ) ORDER BY is_default DESC, display_name)
    INTO v_rows
    FROM security.model_registry_db
    WHERE tenant_id = p_tenant
      AND active AND retired_at IS NULL;
    RETURN jsonb_build_object('items', COALESCE(v_rows, '[]'::jsonb));
END;
$$;

-- DP-13: Admin list (all including inactive)
CREATE OR REPLACE FUNCTION security.model_registry_admin_list(
    p_session UUID, p_tenant UUID
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_rows JSONB; v_role TEXT;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role INTO v_role
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role NOT IN ('PADMIN') THEN
        RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403';
    END IF;
    SELECT jsonb_agg(jsonb_build_object(
        'model_id',       model_id::text,
        'provider_key',   provider_key,
        'model_name',     model_name,
        'display_name',   display_name,
        'context_window', context_window,
        'max_output',     max_output,
        'price_input_usd', price_input_usd::text,
        'price_out_usd',   price_out_usd::text,
        'credential_ref',  credential_ref,
        'active',          active,
        'is_default',      is_default,
        'capabilities',    to_jsonb(capabilities),
        'created_at',      created_at,
        'updated_at',      updated_at
    ) ORDER BY active DESC, is_default DESC, display_name)
    INTO v_rows
    FROM security.model_registry_db
    WHERE tenant_id = p_tenant AND retired_at IS NULL;
    RETURN jsonb_build_object('items', COALESCE(v_rows, '[]'::jsonb));
END;
$$;

-- DP-13: Admin upsert model
CREATE OR REPLACE FUNCTION security.model_registry_upsert(
    p_session UUID, p_tenant UUID,
    p_provider_key TEXT, p_model_name TEXT, p_display_name TEXT,
    p_context_window INT, p_max_output INT,
    p_price_input_usd NUMERIC, p_price_out_usd NUMERIC,
    p_credential_ref TEXT, p_capabilities TEXT[]
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT; v_id UUID;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role INTO v_role
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role NOT IN ('PADMIN') THEN
        RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403';
    END IF;
    INSERT INTO security.model_registry_db (
        tenant_id, provider_key, model_name, display_name,
        context_window, max_output, price_input_usd, price_out_usd,
        credential_ref, capabilities
    ) VALUES (
        p_tenant, p_provider_key, p_model_name, p_display_name,
        p_context_window, p_max_output, p_price_input_usd, p_price_out_usd,
        p_credential_ref, p_capabilities
    )
    ON CONFLICT (tenant_id, provider_key, model_name) DO UPDATE SET
        display_name   = EXCLUDED.display_name,
        context_window = EXCLUDED.context_window,
        max_output     = EXCLUDED.max_output,
        price_input_usd = EXCLUDED.price_input_usd,
        price_out_usd  = EXCLUDED.price_out_usd,
        credential_ref = EXCLUDED.credential_ref,
        capabilities   = EXCLUDED.capabilities,
        updated_at     = now()
    RETURNING model_id INTO v_id;
    RETURN jsonb_build_object('model_id', v_id::text);
END;
$$;

-- DP-13: Set active/inactive
CREATE OR REPLACE FUNCTION security.model_registry_set_active(
    p_session UUID, p_tenant UUID, p_model_id UUID, p_active BOOLEAN
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role INTO v_role
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role NOT IN ('PADMIN') THEN
        RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403';
    END IF;
    UPDATE security.model_registry_db
    SET active = p_active, is_default = CASE WHEN NOT p_active THEN FALSE ELSE is_default END
    WHERE model_id = p_model_id AND tenant_id = p_tenant AND retired_at IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'MODEL_NOT_FOUND' USING ERRCODE = 'A0404'; END IF;
    RETURN jsonb_build_object('ok', TRUE);
END;
$$;

-- DP-13: Set default model (clears existing default first)
CREATE OR REPLACE FUNCTION security.model_registry_set_default(
    p_session UUID, p_tenant UUID, p_model_id UUID
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, portal, ops, pg_temp AS $$
DECLARE v_role TEXT; v_active BOOLEAN;
BEGIN
    PERFORM security.require_active_session(p_session, p_tenant);
    SELECT effective_role INTO v_role
    FROM security.active_sessions WHERE session_id = p_session AND tenant_id = p_tenant;
    IF v_role NOT IN ('PADMIN') THEN
        RAISE EXCEPTION 'REQUEST_FORBIDDEN' USING ERRCODE = 'A0403';
    END IF;
    SELECT active INTO v_active FROM security.model_registry_db
    WHERE model_id = p_model_id AND tenant_id = p_tenant AND retired_at IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'MODEL_NOT_FOUND' USING ERRCODE = 'A0404'; END IF;
    IF NOT v_active THEN RAISE EXCEPTION 'MODEL_NOT_ACTIVE' USING ERRCODE = 'A0422'; END IF;
    -- Clear existing default first to avoid unique constraint conflict
    UPDATE security.model_registry_db SET is_default = FALSE
    WHERE tenant_id = p_tenant AND is_default AND retired_at IS NULL;
    UPDATE security.model_registry_db SET is_default = TRUE
    WHERE model_id = p_model_id AND tenant_id = p_tenant;
    RETURN jsonb_build_object('ok', TRUE);
END;
$$;

COMMENT ON TABLE security.model_registry_db IS 'DP-13: Persistent LLM model catalogue. credential_ref holds env-var key name only.';
