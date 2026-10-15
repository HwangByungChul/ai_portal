-- DP04: private owner feedback; aggregate-only management. No ledger/payload mutation.
CREATE TABLE portal.response_feedback (
 tenant_id uuid NOT NULL,run_id uuid NOT NULL,conversation_id uuid NOT NULL,owner_user_id uuid NOT NULL,
 agent_key text NOT NULL,execution_mode text NOT NULL,rating text NOT NULL CHECK(rating IN ('positive','negative')),
 comment text CHECK(comment IS NULL OR char_length(comment)<=1000),revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),withdrawn_at timestamptz,
 PRIMARY KEY(tenant_id,run_id),
 FOREIGN KEY(tenant_id,run_id,conversation_id,owner_user_id,agent_key) REFERENCES portal.runs(tenant_id,run_id,conversation_id,owner_user_id,agent_key),
 FOREIGN KEY(tenant_id,run_id,owner_user_id,execution_mode,agent_key) REFERENCES portal.runs(tenant_id,run_id,owner_user_id,execution_mode,agent_key),
 CHECK(withdrawn_at IS NULL OR comment IS NULL)
);
ALTER TABLE portal.response_feedback OWNER TO ai_owner;
ALTER TABLE portal.response_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.response_feedback FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.response_feedback FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
GRANT SELECT ON portal.response_feedback TO ai_web;
GRANT SELECT,INSERT ON portal.response_feedback TO ai_policy_executor;
GRANT UPDATE(rating,comment,revision,updated_at,withdrawn_at) ON portal.response_feedback TO ai_policy_executor;
CREATE INDEX feedback_summary_period ON portal.response_feedback(tenant_id,execution_mode,agent_key,updated_at) WHERE withdrawn_at IS NULL;

CREATE FUNCTION security.can_read_feedback_summary(p_tenant uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 -- Explicit feedback.summary_read capability, currently mapped to active tenant management.
 RETURN session_user='ai_web' AND security.can_manage_current_tenant(p_tenant);
END; $body$;
ALTER FUNCTION security.can_read_feedback_summary(uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.can_read_feedback_summary(uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;

CREATE POLICY feedback_web_owner ON portal.response_feedback FOR SELECT TO ai_web
 USING(security.can_read_own_conversation(tenant_id,owner_user_id)
 AND EXISTS(SELECT 1 FROM portal.runs r WHERE r.tenant_id=response_feedback.tenant_id AND r.run_id=response_feedback.run_id AND r.state='completed' AND r.answer_kind='answer')
 AND EXISTS(SELECT 1 FROM portal.messages m WHERE m.tenant_id=response_feedback.tenant_id AND m.run_id=response_feedback.run_id AND m.role='assistant' AND NOT m.payload_purged));
CREATE POLICY feedback_policy_owner ON portal.response_feedback TO ai_policy_executor
 USING(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id))
 WITH CHECK(current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id));
CREATE POLICY feedback_policy_summary ON portal.response_feedback FOR SELECT TO ai_policy_executor
 USING(current_setting('app.feedback_scope',true)='summary' AND security.can_read_feedback_summary(tenant_id));
CREATE POLICY conversation_feedback_summary ON portal.conversations FOR SELECT TO ai_policy_executor
 USING(current_setting('app.feedback_scope',true)='summary' AND security.can_read_feedback_summary(tenant_id));
CREATE POLICY audit_response_feedback ON ops.audit_events FOR INSERT TO ai_policy_executor
 WITH CHECK(scope_kind='tenant' AND current_setting('app.run_scope',true)='owner'
 AND security.run_row_allowed(tenant_id,actor_id) AND action IN ('feedback_updated','feedback_withdrawn'));

CREATE FUNCTION security.feedback_target(p_session uuid,p_tenant uuid,p_run uuid,p_lock boolean) RETURNS portal.runs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_run portal.runs%ROWTYPE;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,p_lock);
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run AND owner_user_id=v_user;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF p_lock THEN
  PERFORM 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id AND deleted_at IS NULL FOR UPDATE;
 ELSE
  PERFORM 1 FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=v_run.conversation_id AND deleted_at IS NULL;
 END IF;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF v_run.state<>'completed' OR v_run.answer_kind IS DISTINCT FROM 'answer'
 OR NOT security.can_read_rag_answer_payload(p_tenant,p_run)
 OR NOT EXISTS(SELECT 1 FROM portal.messages WHERE tenant_id=p_tenant AND run_id=p_run AND role='assistant' AND NOT payload_purged) THEN
  RAISE EXCEPTION 'FEEDBACK_NOT_READY' USING ERRCODE='B0412'; END IF;
 RETURN v_run;
