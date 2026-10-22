-- Owner-scoped storage and idempotent admission for private Builder proposals.
-- Provider dispatch is intentionally not wired until a non-conversation
-- capability is added to the shared AI call ledger.
CREATE TABLE portal.builder_scaffold_proposals (
 tenant_id uuid NOT NULL,
 proposal_id uuid NOT NULL DEFAULT gen_random_uuid(),
 owner_user_id uuid NOT NULL,
 client_request_id uuid NOT NULL,
 request_hash bytea NOT NULL CHECK(octet_length(request_hash)=32),
 target text NOT NULL CHECK(target IN ('agent','workflow')),
 request_payload jsonb NOT NULL CHECK(jsonb_typeof(request_payload)='object'),
 proposal_payload jsonb CHECK(proposal_payload IS NULL OR jsonb_typeof(proposal_payload)='object'),
 state text NOT NULL DEFAULT 'admitted' CHECK(state IN ('admitted','ready','failed','discarded')),
 safe_error_code text CHECK(safe_error_code IS NULL OR safe_error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
 model_id text NOT NULL CHECK(model_id ~ '^[a-z0-9][a-z0-9._-]{0,63}$'),
 policy_revision text NOT NULL CHECK(policy_revision ~ '^[A-Za-z0-9._-]{1,64}$'),
 budget_period date NOT NULL CHECK(extract(day FROM budget_period)=1),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 PRIMARY KEY(tenant_id,proposal_id),
 UNIQUE(tenant_id,owner_user_id,client_request_id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES security.memberships(tenant_id,user_id),
 CHECK((state='ready')=(proposal_payload IS NOT NULL)),
 CHECK(state NOT IN ('failed','discarded') OR proposal_payload IS NULL),
 CHECK(state<>'failed' OR safe_error_code IS NOT NULL),
 CHECK(state NOT IN ('admitted','ready') OR safe_error_code IS NULL)
);
ALTER TABLE portal.builder_scaffold_proposals OWNER TO ai_owner;
ALTER TABLE portal.builder_scaffold_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.builder_scaffold_proposals FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.builder_scaffold_proposals FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT SELECT,INSERT,UPDATE ON portal.builder_scaffold_proposals TO ai_policy_executor;
CREATE POLICY builder_scaffold_owner ON portal.builder_scaffold_proposals TO ai_policy_executor
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin'
 AND security.can_read_own_conversation(tenant_id,owner_user_id))
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid
 AND owner_user_id=nullif(current_setting('app.user_id',true),'')::uuid
 AND current_setting('app.operations_scope',true)='agent_admin'
 AND security.can_read_own_conversation(tenant_id,owner_user_id));

CREATE FUNCTION security.builder_scaffold_admit(
 p_session uuid,p_tenant uuid,p_client_request uuid,p_target text,p_payload jsonb,
 p_model_id text,p_policy_revision text,p_budget_period date
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog,security,portal,pg_temp AS $body$
DECLARE u uuid;h bytea;old portal.builder_scaffold_proposals%ROWTYPE;result jsonb;
BEGIN
 IF p_client_request IS NULL OR p_target NOT IN ('agent','workflow') OR p_target IS NULL
 OR p_payload IS NULL OR jsonb_typeof(p_payload)<>'object'
 OR p_payload-ARRAY['intent','answers','document_refs']::text[]<>'{}'::jsonb
 OR NOT p_payload ?& ARRAY['intent','answers','document_refs']
 OR jsonb_typeof(p_payload->'intent')<>'string' OR octet_length(p_payload->>'intent') NOT BETWEEN 1 AND 4000
 OR jsonb_typeof(p_payload->'answers')<>'object'
 OR (SELECT count(*) FROM jsonb_object_keys(p_payload->'answers'))>20
 OR jsonb_typeof(p_payload->'document_refs')<>'array' OR jsonb_array_length(p_payload->'document_refs')>5
 OR p_model_id IS NULL OR p_model_id !~ '^[a-z0-9][a-z0-9._-]{0,63}$'
 OR p_policy_revision IS NULL OR p_policy_revision !~ '^[A-Za-z0-9._-]{1,64}$'
 OR p_budget_period IS NULL OR extract(day FROM p_budget_period)<>1 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
 END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 h:=sha256(convert_to(jsonb_build_object('target',p_target,'payload',p_payload)::text,'UTF8'));
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':builder-scaffold:'||u::text||p_client_request::text,0));
 SELECT * INTO old FROM portal.builder_scaffold_proposals
  WHERE tenant_id=p_tenant AND owner_user_id=u AND client_request_id=p_client_request FOR UPDATE;
 IF FOUND THEN
  IF old.request_hash<>h THEN RAISE EXCEPTION 'REQUEST_CONFLICT' USING ERRCODE='A0409'; END IF;
  RETURN jsonb_build_object('proposal_id',old.proposal_id,'state',old.state,'revision',old.revision,'replayed',true,
   'proposal',old.proposal_payload,'error_code',old.safe_error_code);
 END IF;
 INSERT INTO portal.builder_scaffold_proposals(tenant_id,owner_user_id,client_request_id,request_hash,target,
  request_payload,model_id,policy_revision,budget_period)
 VALUES(p_tenant,u,p_client_request,h,p_target,p_payload,p_model_id,p_policy_revision,p_budget_period)
 RETURNING * INTO old;
 result:=jsonb_build_object('proposal_id',old.proposal_id,'state',old.state,'revision',old.revision,'replayed',false,
  'proposal',NULL,'error_code',NULL);
 RETURN result;
