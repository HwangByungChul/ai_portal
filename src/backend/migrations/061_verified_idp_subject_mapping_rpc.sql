-- Server-only self-service mapping contract for a future verified OIDC/SAML verifier.
-- No policy head or assurance evidence is seeded by this migration; calls fail closed.

ALTER TABLE security.session_assurance_evidence
    ADD COLUMN subject_digest_key_version smallint
        CHECK (subject_digest_key_version IS NULL OR subject_digest_key_version > 0);

ALTER TABLE security.idp_subject_account_mapping_events
    ADD COLUMN evidence_id uuid NOT NULL
        REFERENCES security.session_assurance_evidence(evidence_id),
    ADD COLUMN client_request_id uuid NOT NULL,
    ADD COLUMN expected_mapping_revision bigint NOT NULL CHECK (expected_mapping_revision >= 0);
CREATE UNIQUE INDEX idp_subject_mapping_request_once
    ON security.idp_subject_account_mapping_events(tenant_id, actor_id, client_request_id);
CREATE INDEX idp_subject_mapping_latest
    ON security.idp_subject_account_mapping_events
       (tenant_id, protocol, issuer, subject_digest, digest_key_version, mapping_revision DESC);

-- A missing head means disabled. Enabling this later requires a separately reviewed
-- policy administration operation and a real verifier implementation.
CREATE TABLE security.idp_assurance_policy_heads (
    tenant_id uuid PRIMARY KEY REFERENCES security.tenants(tenant_id),
    policy_revision bigint NOT NULL,
    enabled boolean NOT NULL DEFAULT false CHECK (enabled = false),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (tenant_id, policy_revision)
        REFERENCES security.idp_assurance_policy_revisions(tenant_id, policy_revision)
);
ALTER TABLE security.idp_assurance_policy_heads OWNER TO ai_policy_executor;
ALTER TABLE security.idp_assurance_policy_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE security.idp_assurance_policy_heads FORCE ROW LEVEL SECURITY;
REVOKE ALL ON security.idp_assurance_policy_heads FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT ON security.idp_assurance_policy_heads TO ai_policy_executor;
CREATE POLICY idp_assurance_policy_head_read
    ON security.idp_assurance_policy_heads FOR SELECT TO ai_policy_executor
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND security.can_read_agent(tenant_id));

-- The self policies are deliberately narrow; raw table DML remains unavailable to ai_web.
CREATE POLICY session_assurance_self_read
    ON security.session_assurance_evidence FOR SELECT TO ai_policy_executor
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
           AND session_id = NULLIF(current_setting('app.session_id', true), '')::uuid
           AND security.can_read_agent(tenant_id));
CREATE POLICY session_assurance_self_insert
    ON security.session_assurance_evidence FOR INSERT TO ai_policy_executor
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                AND session_id = NULLIF(current_setting('app.session_id', true), '')::uuid
                AND security.can_read_agent(tenant_id));
CREATE POLICY idp_subject_mapping_self_scope
    ON security.idp_subject_account_mapping_events TO ai_policy_executor
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND actor_id = NULLIF(current_setting('app.user_id', true), '')::uuid
           AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
           AND security.can_read_agent(tenant_id))
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND actor_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                AND security.can_read_agent(tenant_id));

CREATE POLICY audit_idp_subject_mapping ON ops.audit_events FOR INSERT TO ai_policy_executor
WITH CHECK (session_user = 'ai_web' AND scope_kind = 'tenant'
    AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    AND actor_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    AND action IN ('security.idp_subject_mapping.linked', 'security.idp_subject_mapping.revoked')
    AND result = 'success' AND security.can_read_agent(tenant_id));
GRANT INSERT ON ops.audit_events TO ai_policy_executor;

