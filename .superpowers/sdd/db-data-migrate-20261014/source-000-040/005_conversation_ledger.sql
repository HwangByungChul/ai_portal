-- B01 storage only. Raw runtime mutations remain denied until fixed control functions in B02~04.
ALTER TABLE security.sessions ADD CONSTRAINT sessions_origin_owner UNIQUE(session_id,user_id);
ALTER TABLE ops.project_budget ADD CONSTRAINT project_budget_mode_binding UNIQUE(budget_id,mode);
ALTER TABLE ops.project_budget ADD CONSTRAINT project_budget_finite CHECK(
 approved_cap_krw <> 'NaN'::numeric AND operational_cap_krw <> 'NaN'::numeric
 AND reserved_krw <> 'NaN'::numeric AND accounted_krw <> 'NaN'::numeric);

CREATE TABLE portal.runs (
 tenant_id uuid NOT NULL, run_id uuid NOT NULL, conversation_id uuid NOT NULL,
 owner_user_id uuid NOT NULL, client_send_id uuid NOT NULL, request_hash bytea NOT NULL CHECK(octet_length(request_hash)=32),
 agent_key text NOT NULL CHECK(agent_key='general'), config_snapshot jsonb NOT NULL CHECK(jsonb_typeof(config_snapshot)='object'),
 origin_session_id uuid NOT NULL, execution_mode text NOT NULL CHECK(execution_mode IN ('mock','real')),
 state text NOT NULL DEFAULT 'accepted' CHECK(state IN ('accepted','running','cancel_requested','completed','failed','cancelled','blocked','interrupted')),
 stage text NOT NULL DEFAULT 'queued' CHECK(stage IN ('queued','authorization','retrieval','generation','finalizing','terminal')),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), execution_epoch bigint NOT NULL DEFAULT 1 CHECK(execution_epoch>0),
 heartbeat_at timestamptz, lease_expires_at timestamptz, started_at timestamptz, ended_at timestamptz,
 cancel_requested_at timestamptz, safe_error_code text CHECK(safe_error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
 answer_kind text CHECK(answer_kind IN ('answer','insufficient_evidence')),
 source_count integer NOT NULL DEFAULT 0 CHECK(source_count=0), provenance_sealed boolean NOT NULL DEFAULT false CHECK(NOT provenance_sealed),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,run_id), UNIQUE(tenant_id,owner_user_id,client_send_id),
 UNIQUE(tenant_id,run_id,conversation_id,owner_user_id,agent_key),
 UNIQUE(tenant_id,run_id,owner_user_id,execution_mode,agent_key),
 FOREIGN KEY(tenant_id,conversation_id,owner_user_id,agent_key)
  REFERENCES portal.conversations(tenant_id,conversation_id,owner_user_id,agent_key),
 FOREIGN KEY(origin_session_id,owner_user_id) REFERENCES security.sessions(session_id,user_id),
 CHECK((state IN ('completed','failed','cancelled','blocked','interrupted')) = (ended_at IS NOT NULL)),
 CHECK((stage='terminal') = (state IN ('completed','failed','cancelled','blocked','interrupted'))),
 CHECK(answer_kind IS NULL OR (state='completed' AND answer_kind='answer')),
 CHECK(state<>'completed' OR answer_kind IS NOT NULL),
 CHECK(lease_expires_at IS NULL OR heartbeat_at IS NOT NULL)
);
CREATE INDEX runs_owner_time ON portal.runs(tenant_id,owner_user_id,created_at,run_id);
CREATE INDEX runs_active_lease ON portal.runs(lease_expires_at) WHERE state IN ('accepted','running','cancel_requested');

CREATE TABLE portal.messages (
 tenant_id uuid NOT NULL, message_id uuid NOT NULL, conversation_id uuid NOT NULL, owner_user_id uuid NOT NULL,
 agent_key text NOT NULL CHECK(agent_key='general'), sequence_no bigint NOT NULL CHECK(sequence_no>0),
 role text NOT NULL CHECK(role IN ('user','assistant')), body text, run_id uuid NOT NULL,
 payload_kind text NOT NULL CHECK(payload_kind IN ('user','general_assistant')),
 payload_purged boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,message_id), UNIQUE(tenant_id,conversation_id,sequence_no),
 FOREIGN KEY(tenant_id,run_id,conversation_id,owner_user_id,agent_key)
  REFERENCES portal.runs(tenant_id,run_id,conversation_id,owner_user_id,agent_key),
 CHECK((role='user' AND payload_kind='user') OR (role='assistant' AND payload_kind='general_assistant')),
 CHECK(payload_purged=(body IS NULL)), CHECK(body IS NULL OR btrim(body)<>''),
 CHECK(body IS NULL OR (role='user' AND char_length(body)<=4000 AND octet_length(body)<=16384)
                     OR (role='assistant' AND octet_length(body)<=65536))
);