END; $body$;

CREATE FUNCTION security.feedback_read(p_session uuid,p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_row portal.response_feedback%ROWTYPE;
BEGIN
 PERFORM security.feedback_target(p_session,p_tenant,p_run,false);
 SELECT * INTO v_row FROM portal.response_feedback WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND THEN RETURN jsonb_build_object('run_id',p_run,'active',false,'revision',0,'rating',NULL,'comment',NULL,'updated_at',NULL); END IF;
 RETURN jsonb_build_object('run_id',p_run,'active',v_row.withdrawn_at IS NULL,'revision',v_row.revision,
 'rating',CASE WHEN v_row.withdrawn_at IS NULL THEN v_row.rating ELSE NULL END,
 'comment',CASE WHEN v_row.withdrawn_at IS NULL THEN v_row.comment ELSE NULL END,'updated_at',v_row.updated_at);
END; $body$;

CREATE FUNCTION security.feedback_mutate(p_session uuid,p_tenant uuid,p_run uuid,p_delta jsonb,p_revision bigint,p_delete boolean,p_request uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_row portal.response_feedback%ROWTYPE;v_exists boolean;v_same boolean;v_replay boolean:=false;v_rating text;v_comment text;
BEGIN
 IF p_run IS NULL OR p_revision IS NULL OR p_revision<0 OR p_delete IS NULL OR p_request IS NULL OR p_delta IS NULL
 OR jsonb_typeof(p_delta)<>'object' OR p_delta-ARRAY['rating','comment']::text[]<>'{}'::jsonb
 OR (p_delete AND p_delta<>'{}'::jsonb) THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF NOT p_delete THEN
  IF NOT p_delta ?& ARRAY['rating','comment']::text[] OR jsonb_typeof(p_delta->'rating')<>'string'
  OR p_delta->>'rating' NOT IN ('positive','negative') OR jsonb_typeof(p_delta->'comment')<>'string'
  OR char_length(p_delta->>'comment')>1000 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  v_rating:=p_delta->>'rating';v_comment:=btrim(p_delta->>'comment');
 END IF;
 v_run:=security.feedback_target(p_session,p_tenant,p_run,true);
 SELECT * INTO v_row FROM portal.response_feedback WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 v_exists:=FOUND;
 IF NOT v_exists THEN
  IF p_revision<>0 THEN RAISE EXCEPTION 'FEEDBACK_CONFLICT' USING ERRCODE='B0411'; END IF;
  IF p_delete THEN v_replay:=true;
  ELSE
   INSERT INTO portal.response_feedback(tenant_id,run_id,conversation_id,owner_user_id,agent_key,execution_mode,rating,comment)
    VALUES(p_tenant,p_run,v_run.conversation_id,v_run.owner_user_id,v_run.agent_key,v_run.execution_mode,v_rating,v_comment);
  END IF;
 ELSE
  v_same:=CASE WHEN p_delete THEN v_row.withdrawn_at IS NOT NULL
   ELSE v_row.withdrawn_at IS NULL AND v_row.rating=v_rating AND v_row.comment=v_comment END;
  IF v_row.revision<>p_revision THEN
   IF v_row.revision-1=p_revision AND v_same THEN v_replay:=true;
   ELSE RAISE EXCEPTION 'FEEDBACK_CONFLICT' USING ERRCODE='B0411'; END IF;
  ELSE v_replay:=v_same; END IF;
  IF NOT v_replay THEN
   IF v_row.revision=9223372036854775807 THEN RAISE EXCEPTION 'FEEDBACK_CONFLICT' USING ERRCODE='B0411'; END IF;
   UPDATE portal.response_feedback SET rating=CASE WHEN p_delete THEN rating ELSE v_rating END,
    comment=CASE WHEN p_delete THEN NULL ELSE v_comment END,revision=revision+1,updated_at=clock_timestamp(),
    withdrawn_at=CASE WHEN p_delete THEN clock_timestamp() ELSE NULL END WHERE tenant_id=p_tenant AND run_id=p_run;
  END IF;
 END IF;
 IF NOT v_replay THEN
  INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
   SELECT p_request,'tenant',p_tenant,v_run.owner_user_id,CASE WHEN p_delete THEN 'feedback_withdrawn' ELSE 'feedback_updated' END,p_run,'ok',jsonb_build_object('feedback_revision',revision)
   FROM portal.response_feedback WHERE tenant_id=p_tenant AND run_id=p_run;
 END IF;
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN security.feedback_read(p_session,p_tenant,p_run)||jsonb_build_object('replayed',v_replay);
END; $body$;

CREATE FUNCTION security.feedback_summary(p_session uuid,p_tenant uuid,p_period date,p_mode text,p_agent text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_items jsonb;
BEGIN
 PERFORM security.operations_authorize(p_session,p_tenant,'usage_admin',false);
 IF NOT security.can_read_feedback_summary(p_tenant) THEN RAISE EXCEPTION 'CAPABILITY_DENIED' USING ERRCODE='A0403'; END IF;
 IF p_period IS NULL OR extract(day FROM p_period)<>1 OR extract(year FROM p_period) NOT BETWEEN 2000 AND 2100
 OR p_mode IS NULL OR p_mode NOT IN ('mock','real') OR (p_agent IS NOT NULL AND p_agent NOT IN ('general','rules_rag')) THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 PERFORM set_config('app.feedback_scope','summary',true);
 SELECT jsonb_agg(jsonb_build_object('agent_key',q.agent_key,'status',CASE WHEN q.total=0 THEN 'empty' WHEN q.participants<3 THEN 'suppressed' ELSE 'available' END,
  'positive_count',CASE WHEN q.total=0 OR q.participants>=3 THEN q.positive ELSE NULL END,
  'negative_count',CASE WHEN q.total=0 OR q.participants>=3 THEN q.negative ELSE NULL END,
  'total_count',CASE WHEN q.total=0 OR q.participants>=3 THEN q.total ELSE NULL END) ORDER BY q.agent_key) INTO v_items
 FROM (SELECT a.agent_key,count(f.run_id) AS total,count(DISTINCT f.owner_user_id) AS participants,
  count(f.run_id) FILTER(WHERE f.rating='positive') AS positive,count(f.run_id) FILTER(WHERE f.rating='negative') AS negative
  FROM (VALUES('general'),('rules_rag')) a(agent_key)
  LEFT JOIN portal.response_feedback f ON f.tenant_id=p_tenant AND f.agent_key=a.agent_key AND f.execution_mode=p_mode AND f.withdrawn_at IS NULL
   AND f.updated_at>=p_period::timestamp AT TIME ZONE 'UTC' AND f.updated_at<(p_period+interval '1 month')::timestamp AT TIME ZONE 'UTC'
   AND EXISTS(SELECT 1 FROM portal.conversations c WHERE c.tenant_id=f.tenant_id AND c.conversation_id=f.conversation_id AND c.deleted_at IS NULL)
  WHERE p_agent IS NULL OR a.agent_key=p_agent GROUP BY a.agent_key) q;
 RETURN jsonb_build_object('period',p_period,'execution_mode',p_mode,'minimum_participants',3,'items',coalesce(v_items,'[]'::jsonb));
END; $body$;

ALTER FUNCTION security.feedback_target(uuid,uuid,uuid,boolean) OWNER TO ai_policy_executor;
ALTER FUNCTION security.feedback_read(uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.feedback_mutate(uuid,uuid,uuid,jsonb,bigint,boolean,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.feedback_summary(uuid,uuid,date,text,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.feedback_target(uuid,uuid,uuid,boolean),security.feedback_read(uuid,uuid,uuid),security.feedback_mutate(uuid,uuid,uuid,jsonb,bigint,boolean,uuid),security.feedback_summary(uuid,uuid,date,text,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.feedback_read(uuid,uuid,uuid),security.feedback_mutate(uuid,uuid,uuid,jsonb,bigint,boolean,uuid),security.feedback_summary(uuid,uuid,date,text,text) TO ai_web;
