-- Additive storage contract for future server-verified OIDC/SAML step-up.
-- No issuer policy is enabled and no application path writes these records yet.
-- Existing dynamic MCP approval remains registration-review-only.

CREATE TABLE security.idp_assurance_policy_revisions (
    tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    protocol text NOT NULL CHECK (protocol IN ('oidc', 'saml')),
    issuer text NOT NULL CHECK (length(btrim(issuer)) BETWEEN 1 AND 500),
    client_identifier text NOT NULL CHECK (length(btrim(client_identifier)) BETWEEN 1 AND 300),
    metadata_reference text NOT NULL CHECK (length(btrim(metadata_reference)) BETWEEN 1 AND 300),
    subject_claim text NOT NULL CHECK (length(btrim(subject_claim)) BETWEEN 1 AND 200),
    assurance_claim text NOT NULL CHECK (length(btrim(assurance_claim)) BETWEEN 1 AND 200),
    accepted_assurance_values text[] NOT NULL
        CHECK (cardinality(accepted_assurance_values) BETWEEN 1 AND 20
               AND array_position(accepted_assurance_values, NULL) IS NULL),
    max_auth_age_seconds integer NOT NULL CHECK (max_auth_age_seconds BETWEEN 1 AND 3600),
    policy_digest bytea NOT NULL CHECK (octet_length(policy_digest) = 32),
    created_by uuid NOT NULL REFERENCES security.accounts(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, policy_revision),
    UNIQUE (tenant_id, policy_digest)
);
ALTER TABLE security.idp_assurance_policy_revisions OWNER TO ai_policy_executor;
ALTER TABLE security.idp_assurance_policy_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE security.idp_assurance_policy_revisions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON security.idp_assurance_policy_revisions FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT ON security.idp_assurance_policy_revisions TO ai_policy_executor;
CREATE POLICY idp_assurance_policy_tenant_scope
    ON security.idp_assurance_policy_revisions TO ai_policy_executor
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND security.can_manage_current_tenant(tenant_id))
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND created_by = NULLIF(current_setting('app.user_id', true), '')::uuid
                AND security.can_manage_current_tenant(tenant_id));

CREATE FUNCTION security.idp_assurance_record_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'ASSURANCE_RECORD_IMMUTABLE' USING ERRCODE = '23514';
END;
$$;
ALTER FUNCTION security.idp_assurance_record_immutable() OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.idp_assurance_record_immutable() FROM PUBLIC, ai_web, ai_index, ai_meter;

CREATE TRIGGER idp_assurance_policy_revision_immutable
    BEFORE UPDATE OR DELETE ON security.idp_assurance_policy_revisions
    FOR EACH ROW EXECUTE FUNCTION security.idp_assurance_record_immutable();

CREATE TABLE security.session_assurance_evidence (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    session_id uuid NOT NULL REFERENCES security.sessions(session_id),
    user_id uuid NOT NULL REFERENCES security.accounts(user_id),
    policy_revision bigint NOT NULL,
    issuer text NOT NULL CHECK (length(btrim(issuer)) BETWEEN 1 AND 500),
    subject_digest bytea NOT NULL CHECK (octet_length(subject_digest) = 32),
    assurance_level text NOT NULL CHECK (assurance_level IN ('aal1', 'aal2', 'aal3')),
    authenticated_at timestamptz NOT NULL,
    verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    assertion_digest bytea NOT NULL CHECK (octet_length(assertion_digest) = 32),
    verifier_policy_digest bytea NOT NULL CHECK (octet_length(verifier_policy_digest) = 32),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES security.memberships(tenant_id, user_id),
    FOREIGN KEY (tenant_id, policy_revision)
        REFERENCES security.idp_assurance_policy_revisions(tenant_id, policy_revision),
    CHECK (expires_at > verified_at),
    CHECK (authenticated_at <= verified_at),
    UNIQUE (tenant_id, session_id, assertion_digest)
);
ALTER TABLE security.session_assurance_evidence OWNER TO ai_policy_executor;
ALTER TABLE security.session_assurance_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE security.session_assurance_evidence FORCE ROW LEVEL SECURITY;
REVOKE ALL ON security.session_assurance_evidence FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT ON security.session_assurance_evidence TO ai_policy_executor;
CREATE POLICY session_assurance_tenant_scope
    ON security.session_assurance_evidence TO ai_policy_executor
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND security.can_manage_current_tenant(tenant_id))
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                AND security.can_manage_current_tenant(tenant_id));

CREATE TRIGGER session_assurance_evidence_immutable
    BEFORE UPDATE OR DELETE ON security.session_assurance_evidence
    FOR EACH ROW EXECUTE FUNCTION security.idp_assurance_record_immutable();
