CREATE SCHEMA security AUTHORIZATION ai_policy_executor;
CREATE SCHEMA portal AUTHORIZATION ai_owner;
CREATE SCHEMA ops AUTHORIZATION ai_owner;
CREATE TABLE security.accounts (
 user_id uuid PRIMARY KEY, login_id text UNIQUE NOT NULL,
 display_name text NOT NULL, password_hash text NOT NULL, active boolean NOT NULL,
 auth_revision bigint NOT NULL DEFAULT 1 CHECK(auth_revision>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(login_id ~ '^[a-z0-9._-]{3,64}$')
);
CREATE TABLE security.tenants (
 tenant_id uuid PRIMARY KEY, fixture_label text UNIQUE NOT NULL,
 display_name text NOT NULL, active boolean NOT NULL DEFAULT true,
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0)
);
CREATE TABLE security.memberships (
 tenant_id uuid REFERENCES security.tenants, user_id uuid REFERENCES security.accounts,
 membership_id uuid UNIQUE NOT NULL, role text NOT NULL CHECK(role IN ('USER','TADMIN')),
 active boolean NOT NULL DEFAULT true, revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 PRIMARY KEY(tenant_id,user_id)
);
CREATE TABLE security.platform_access (
 user_id uuid PRIMARY KEY REFERENCES security.accounts,
 is_padmin boolean NOT NULL, permissions text[] NOT NULL DEFAULT '{}',
 active boolean NOT NULL DEFAULT true, revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 CHECK(permissions <@ ARRAY['global_usage_read','global_stop_write']::text[])
);
CREATE TABLE security.managed_tenants (
 tenant_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES security.platform_access,
 active boolean NOT NULL DEFAULT true, revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 PRIMARY KEY(tenant_id,user_id),
 FOREIGN KEY(tenant_id,user_id) REFERENCES security.memberships(tenant_id,user_id)
);
CREATE TABLE security.sessions (
 session_id uuid PRIMARY KEY, token_hash bytea UNIQUE NOT NULL CHECK(octet_length(token_hash)=32),
 user_id uuid NOT NULL REFERENCES security.accounts, auth_revision bigint NOT NULL CHECK(auth_revision>0),
 csrf_secret text NOT NULL, issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 last_activity_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL, revoked_at timestamptz,
 CHECK(expires_at=issued_at+interval '8 hours'), CHECK(last_activity_at>=issued_at)
);
CREATE TABLE security.login_windows (
 purpose text NOT NULL CHECK(purpose IN ('login_input','login_ip','run_admission','document_admission','http_read')),
 key_kind text NOT NULL CHECK(key_kind IN ('login','ip','principal')),
 key_digest bytea NOT NULL CHECK(octet_length(key_digest)=32),
 window_started_at timestamptz NOT NULL, count integer NOT NULL CHECK(count>=0),
 PRIMARY KEY(purpose,key_kind,key_digest)
);
CREATE TABLE portal.agent_configs (
 tenant_id uuid NOT NULL REFERENCES security.tenants,
 agent_key text NOT NULL CHECK(agent_key IN ('general','rules_rag')),
 config_version bigint NOT NULL DEFAULT 1 CHECK(config_version>0),
 enabled boolean NOT NULL, settings jsonb NOT NULL DEFAULT '{}',
 updated_by uuid NOT NULL, updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,agent_key),
 FOREIGN KEY(tenant_id,updated_by) REFERENCES security.memberships(tenant_id,user_id)
);
CREATE TABLE portal.conversations (
 tenant_id uuid NOT NULL, conversation_id uuid NOT NULL, owner_user_id uuid NOT NULL,
 agent_key text NOT NULL, client_conversation_id uuid,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,conversation_id),
 UNIQUE(tenant_id,conversation_id,owner_user_id,agent_key),
 UNIQUE(tenant_id,owner_user_id,client_conversation_id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES security.memberships(tenant_id,user_id),
 FOREIGN KEY(tenant_id,agent_key) REFERENCES portal.agent_configs(tenant_id,agent_key)
);
CREATE TABLE ops.project_budget (
 budget_id uuid PRIMARY KEY, period date NOT NULL, mode text NOT NULL CHECK(mode IN ('mock','real')),
 approved_cap_krw numeric(18,6) NOT NULL CHECK(approved_cap_krw>=0),
 operational_cap_krw numeric(18,6) NOT NULL CHECK(operational_cap_krw BETWEEN 0 AND approved_cap_krw),
 reserved_krw numeric(18,6) NOT NULL DEFAULT 0 CHECK(reserved_krw>=0),
 accounted_krw numeric(18,6) NOT NULL DEFAULT 0 CHECK(accounted_krw>=0),
 active_slot integer NOT NULL DEFAULT 0 CHECK(active_slot>=0),
 stopped boolean NOT NULL DEFAULT false, stop_latch boolean NOT NULL DEFAULT false,
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), UNIQUE(period,mode)
);
CREATE TABLE ops.audit_events (
 event_id uuid PRIMARY KEY, scope_kind text NOT NULL CHECK(scope_kind IN ('tenant','platform','auth')),
 tenant_id uuid REFERENCES security.tenants, actor_id uuid REFERENCES security.accounts,
 action text NOT NULL, opaque_target_id uuid, result text NOT NULL,
 safe_reason text, revisions jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((scope_kind='tenant' AND tenant_id IS NOT NULL) OR
       (scope_kind IN ('platform','auth') AND tenant_id IS NULL))
);
ALTER TABLE security.accounts OWNER TO ai_policy_executor;
ALTER TABLE security.tenants OWNER TO ai_policy_executor;
ALTER TABLE security.memberships OWNER TO ai_policy_executor;
ALTER TABLE security.platform_access OWNER TO ai_policy_executor;
ALTER TABLE security.managed_tenants OWNER TO ai_policy_executor;
ALTER TABLE security.sessions OWNER TO ai_policy_executor;
ALTER TABLE security.login_windows OWNER TO ai_policy_executor;
ALTER TABLE portal.agent_configs OWNER TO ai_owner;
ALTER TABLE portal.conversations OWNER TO ai_owner;
ALTER TABLE ops.project_budget OWNER TO ai_owner;
ALTER TABLE ops.audit_events OWNER TO ai_owner;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA security,portal,ops FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER DEFAULT PRIVILEGES FOR ROLE ai_policy_executor IN SCHEMA security REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE mvp_bootstrap IN SCHEMA security REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER TABLE portal.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.agent_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.agent_configs FORCE ROW LEVEL SECURITY;
ALTER TABLE ops.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.audit_events FORCE ROW LEVEL SECURITY;
