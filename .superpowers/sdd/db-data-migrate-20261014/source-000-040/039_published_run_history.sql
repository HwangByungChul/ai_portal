-- Owner metadata survives retirement; answer access keeps the existing exact publication guard.
CREATE INDEX published_run_owner_history ON portal.published_agent_runs(tenant_id,owner_user_id,asset_id,run_id);
CREATE FUNCTION security.published_run_history(p_session uuid,p_tenant uuid,p_action text,p_id uuid,p_body jsonb,p_mode text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE u uuid;cursor_id uuid;asset uuid;state_filter text;anchor timestamptz;row record;items jsonb:='[]';entry jsonb;next_id uuid;allowed boolean;name text;binding jsonb;pub jsonb;
BEGIN
 u:=security.run_authorize(p_session,p_tenant,false);
 IF p_action IS NULL OR p_action NOT IN ('list','record') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR coalesce(p_mode,'') NOT IN ('mock','real') OR p_body-ARRAY['cursor','asset_id','state']<>'{}'
 OR (p_action='record' AND (p_id IS NULL OR p_body<>'{}'))
 OR (p_action='list' AND p_id IS NOT NULL)
 OR EXISTS(SELECT 1 FROM jsonb_each(p_body) kv WHERE jsonb_typeof(kv.value)<>'string')
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 cursor_id:=(p_body->>'cursor')::uuid;asset:=(p_body->>'asset_id')::uuid;state_filter:=p_body->>'state';
 IF state_filter IS NOT NULL AND state_filter NOT IN ('accepted','running','cancel_requested','completed','cancelled','failed','blocked','interrupted') THEN
 RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF cursor_id IS NOT NULL THEN
 SELECT r.created_at INTO anchor FROM portal.runs r JOIN portal.published_agent_runs q USING(tenant_id,run_id)
 WHERE r.tenant_id=p_tenant AND r.owner_user_id=u AND q.owner_user_id=u AND r.task_kind='asset_chat'
 AND r.run_id=cursor_id AND (asset IS NULL OR q.asset_id=asset) AND (state_filter IS NULL OR r.state=state_filter);
 IF anchor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;END IF;
 FOR row IN SELECT r.run_id,r.state,r.revision,r.asset_revision,r.asset_version_id,r.execution_mode,r.created_at,q.asset_id,q.publication_revision
 FROM portal.runs r JOIN portal.published_agent_runs q USING(tenant_id,run_id)
 WHERE r.tenant_id=p_tenant AND r.owner_user_id=u AND q.owner_user_id=u AND r.task_kind='asset_chat'
 AND (p_action<>'record' OR r.run_id=p_id) AND (asset IS NULL OR q.asset_id=asset) AND (state_filter IS NULL OR r.state=state_filter)
 AND (anchor IS NULL OR (r.created_at,r.run_id)<(anchor,cursor_id)) ORDER BY r.created_at DESC,r.run_id DESC LIMIT 21 LOOP
 allowed:=false;name:=NULL;
 BEGIN
 binding:=security.published_run_guard(p_session,p_tenant,row.run_id);
 pub:=security.published_asset_guard(p_session,p_tenant,row.asset_id,row.execution_mode);
 allowed:=true;name:=pub->'config'->>'name';
 EXCEPTION WHEN SQLSTATE 'A0404' OR SQLSTATE 'D0404' OR SQLSTATE 'B0340' OR SQLSTATE 'B0401' THEN NULL;END;
 entry:=to_jsonb(row)||jsonb_build_object('is_terminal',row.state IN ('completed','cancelled','failed','blocked','interrupted'),'available',allowed,'display_name',name);
 IF p_action='record' THEN RETURN entry;END IF;
 items:=items||jsonb_build_array(entry);
 END LOOP;
 IF p_action='record' THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
 IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'run_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
END;$body$;
ALTER FUNCTION security.published_run_history(uuid,uuid,text,uuid,jsonb,text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.published_run_history(uuid,uuid,text,uuid,jsonb,text) FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.published_run_history(uuid,uuid,text,uuid,jsonb,text) TO ai_web;

-- Cancellation returns owner metadata for dynamic runs, without reopening withdrawn answers.
CREATE OR REPLACE FUNCTION security.run_cancel(p_session uuid,p_tenant uuid,p_run uuid,p_expected bigint,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE v_user uuid;v_row portal.runs%ROWTYPE;v_action text;
BEGIN
 v_user:=security.run_authorize(p_session,p_tenant,true);
 SELECT * INTO v_row FROM portal.runs WHERE tenant_id=p_tenant AND run_id=p_run FOR UPDATE;
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF v_row.run_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404'; END IF;
 IF p_expected IS NULL OR p_expected<1 OR p_request IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
 IF v_row.state IN ('completed','failed','cancelled','blocked','interrupted','cancel_requested') THEN RETURN CASE WHEN v_row.task_kind='asset_chat' THEN security.published_run_history(p_session,p_tenant,'record',p_run,'{}'::jsonb,v_row.execution_mode) ELSE security.run_view(p_tenant,p_run) END; END IF;
 IF v_row.revision<>p_expected THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409'; END IF;
 IF v_row.state='accepted' THEN
  IF EXISTS(SELECT 1 FROM ops.call_attempts WHERE tenant_id=p_tenant AND run_id=p_run) THEN
   RAISE EXCEPTION 'REVIEW_REQUIRED' USING ERRCODE='B0210'; END IF;
  UPDATE portal.runs SET state='cancelled',stage='terminal',revision=revision+1,
   cancel_requested_at=clock_timestamp(),ended_at=clock_timestamp() WHERE tenant_id=p_tenant AND run_id=p_run;
  v_action:='run_cancelled';
 ELSE
  UPDATE portal.runs SET state='cancel_requested',revision=revision+1,cancel_requested_at=clock_timestamp()
   WHERE tenant_id=p_tenant AND run_id=p_run;
  v_action:='run_cancel_requested';
 END IF;
 INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,opaque_target_id,result,revisions)
 VALUES(p_request,'tenant',p_tenant,v_user,v_action,p_run,'ok',jsonb_build_object('expected_revision',p_expected,'revision',p_expected+1));
 IF NOT security.touch_session(p_session) THEN RAISE EXCEPTION 'AUTH_REQUIRED' USING ERRCODE='A0401'; END IF;
 RETURN CASE WHEN v_row.task_kind='asset_chat' THEN security.published_run_history(p_session,p_tenant,'record',p_run,'{}'::jsonb,v_row.execution_mode) ELSE security.run_view(p_tenant,p_run) END;
END; $body$;