END;$body$;
ALTER FUNCTION security.builder_scaffold_admit(uuid,uuid,uuid,text,jsonb,text,text,date) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_admit(uuid,uuid,uuid,text,jsonb,text,text,date) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_admit(uuid,uuid,uuid,text,jsonb,text,text,date) TO ai_web;

CREATE FUNCTION security.builder_scaffold_read(p_session uuid,p_tenant uuid,p_proposal uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,pg_temp AS $body$
DECLARE u uuid;r portal.builder_scaffold_proposals%ROWTYPE;
BEGIN
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',false);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 SELECT * INTO r FROM portal.builder_scaffold_proposals
  WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 RETURN jsonb_build_object('proposal_id',r.proposal_id,'target',r.target,'state',r.state,'revision',r.revision,
  'proposal',r.proposal_payload,'error_code',r.safe_error_code,'model_id',r.model_id,
  'policy_revision',r.policy_revision,'budget_period',r.budget_period,'created_at',r.created_at);
END;$body$;
ALTER FUNCTION security.builder_scaffold_read(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_read(uuid,uuid,uuid) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_read(uuid,uuid,uuid) TO ai_web;

CREATE FUNCTION security.builder_scaffold_discard(p_session uuid,p_tenant uuid,p_proposal uuid,p_revision bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,pg_temp AS $body$
DECLARE u uuid;r portal.builder_scaffold_proposals%ROWTYPE;
BEGIN
 IF p_proposal IS NULL OR p_revision IS NULL OR p_revision<1 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',true);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 SELECT * INTO r FROM portal.builder_scaffold_proposals WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF r.revision<>p_revision THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 IF r.state='discarded' THEN RETURN jsonb_build_object('proposal_id',r.proposal_id,'state','discarded','revision',r.revision,'replayed',true); END IF;
 UPDATE portal.builder_scaffold_proposals SET state='discarded',request_payload='{}'::jsonb,proposal_payload=NULL,
  safe_error_code=NULL,updated_at=clock_timestamp(),revision=revision+1
 WHERE tenant_id=p_tenant AND proposal_id=p_proposal RETURNING * INTO r;
 RETURN jsonb_build_object('proposal_id',r.proposal_id,'state',r.state,'revision',r.revision,'replayed',false);
END;$body$;
ALTER FUNCTION security.builder_scaffold_discard(uuid,uuid,uuid,bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_discard(uuid,uuid,uuid,bigint) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.builder_scaffold_discard(uuid,uuid,uuid,bigint) TO ai_web;

-- Generation completion remains private to the service and will be enabled
-- alongside the dedicated metered, non-conversation call capability.
CREATE FUNCTION security.builder_scaffold_complete(uuid,uuid,uuid,bigint,jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,portal,pg_temp AS $body$
DECLARE u uuid;r portal.builder_scaffold_proposals%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' OR $5 IS NULL OR jsonb_typeof($5)<>'object' OR $4 IS NULL OR $4<1 THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 u:=security.operations_authorize($1,$2,'agent_admin',true);
 PERFORM set_config('app.operations_scope','agent_admin',true);
 SELECT * INTO r FROM portal.builder_scaffold_proposals WHERE tenant_id=$2 AND owner_user_id=u AND proposal_id=$3 FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF r.revision<>$4 OR r.state<>'admitted' THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 UPDATE portal.builder_scaffold_proposals SET state='ready',proposal_payload=$5,updated_at=clock_timestamp(),revision=revision+1
 WHERE tenant_id=$2 AND proposal_id=$3 RETURNING * INTO r;
 RETURN jsonb_build_object('proposal_id',r.proposal_id,'state',r.state,'revision',r.revision,'proposal',r.proposal_payload);
END;$body$;
ALTER FUNCTION security.builder_scaffold_complete(uuid,uuid,uuid,bigint,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.builder_scaffold_complete(uuid,uuid,uuid,bigint,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