CREATE FUNCTION security.idp_subject_mapping_control(
    p_session uuid,
    p_tenant uuid,
    p_action text,
    p_evidence_id uuid,
    p_client_request_id uuid,
    p_expected_mapping_revision bigint
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, security, ops, pg_temp
AS $function$
DECLARE
    v_user uuid;
    v_protocol text;
    v_evidence security.session_assurance_evidence%ROWTYPE;
    v_latest security.idp_subject_account_mapping_events%ROWTYPE;
    v_replay security.idp_subject_account_mapping_events%ROWTYPE;
    v_revision bigint;
    v_event uuid;
    v_lock_key bigint;
BEGIN
    IF session_user <> 'ai_web' THEN
        RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE = '42501';
    END IF;
    IF p_action IS NULL OR p_action NOT IN ('link', 'revoke') OR p_evidence_id IS NULL
       OR p_client_request_id IS NULL OR p_expected_mapping_revision IS NULL
       OR p_expected_mapping_revision < 0 THEN
        RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE = 'A0422';
    END IF;

    v_user := security.operations_authorize(p_session, p_tenant, 'agents', true);

    -- Idempotent retry returns only the outcome of the same operation/evidence.
    SELECT * INTO v_replay FROM security.idp_subject_account_mapping_events
     WHERE tenant_id = p_tenant AND actor_id = v_user
       AND client_request_id = p_client_request_id;
    IF FOUND THEN
        IF v_replay.action <> (CASE p_action WHEN 'link' THEN 'map' ELSE 'revoke' END)
           OR v_replay.evidence_id <> p_evidence_id
           OR v_replay.expected_mapping_revision <> p_expected_mapping_revision THEN
            RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE = 'A0409';
        END IF;
        RETURN jsonb_build_object('status', 'recorded', 'replayed', true,
            'mapping_event_id', v_replay.mapping_event_id,
            'mapping_revision', v_replay.mapping_revision,
            'action', v_replay.action);
    END IF;

    SELECT e.* INTO v_evidence
      FROM security.session_assurance_evidence e
      JOIN security.idp_assurance_policy_revisions p
        ON p.tenant_id = e.tenant_id AND p.policy_revision = e.policy_revision
      JOIN security.idp_assurance_policy_heads h
        ON h.tenant_id = p.tenant_id AND h.policy_revision = p.policy_revision AND h.enabled
     WHERE e.evidence_id = p_evidence_id AND e.tenant_id = p_tenant
       AND e.session_id = p_session AND e.user_id = v_user
       AND e.issuer = p.issuer AND e.verifier_policy_digest = p.policy_digest
       AND e.subject_digest_key_version IS NOT NULL
       AND e.assurance_level IN ('aal2', 'aal3')
       AND clock_timestamp() < e.expires_at
       AND clock_timestamp() < e.authenticated_at + make_interval(secs => p.max_auth_age_seconds)
       AND e.expires_at <= e.authenticated_at + make_interval(secs => p.max_auth_age_seconds);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'VERIFIED_ASSURANCE_REQUIRED' USING ERRCODE = 'A0403';
    END IF;
    SELECT p.protocol INTO v_protocol
      FROM security.idp_assurance_policy_revisions p
     WHERE p.tenant_id = v_evidence.tenant_id
       AND p.policy_revision = v_evidence.policy_revision;

    v_lock_key := hashtextextended(p_tenant::text || ':' || v_protocol || ':' ||
        v_evidence.issuer || ':' || encode(v_evidence.subject_digest, 'hex') || ':' ||
        v_evidence.subject_digest_key_version::text, 0);
    PERFORM pg_advisory_xact_lock(v_lock_key);

    SELECT * INTO v_latest FROM security.idp_subject_account_mapping_events
     WHERE tenant_id = p_tenant AND protocol = v_protocol
       AND issuer = v_evidence.issuer AND subject_digest = v_evidence.subject_digest
       AND digest_key_version = v_evidence.subject_digest_key_version
     ORDER BY mapping_revision DESC LIMIT 1;
    v_revision := COALESCE(v_latest.mapping_revision, 0);
    IF v_revision <> p_expected_mapping_revision THEN
        RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE = 'A0409';
    END IF;
    IF p_action = 'link' AND v_latest.action = 'map' THEN
        RAISE EXCEPTION 'MAPPING_ALREADY_ACTIVE' USING ERRCODE = 'A0409';
    ELSIF p_action = 'revoke' AND (v_latest.mapping_event_id IS NULL
            OR v_latest.action <> 'map' OR v_latest.user_id <> v_user) THEN
        RAISE EXCEPTION 'MAPPING_NOT_FOUND' USING ERRCODE = 'A0404';
    END IF;

    v_event := gen_random_uuid();
    INSERT INTO security.idp_subject_account_mapping_events(
        tenant_id, mapping_event_id, protocol, issuer, subject_digest,
        digest_key_version, user_id, mapping_revision, action, actor_id,
        evidence_id, client_request_id, expected_mapping_revision
    ) VALUES (
        p_tenant, v_event, v_protocol, v_evidence.issuer,
        v_evidence.subject_digest, v_evidence.subject_digest_key_version,
        v_user, v_revision + 1, CASE p_action WHEN 'link' THEN 'map' ELSE 'revoke' END,
        v_user, p_evidence_id, p_client_request_id, v_revision
    );

    INSERT INTO ops.audit_events(event_id, scope_kind, tenant_id, actor_id, action,
        opaque_target_id, result, safe_reason, revisions)
    VALUES (gen_random_uuid(), 'tenant', p_tenant, v_user,
        CASE p_action WHEN 'link' THEN 'security.idp_subject_mapping.linked'
                      ELSE 'security.idp_subject_mapping.revoked' END,
        v_event, 'success', 'server_verified_step_up',
        jsonb_build_object('mapping_revision', v_revision + 1,
                           'policy_revision', v_evidence.policy_revision));

    RETURN jsonb_build_object('status', 'recorded', 'replayed', false,
        'mapping_event_id', v_event, 'mapping_revision', v_revision + 1,
        'action', CASE p_action WHEN 'link' THEN 'map' ELSE 'revoke' END);
END;
$function$;
ALTER FUNCTION security.idp_subject_mapping_control(uuid, uuid, text, uuid, uuid, bigint)
    OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.idp_subject_mapping_control(uuid, uuid, text, uuid, uuid, bigint)
    FROM PUBLIC, ai_index, ai_meter, ai_policy_executor;
GRANT EXECUTE ON FUNCTION security.idp_subject_mapping_control(uuid, uuid, text, uuid, uuid, bigint)
    TO ai_web;
