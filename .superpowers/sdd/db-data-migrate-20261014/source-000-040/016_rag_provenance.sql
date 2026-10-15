-- Metadata-only proof supports all-source gate and exact quote binding without executor payload reads.
CREATE FUNCTION security.quote_digest(value text) RETURNS bytea LANGUAGE sql IMMUTABLE STRICT SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$ SELECT sha256(convert_to(value,'UTF8')); $body$;
ALTER FUNCTION security.quote_digest(text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.quote_digest(text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.quote_digest(text) TO ai_index;
ALTER TABLE rag.evidence ADD COLUMN quote_sha256 bytea GENERATED ALWAYS AS (security.quote_digest(exact_quote)) STORED;
ALTER TABLE portal.answer_evidence ADD COLUMN relation_id uuid;
ALTER TABLE portal.answer_evidence ADD CONSTRAINT answer_relation_binding FOREIGN KEY(source_tenant_id,index_id,relation_id) REFERENCES rag.relations(tenant_id,index_id,relation_id);
GRANT SELECT(tenant_id,document_id,version_id,index_id,evidence_id,source_sha256,start_offset,end_offset,line_start,line_end,quote_sha256,payload_purged) ON rag.evidence TO ai_policy_executor;
GRANT SELECT ON rag.relation_evidence TO ai_policy_executor;
GRANT SELECT(tenant_id,run_id,ordinal,source_tenant_id,document_id,version_id,index_id,evidence_id,source_sha256,payload_purged,relation_id) ON portal.answer_evidence TO ai_policy_executor;
GRANT INSERT ON portal.answer_evidence TO ai_policy_executor;
GRANT SELECT(source_sha256) ON rag.document_versions TO ai_policy_executor;
CREATE POLICY evidence_current_metadata ON rag.evidence FOR SELECT TO ai_policy_executor USING(session_user='ai_web' AND security.document_can_read(tenant_id,document_id,version_id,index_id));
CREATE POLICY relation_evidence_current_metadata ON rag.relation_evidence FOR SELECT TO ai_policy_executor USING(session_user='ai_web' AND EXISTS(SELECT 1 FROM rag.evidence e WHERE (e.tenant_id,e.index_id,e.evidence_id)=(relation_evidence.tenant_id,relation_evidence.index_id,relation_evidence.evidence_id)));
CREATE POLICY run_current_gate_metadata ON portal.runs FOR SELECT TO ai_policy_executor USING(session_user='ai_web' AND security.can_read_own_conversation(tenant_id,owner_user_id));
CREATE POLICY answer_current_metadata ON portal.answer_evidence FOR SELECT TO ai_policy_executor USING(session_user='ai_web' AND EXISTS(SELECT 1 FROM portal.runs r WHERE (r.tenant_id,r.run_id)=(answer_evidence.tenant_id,answer_evidence.run_id) AND security.can_read_own_conversation(r.tenant_id,r.owner_user_id)));
CREATE POLICY answer_current_insert ON portal.answer_evidence FOR INSERT TO ai_policy_executor WITH CHECK(session_user='ai_web' AND current_setting('app.rag_finalize',true)=run_id::text AND security.document_can_read(source_tenant_id,document_id,version_id,index_id) AND EXISTS(SELECT 1 FROM portal.runs r WHERE (r.tenant_id,r.run_id)=(answer_evidence.tenant_id,answer_evidence.run_id) AND r.agent_key='rules_rag' AND r.state='running' AND security.can_read_own_conversation(r.tenant_id,r.owner_user_id)));
CREATE POLICY agent_current_gate ON portal.agent_configs FOR SELECT TO ai_policy_executor USING(session_user='ai_web' AND security.can_read_agent(tenant_id));
GRANT UPDATE(answer_kind,source_count,provenance_sealed) ON portal.runs TO ai_policy_executor;

CREATE FUNCTION security.rag_sources_guard(p_session uuid,p_tenant uuid,p_mode text,p_sources jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE src jsonb;st uuid;doc uuid;ver uuid;idx uuid;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_mode IS NULL OR p_mode NOT IN ('mock','real') OR p_sources IS NULL OR jsonb_typeof(p_sources)<>'array' OR jsonb_array_length(p_sources)>128 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 FOR src IN SELECT value FROM jsonb_array_elements(p_sources) ORDER BY value->>'source_tenant_id',value->>'document_id',value->>'version_id' LOOP
  IF jsonb_typeof(src)<>'object' OR src-ARRAY['source_tenant_id','document_id','version_id','index_id']::text[]<>'{}'::jsonb OR NOT src ?& ARRAY['source_tenant_id','document_id','version_id','index_id'] THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  BEGIN st:=(src->>'source_tenant_id')::uuid;doc:=(src->>'document_id')::uuid;ver:=(src->>'version_id')::uuid;idx:=(src->>'index_id')::uuid;EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END;
  PERFORM tenant_id FROM security.tenants WHERE tenant_id=st FOR SHARE;
  PERFORM document_id FROM security.document_access WHERE tenant_id=st AND document_id=doc FOR SHARE;
  PERFORM version_id FROM security.document_publications WHERE tenant_id=st AND document_id=doc AND version_id=ver FOR SHARE;
  IF st<>p_tenant THEN PERFORM grant_id FROM security.share_grants WHERE owner_tenant_id=st AND document_id=doc AND version_id=ver AND recipient_tenant_id=p_tenant AND active FOR SHARE;END IF;
  IF NOT security.document_can_read(st,doc,ver,idx) OR NOT EXISTS(SELECT 1 FROM rag.index_builds WHERE tenant_id=st AND index_id=idx AND execution_mode=p_mode AND embedding_model='text-embedding-3-small' AND embedding_dimensions=1536 AND pipeline_revision='rules-v1') THEN RAISE EXCEPTION 'DOCUMENT_UNAVAILABLE' USING ERRCODE='A0404';END IF;
 END LOOP;
 RETURN true;
END;$body$;

CREATE FUNCTION security.can_read_rag_answer_payload(p_tenant uuid,p_run uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;
BEGIN
 IF session_user<>'ai_web' THEN RETURN false;END IF;
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND OR NOT security.can_read_own_conversation(p_tenant,r.owner_user_id) THEN RETURN false;END IF;
 IF r.agent_key='general' THEN RETURN true;END IF;
 IF r.state<>'completed' OR NOT r.provenance_sealed OR NOT EXISTS(SELECT 1 FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag' AND enabled) THEN RETURN false;END IF;
 IF (SELECT count(*) FROM portal.answer_evidence WHERE tenant_id=p_tenant AND run_id=p_run)<>r.source_count THEN RETURN false;END IF;
 RETURN NOT EXISTS(SELECT 1 FROM portal.answer_evidence e WHERE e.tenant_id=p_tenant AND e.run_id=p_run AND (e.payload_purged OR NOT security.document_can_read(e.source_tenant_id,e.document_id,e.version_id,e.index_id) OR NOT EXISTS(SELECT 1 FROM rag.document_versions v WHERE (v.tenant_id,v.document_id,v.version_id,v.source_sha256)=(e.source_tenant_id,e.document_id,e.version_id,e.source_sha256) AND NOT v.payload_purged)));
END;$body$;
DROP POLICY message_owner_read ON portal.messages;
CREATE POLICY message_owner_read ON portal.messages FOR SELECT TO ai_web USING(security.can_read_own_conversation(tenant_id,owner_user_id) AND NOT payload_purged AND (role='user' OR EXISTS(SELECT 1 FROM portal.runs r WHERE (r.tenant_id,r.run_id)=(messages.tenant_id,messages.run_id) AND r.state='completed' AND r.answer_kind IN ('answer','insufficient_evidence') AND security.can_read_rag_answer_payload(r.tenant_id,r.run_id))));
DROP POLICY message_run_owner_read ON portal.messages;
CREATE POLICY message_run_owner_read ON portal.messages FOR SELECT TO ai_policy_executor USING((current_setting('app.run_scope',true)='sequence' AND security.can_read_own_conversation(tenant_id,owner_user_id)) OR (current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id) AND NOT payload_purged AND (role='user' OR EXISTS(SELECT 1 FROM portal.runs r WHERE (r.tenant_id,r.run_id)=(messages.tenant_id,messages.run_id) AND r.state='completed' AND r.answer_kind IN ('answer','insufficient_evidence') AND security.can_read_rag_answer_payload(r.tenant_id,r.run_id)))));
DROP POLICY message_execution_assistant ON portal.messages;
CREATE POLICY message_execution_assistant ON portal.messages FOR INSERT TO ai_policy_executor WITH CHECK(session_user='ai_web' AND current_setting('app.run_scope',true)='owner' AND security.run_row_allowed(tenant_id,owner_user_id) AND role='assistant' AND NOT payload_purged AND ((agent_key='general' AND payload_kind='general_assistant') OR (agent_key='rules_rag' AND payload_kind='rag_assistant' AND current_setting('app.rag_finalize',true)=run_id::text)));

CREATE FUNCTION security.rag_finish(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_body text,p_kind text,p_evidence jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE r portal.runs%ROWTYPE;seq bigint;e jsonb;n integer:=0;source uuid;doc uuid;ver uuid;idx uuid;ev uuid;rel uuid;proof record;
BEGIN
 IF p_body IS NULL OR btrim(p_body)='' OR octet_length(p_body)>65536 OR p_kind IS NULL OR p_kind NOT IN ('answer','insufficient_evidence') OR p_evidence IS NULL OR jsonb_typeof(p_evidence)<>'array' OR jsonb_array_length(p_evidence)>20 OR (p_kind='answer') IS DISTINCT FROM (jsonb_array_length(p_evidence)>0) THEN RAISE EXCEPTION 'ANSWER_EVIDENCE_INVALID' USING ERRCODE='A0422';END IF;
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF r.agent_key<>'rules_rag' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 FOR e IN SELECT value FROM jsonb_array_elements(p_evidence) LOOP
  source:=(e->>'source_tenant_id')::uuid;doc:=(e->>'document_id')::uuid;ver:=(e->>'version_id')::uuid;idx:=(e->>'index_id')::uuid;ev:=(e->>'evidence_id')::uuid;rel:=(e->>'relation_id')::uuid;
  PERFORM security.rag_sources_guard(p_session,p_tenant,r.execution_mode,jsonb_build_array(jsonb_build_object('source_tenant_id',source,'document_id',doc,'version_id',ver,'index_id',idx)));
  SELECT source_sha256,quote_sha256,start_offset,end_offset,line_start,line_end INTO proof FROM rag.evidence WHERE (tenant_id,document_id,version_id,index_id,evidence_id)=(source,doc,ver,idx,ev) AND NOT payload_purged;
  IF NOT FOUND OR proof.quote_sha256 IS DISTINCT FROM security.quote_digest(e->>'quote') OR encode(proof.source_sha256,'hex') IS DISTINCT FROM e->>'source_sha256' OR e->'location' IS DISTINCT FROM jsonb_build_object('start_offset',proof.start_offset,'end_offset',proof.end_offset,'line_start',proof.line_start,'line_end',proof.line_end) OR NOT EXISTS(SELECT 1 FROM rag.relation_evidence WHERE tenant_id=source AND index_id=idx AND evidence_id=ev AND relation_id=rel) THEN RAISE EXCEPTION 'ANSWER_EVIDENCE_INVALID' USING ERRCODE='A0422';END IF;
 END LOOP;
 IF p_kind='answer' AND NOT EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run AND operation='generate_rag' AND (state='settled' OR (state='usage_unknown' AND provider_end_status='observed')) AND NOT slot_held AND NOT cost_overrun) THEN RAISE EXCEPTION 'CALL_UNSETTLED' USING ERRCODE='B0401';END IF;
 IF NOT security.execution_heartbeat(p_session,p_tenant,p_run,p_epoch,p_worker) THEN RETURN false;END IF;
 SELECT * INTO r FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 PERFORM conversation_id FROM portal.conversations WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id FOR UPDATE;
 PERFORM set_config('app.rag_finalize',p_run::text,true);
 FOR e IN SELECT value FROM jsonb_array_elements(p_evidence) LOOP
  INSERT INTO portal.answer_evidence(tenant_id,run_id,ordinal,source_tenant_id,document_id,version_id,index_id,evidence_id,source_sha256,location_snapshot,quote_snapshot,relation_id) VALUES(p_tenant,p_run,n,(e->>'source_tenant_id')::uuid,(e->>'document_id')::uuid,(e->>'version_id')::uuid,(e->>'index_id')::uuid,(e->>'evidence_id')::uuid,decode(e->>'source_sha256','hex'),e->'location',e->>'quote',(e->>'relation_id')::uuid);n:=n+1;
 END LOOP;
 PERFORM set_config('app.run_scope','sequence',true);
 SELECT coalesce(max(sequence_no),0)+1 INTO seq FROM portal.messages WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id;
 PERFORM set_config('app.run_scope','owner',true);
 INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind) VALUES(p_tenant,gen_random_uuid(),r.conversation_id,r.owner_user_id,'rules_rag',seq,'assistant',p_body,p_run,'rag_assistant');
 UPDATE portal.runs SET state='completed',stage='terminal',revision=revision+1,answer_kind=p_kind,source_count=n,provenance_sealed=true,ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_run;
 UPDATE portal.conversations SET updated_at=clock_timestamp() WHERE tenant_id=p_tenant AND conversation_id=r.conversation_id;
 RETURN true;
END;$body$;
ALTER FUNCTION security.rag_sources_guard(uuid,uuid,text,jsonb) OWNER TO ai_policy_executor;
ALTER FUNCTION security.can_read_rag_answer_payload(uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.rag_finish(uuid,uuid,uuid,bigint,bytea,text,text,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.rag_sources_guard(uuid,uuid,text,jsonb),security.can_read_rag_answer_payload(uuid,uuid),security.rag_finish(uuid,uuid,uuid,bigint,bytea,text,text,jsonb) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.rag_sources_guard(uuid,uuid,text,jsonb),security.can_read_rag_answer_payload(uuid,uuid),security.rag_finish(uuid,uuid,uuid,bigint,bytea,text,text,jsonb) TO ai_web;

CREATE OR REPLACE FUNCTION security.run_view(p_tenant uuid,p_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_run portal.runs%ROWTYPE;v_result jsonb;v_usage text;v_terminal boolean;
BEGIN
 IF current_setting('app.run_scope',true) IS DISTINCT FROM 'owner' THEN
  RAISE EXCEPTION 'CONTEXT_DENIED' USING ERRCODE='A0403'; END IF;
 SELECT * INTO v_run FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 v_terminal:=v_run.state IN ('completed','failed','cancelled','blocked','interrupted');
 SELECT CASE WHEN bool_or(c.state='usage_unknown') THEN 'unknown'
  WHEN bool_or(c.state IN ('reserved','dispatched')) THEN 'estimated'
  WHEN bool_or(c.state='settled') THEN 'final' ELSE 'none' END INTO v_usage
 FROM ops.call_attempts c WHERE c.tenant_id=p_tenant AND c.run_id=p_run;
 IF v_run.state='completed' THEN
  SELECT jsonb_build_object('message_id',m.message_id,'text',m.body,'evidence','[]'::jsonb) INTO v_result
  FROM portal.messages m WHERE m.tenant_id=p_tenant AND m.run_id=p_run AND m.role='assistant'
  ORDER BY m.sequence_no DESC LIMIT 1;
 END IF;
 RETURN jsonb_build_object('run_id',v_run.run_id,'tenant_id',v_run.tenant_id,'conversation_id',v_run.conversation_id,
  'agent_key',v_run.agent_key,'config_version',v_run.config_snapshot->'config_version','state',v_run.state,
  'stage',v_run.stage,'revision',v_run.revision,'is_terminal',v_terminal,'answer_kind',v_run.answer_kind,
  'content_status',CASE WHEN v_run.state='completed' AND v_result IS NOT NULL THEN 'final' WHEN v_terminal THEN 'unavailable' ELSE 'pending' END,
  'execution_mode',v_run.execution_mode,'usage_status',v_usage,'error_code',v_run.safe_error_code,
  'created_at',v_run.created_at,'ended_at',v_run.ended_at,'cancel_requested_at',v_run.cancel_requested_at,'result',v_result);
END; $body$;

CREATE OR REPLACE FUNCTION security.execution_stream_view(p_session uuid,p_tenant uuid,p_run uuid,p_mode text,p_period date)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_view jsonb;v_agent portal.agent_configs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 v_view:=security.run_view(p_tenant,p_run);
 IF v_view->>'execution_mode'<>p_mode THEN RAISE EXCEPTION 'EXECUTION_FENCED' USING ERRCODE='B0401'; END IF;
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key=v_view->>'agent_key';
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 IF NOT (v_view->>'is_terminal')::boolean AND (NOT EXISTS(SELECT 1 FROM portal.runs r WHERE r.tenant_id=p_tenant AND r.run_id=p_run
 AND EXISTS(SELECT 1 FROM security.current_membership(r.origin_session_id,p_tenant))) OR NOT COALESCE(v_agent.enabled,false) OR v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL
 OR v_project.stopped OR v_project.stop_latch OR v_tenant.stopped) THEN RAISE EXCEPTION 'EXECUTION_BLOCKED' USING ERRCODE='B0405'; END IF;
 RETURN v_view||jsonb_build_object('execution_epoch',(SELECT execution_epoch FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run));
END; $body$;
CREATE FUNCTION security.document_read_visibility(p_tenant uuid,p_document uuid,p_version uuid) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 IF NOT security.document_can_read(p_tenant,p_document,p_version,NULL) THEN RETURN NULL;END IF;
 IF p_tenant IS DISTINCT FROM nullif(current_setting('app.tenant_id',true),'')::uuid THEN RETURN 'shared';END IF;
 RETURN (SELECT visibility FROM security.document_access WHERE tenant_id=p_tenant AND document_id=p_document);
END;$body$;
ALTER FUNCTION security.document_read_visibility(uuid,uuid,uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_read_visibility(uuid,uuid,uuid) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_read_visibility(uuid,uuid,uuid) TO ai_web;

CREATE FUNCTION security.rag_stage(p_session uuid,p_tenant uuid,p_run uuid,p_epoch bigint,p_worker bytea,p_stage text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
BEGIN
 PERFORM security.execution_guard(p_session,p_tenant,p_run,p_epoch,p_worker,true);
 IF p_stage IS NULL OR p_stage NOT IN ('generation','finalizing') OR NOT EXISTS(SELECT 1 FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run AND agent_key='rules_rag') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 UPDATE portal.runs SET stage=p_stage,revision=revision+1 WHERE tenant_id=p_tenant AND run_id=p_run AND state='running';
 RETURN FOUND;
END;$body$;
ALTER FUNCTION security.rag_stage(uuid,uuid,uuid,bigint,bytea,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.rag_stage(uuid,uuid,uuid,bigint,bytea,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.rag_stage(uuid,uuid,uuid,bigint,bytea,text) TO ai_web;

CREATE FUNCTION security.rag_readiness(p_session uuid,p_tenant uuid,p_period date,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_agent portal.agent_configs%ROWTYPE;v_project ops.project_budget%ROWTYPE;v_tenant ops.tenant_budgets%ROWTYPE;v_reason text;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 SELECT * INTO v_agent FROM portal.agent_configs WHERE tenant_id=p_tenant AND agent_key='rules_rag';
 SELECT * INTO v_project FROM ops.project_budget WHERE period=p_period AND mode=p_mode;
 SELECT * INTO v_tenant FROM ops.tenant_budgets WHERE tenant_id=p_tenant AND budget_id=v_project.budget_id;
 v_reason:=CASE WHEN NOT COALESCE(v_agent.enabled,false) THEN 'AGENT_DISABLED'
 WHEN v_project.budget_id IS NULL OR v_tenant.budget_id IS NULL THEN 'BUDGET_NOT_READY'
 WHEN v_project.stopped OR v_project.stop_latch THEN 'PROJECT_STOPPED' WHEN v_tenant.stopped THEN 'TENANT_STOPPED'
 WHEN p_mode='real' AND (date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date<>p_period
 OR clock_timestamp()>=timestamptz '2026-11-01 00:00:00+09') THEN 'PROJECT_STOPPED'
 WHEN v_project.accounted_krw+v_project.reserved_krw+3.84>v_project.operational_cap_krw
 OR v_tenant.accounted_krw+v_tenant.reserved_krw+3.84>LEAST(v_tenant.local_cap_krw,v_tenant.allocated_cap_krw) THEN 'QUOTA_EXCEEDED'
 WHEN v_project.active_slot>=2 OR v_tenant.active_slot>=1 THEN 'CAPACITY_BUSY' ELSE NULL END;
 RETURN jsonb_build_object('available',v_reason IS NULL,'safe_block_reason',v_reason);
END; $body$;
ALTER FUNCTION security.rag_readiness(uuid,uuid,date,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.rag_readiness(uuid,uuid,date,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.rag_readiness(uuid,uuid,date,text) TO ai_web;