CREATE TABLE ops.tenant_budgets (
 tenant_id uuid NOT NULL REFERENCES security.tenants, budget_id uuid NOT NULL REFERENCES ops.project_budget,
 allocated_cap_krw numeric(18,6) NOT NULL, local_cap_krw numeric(18,6) NOT NULL,
 reserved_krw numeric(18,6) NOT NULL DEFAULT 0, accounted_krw numeric(18,6) NOT NULL DEFAULT 0,
 active_slot integer NOT NULL DEFAULT 0 CHECK(active_slot>=0), stopped boolean NOT NULL DEFAULT false,
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), PRIMARY KEY(tenant_id,budget_id),
 CHECK(allocated_cap_krw<>'NaN'::numeric AND allocated_cap_krw>=0),
 CHECK(local_cap_krw<>'NaN'::numeric AND local_cap_krw BETWEEN 0 AND allocated_cap_krw),
 CHECK(reserved_krw<>'NaN'::numeric AND reserved_krw>=0), CHECK(accounted_krw<>'NaN'::numeric AND accounted_krw>=0)
);

CREATE FUNCTION ops.valid_token_counts(value jsonb) RETURNS boolean
 LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $body$
 SELECT CASE WHEN jsonb_typeof(value)='object'
  AND value ?& ARRAY['input_tokens','output_tokens','total_tokens']::text[]
  AND value - ARRAY['input_tokens','output_tokens','total_tokens']::text[]='{}'::jsonb
  AND jsonb_typeof(value->'input_tokens')='number' AND jsonb_typeof(value->'output_tokens')='number'
  AND jsonb_typeof(value->'total_tokens')='number'
  AND value->>'input_tokens' ~ '^[0-9]{1,19}$' AND value->>'output_tokens' ~ '^[0-9]{1,19}$'
  AND value->>'total_tokens' ~ '^[0-9]{1,19}$'
 THEN (value->>'input_tokens')::numeric + (value->>'output_tokens')::numeric = (value->>'total_tokens')::numeric
  AND (value->>'total_tokens')::numeric<=9223372036854775807
 ELSE false END;
