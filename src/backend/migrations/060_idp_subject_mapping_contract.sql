-- Append-only, tenant-scoped subject-to-account mapping history.
-- Raw OIDC sub / SAML NameID values are never stored here.
-- Writes remain unavailable to ai_web until a verified-assertion RPC is added.

CREATE TABLE security.idp_subject_account_mapping_events (
    tenant_id uuid NOT NULL REFERENCES security.tenants(tenant_id),
    mapping_event_id uuid NOT NULL DEFAULT gen_random_uuid(),
    protocol text NOT NULL CHECK (protocol IN ('oidc', 'saml')),
    issuer text NOT NULL CHECK (length(btrim(issuer)) BETWEEN 1 AND 500),
    subject_digest bytea NOT NULL CHECK (octet_length(subject_digest) = 32),
    digest_key_version smallint NOT NULL CHECK (digest_key_version > 0),
    user_id uuid NOT NULL,
    mapping_revision bigint NOT NULL CHECK (mapping_revision > 0),
    action text NOT NULL CHECK (action IN ('map', 'revoke')),
    actor_id uuid NOT NULL REFERENCES security.accounts(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, mapping_event_id),
    UNIQUE (tenant_id, protocol, issuer, subject_digest, digest_key_version, mapping_revision),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES security.memberships(tenant_id, user_id)
);
ALTER TABLE security.idp_subject_account_mapping_events OWNER TO ai_policy_executor;
ALTER TABLE security.idp_subject_account_mapping_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE security.idp_subject_account_mapping_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON security.idp_subject_account_mapping_events FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT ON security.idp_subject_account_mapping_events TO ai_policy_executor;
CREATE POLICY idp_subject_mapping_tenant_scope
    ON security.idp_subject_account_mapping_events TO ai_policy_executor
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND security.can_manage_current_tenant(tenant_id))
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND actor_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                AND security.can_manage_current_tenant(tenant_id));
CREATE TRIGGER idp_subject_mapping_event_immutable
    BEFORE UPDATE OR DELETE ON security.idp_subject_account_mapping_events
    FOR EACH ROW EXECUTE FUNCTION security.idp_assurance_record_immutable();