$body$;
ALTER FUNCTION ops.valid_token_counts(jsonb) OWNER TO ai_owner;
REVOKE ALL ON FUNCTION ops.valid_token_counts(jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;

CREATE TABLE ops.call_attempts (
 tenant_id uuid NOT NULL, call_id uuid NOT NULL, run_id uuid NOT NULL, job_id uuid CHECK(job_id IS NULL),
 initiator_user_id uuid NOT NULL, operation text NOT NULL CHECK(operation='generate_general'),
 budget_id uuid NOT NULL, mode text NOT NULL CHECK(mode IN ('mock','real')), agent_key text NOT NULL CHECK(agent_key='general'),
 config_revision bigint NOT NULL CHECK(config_revision>0), step_key text NOT NULL CHECK(step_key='generation'),
 attempt_no integer NOT NULL DEFAULT 1 CHECK(attempt_no=1), input_fingerprint bytea NOT NULL CHECK(octet_length(input_fingerprint)=32),
 permit_revision bigint NOT NULL CHECK(permit_revision>0), permit_expires_at timestamptz NOT NULL,
 execution_epoch bigint NOT NULL DEFAULT 1 CHECK(execution_epoch>0), dispatch_claim_hash bytea CHECK(octet_length(dispatch_claim_hash)=32),
 dispatched_at timestamptz, provider_request_id text CHECK(provider_request_id ~ '^[!-~]{1,256}$'),
 provider_end_status text NOT NULL DEFAULT 'not_started' CHECK(provider_end_status IN ('not_started','observed','unknown')),
 reserved_krw numeric(18,6) NOT NULL CHECK(reserved_krw<>'NaN'::numeric AND reserved_krw>=0),
 state text NOT NULL DEFAULT 'reserved' CHECK(state IN ('reserved','dispatched','usage_unknown','settled','released_no_dispatch')),
 slot_held boolean NOT NULL DEFAULT true, cost_overrun boolean NOT NULL DEFAULT false,
 usage_snapshot jsonb, price_snapshot jsonb NOT NULL CHECK(price_snapshot='{"embedding_model": "text-embedding-3-small", "embedding_usd_per_million": "0.02", "generation_model": "gpt-4o-mini", "input_usd_per_million": "0.15", "krw_per_usd": "2000", "output_usd_per_million": "0.60", "protection_factor": "1.2", "quantum_krw": "0.01", "version": "price-20261004-v1"}'::jsonb),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(tenant_id,call_id),
 UNIQUE(tenant_id,run_id,operation,step_key), UNIQUE(tenant_id,call_id,price_snapshot),
 FOREIGN KEY(tenant_id,run_id,initiator_user_id,mode,agent_key)
  REFERENCES portal.runs(tenant_id,run_id,owner_user_id,execution_mode,agent_key),
 FOREIGN KEY(tenant_id,budget_id) REFERENCES ops.tenant_budgets(tenant_id,budget_id),
 FOREIGN KEY(budget_id,mode) REFERENCES ops.project_budget(budget_id,mode),
 CHECK((dispatched_at IS NULL)=(dispatch_claim_hash IS NULL)),
 CHECK((state IN ('reserved','released_no_dispatch'))=(dispatched_at IS NULL)),
 CHECK((provider_end_status='not_started')=(dispatched_at IS NULL)),
 CHECK(state<>'reserved' OR slot_held), CHECK(state<>'released_no_dispatch' OR NOT slot_held),
 CHECK(usage_snapshot IS NULL OR (jsonb_typeof(usage_snapshot)='object'
  AND usage_snapshot - ARRAY['input_tokens','output_tokens','total_tokens','observed_model','observed_tier','provider_request_id']::text[]='{}'::jsonb
  AND ops.valid_token_counts(usage_snapshot - ARRAY['observed_model','observed_tier','provider_request_id']::text[])
  AND usage_snapshot ?& ARRAY['observed_model','observed_tier']::text[]
  AND usage_snapshot->>'observed_model' IN ('gpt-4o-mini','gpt-4o-mini-2024-07-18')
  AND usage_snapshot->>'observed_tier'='default'
  AND (NOT usage_snapshot ? 'provider_request_id' OR usage_snapshot->'provider_request_id'='null'::jsonb
       OR (jsonb_typeof(usage_snapshot->'provider_request_id')='string' AND usage_snapshot->>'provider_request_id' ~ '^[!-~]{1,256}$'))))
);

CREATE TABLE ops.usage_events (
 tenant_id uuid NOT NULL, event_id uuid NOT NULL, call_id uuid NOT NULL,
 event_kind text NOT NULL CHECK(event_kind IN ('reserve','mark_unknown','settle','release')),
 delta_reserved_krw numeric(18,6) NOT NULL, delta_accounted_krw numeric(18,6) NOT NULL,
 token_counts jsonb, price_snapshot jsonb NOT NULL CHECK(price_snapshot='{"embedding_model": "text-embedding-3-small", "embedding_usd_per_million": "0.02", "generation_model": "gpt-4o-mini", "input_usd_per_million": "0.15", "krw_per_usd": "2000", "output_usd_per_million": "0.60", "protection_factor": "1.2", "quantum_krw": "0.01", "version": "price-20261004-v1"}'::jsonb),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(tenant_id,event_id),
 UNIQUE(tenant_id,call_id,event_kind),
 FOREIGN KEY(tenant_id,call_id,price_snapshot) REFERENCES ops.call_attempts(tenant_id,call_id,price_snapshot),
 CHECK(delta_reserved_krw<>'NaN'::numeric AND delta_accounted_krw<>'NaN'::numeric AND delta_accounted_krw>=0),
 CHECK((event_kind='reserve' AND delta_reserved_krw>=0 AND delta_accounted_krw=0)
  OR (event_kind='mark_unknown' AND delta_reserved_krw=0 AND delta_accounted_krw=0)
  OR (event_kind='release' AND delta_reserved_krw<=0 AND delta_accounted_krw=0)
  OR (event_kind='settle' AND delta_reserved_krw<=0)),
 CHECK(token_counts IS NULL OR ops.valid_token_counts(token_counts))
);

CREATE UNIQUE INDEX usage_terminal_once ON ops.usage_events(tenant_id,call_id) WHERE event_kind IN ('settle','release');

CREATE FUNCTION portal.run_binding_immutable() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog AS $body$
BEGIN
 IF (NEW.tenant_id,NEW.run_id,NEW.conversation_id,NEW.owner_user_id,NEW.client_send_id,NEW.request_hash,
     NEW.agent_key,NEW.config_snapshot,NEW.origin_session_id,NEW.execution_mode,NEW.created_at)
 IS DISTINCT FROM (OLD.tenant_id,OLD.run_id,OLD.conversation_id,OLD.owner_user_id,OLD.client_send_id,OLD.request_hash,
     OLD.agent_key,OLD.config_snapshot,OLD.origin_session_id,OLD.execution_mode,OLD.created_at)
 THEN RAISE EXCEPTION 'RUN_BINDING_IMMUTABLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $body$;
CREATE TRIGGER run_binding_immutable BEFORE UPDATE ON portal.runs FOR EACH ROW EXECUTE FUNCTION portal.run_binding_immutable();

CREATE FUNCTION portal.message_binding_immutable() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog AS $body$
BEGIN
 IF (NEW.tenant_id,NEW.message_id,NEW.conversation_id,NEW.owner_user_id,NEW.agent_key,NEW.run_id,
     NEW.sequence_no,NEW.role,NEW.payload_kind,NEW.created_at)
 IS DISTINCT FROM (OLD.tenant_id,OLD.message_id,OLD.conversation_id,OLD.owner_user_id,OLD.agent_key,OLD.run_id,
     OLD.sequence_no,OLD.role,OLD.payload_kind,OLD.created_at)
 THEN RAISE EXCEPTION 'MESSAGE_BINDING_IMMUTABLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $body$;
CREATE TRIGGER message_binding_immutable BEFORE UPDATE ON portal.messages FOR EACH ROW EXECUTE FUNCTION portal.message_binding_immutable();

CREATE FUNCTION ops.call_binding_immutable() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog AS $body$
BEGIN
 IF (NEW.tenant_id,NEW.call_id,NEW.run_id,NEW.job_id,NEW.initiator_user_id,NEW.operation,NEW.budget_id,NEW.mode,
     NEW.agent_key,NEW.config_revision,NEW.step_key,NEW.attempt_no,NEW.input_fingerprint,NEW.permit_revision,
     NEW.permit_expires_at,NEW.execution_epoch,NEW.reserved_krw,NEW.price_snapshot,NEW.created_at)
 IS DISTINCT FROM (OLD.tenant_id,OLD.call_id,OLD.run_id,OLD.job_id,OLD.initiator_user_id,OLD.operation,OLD.budget_id,OLD.mode,
     OLD.agent_key,OLD.config_revision,OLD.step_key,OLD.attempt_no,OLD.input_fingerprint,OLD.permit_revision,
     OLD.permit_expires_at,OLD.execution_epoch,OLD.reserved_krw,OLD.price_snapshot,OLD.created_at)
 THEN RAISE EXCEPTION 'CALL_BINDING_IMMUTABLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $body$;
CREATE TRIGGER call_binding_immutable BEFORE UPDATE ON ops.call_attempts FOR EACH ROW EXECUTE FUNCTION ops.call_binding_immutable();
CREATE FUNCTION ops.usage_append_only() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog AS $body$
BEGIN RAISE EXCEPTION 'USAGE_APPEND_ONLY' USING ERRCODE='23514'; END; $body$;
CREATE TRIGGER usage_append_only BEFORE UPDATE OR DELETE ON ops.usage_events FOR EACH ROW EXECUTE FUNCTION ops.usage_append_only();

ALTER FUNCTION portal.run_binding_immutable() OWNER TO ai_owner;
ALTER FUNCTION portal.message_binding_immutable() OWNER TO ai_owner;
ALTER FUNCTION ops.call_binding_immutable() OWNER TO ai_owner;
ALTER FUNCTION ops.usage_append_only() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION portal.run_binding_immutable(),portal.message_binding_immutable(),ops.call_binding_immutable(),ops.usage_append_only()
 FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE portal.runs OWNER TO ai_owner;
ALTER TABLE portal.messages OWNER TO ai_owner;
ALTER TABLE ops.tenant_budgets OWNER TO ai_owner;
ALTER TABLE ops.call_attempts OWNER TO ai_owner;
ALTER TABLE ops.usage_events OWNER TO ai_owner;
ALTER TABLE portal.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.runs FORCE ROW LEVEL SECURITY;
ALTER TABLE portal.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.messages FORCE ROW LEVEL SECURITY;
ALTER TABLE ops.tenant_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.tenant_budgets FORCE ROW LEVEL SECURITY;
ALTER TABLE ops.call_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.call_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE ops.usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.usage_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.runs,portal.messages,ops.tenant_budgets,ops.call_attempts,ops.usage_events
 FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
GRANT USAGE ON SCHEMA ops TO ai_meter;
GRANT SELECT(tenant_id,run_id,conversation_id,owner_user_id,agent_key,execution_mode,state,stage,revision,
 execution_epoch,started_at,ended_at,cancel_requested_at,safe_error_code,answer_kind,source_count,provenance_sealed,created_at)
 ON portal.runs TO ai_web;
GRANT SELECT ON portal.messages TO ai_web;
CREATE POLICY run_owner_read ON portal.runs FOR SELECT TO ai_web
 USING(security.can_read_own_conversation(tenant_id,owner_user_id));
CREATE POLICY message_owner_read ON portal.messages FOR SELECT TO ai_web
 USING(security.can_read_own_conversation(tenant_id,owner_user_id) AND NOT payload_purged AND
  (role='user' OR EXISTS(SELECT 1 FROM portal.runs r WHERE r.tenant_id=messages.tenant_id
    AND r.run_id=messages.run_id AND r.state='completed' AND r.answer_kind='answer')));
-- No broad INSERT/UPDATE policies or ledger grants. B02~04 add only narrowly reviewed fixed functions.
