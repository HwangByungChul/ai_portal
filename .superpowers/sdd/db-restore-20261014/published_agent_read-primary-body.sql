
DECLARE
 pub jsonb;items jsonb:='[]';entry jsonb;row record;cursor_id uuid;anchor timestamptz;next_id uuid;variables jsonb;
 u uuid:=NULLIF(current_setting('app.user_id',true),'')::uuid;
 f_active boolean; f_rev bigint; mine_filter boolean;
BEGIN
 PERFORM security.run_authorize(p_session,p_tenant,false);
 IF p_action IS NULL OR p_action NOT IN ('list','detail','history','run') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object'
 OR coalesce(p_mode,'') NOT IN ('mock','real') OR p_body-ARRAY['cursor','mine']<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='run' THEN
  IF p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  PERFORM security.published_run_guard(p_session,p_tenant,p_id);RETURN security.run_view(p_tenant,p_id);
 END IF;
 IF p_action='history' THEN
  IF p_body->>'cursor' IS NOT NULL THEN
   SELECT r.created_at INTO anchor FROM portal.runs r JOIN portal.published_agent_runs q USING(tenant_id,run_id) WHERE r.tenant_id=p_tenant AND q.asset_id=p_id AND r.run_id=(p_body->>'cursor')::uuid;
   IF anchor IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.created_at DESC,x.run_id DESC),'[]') INTO items FROM
  (SELECT r.run_id,r.state,r.revision,r.asset_revision,r.asset_version_id,r.execution_mode,r.created_at FROM portal.runs r JOIN portal.published_agent_runs q USING(tenant_id,run_id)
   WHERE r.tenant_id=p_tenant AND q.asset_id=p_id AND (anchor IS NULL OR (r.created_at,r.run_id)<(anchor,(p_body->>'cursor')::uuid)) ORDER BY r.created_at DESC,r.run_id DESC LIMIT 21) x;
  IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'run_id')::uuid;END IF;
  RETURN jsonb_build_object('items',items,'next_cursor',next_id);
 END IF;
 cursor_id:=(p_body->>'cursor')::uuid;
 mine_filter:=COALESCE((p_body->>'mine')::boolean,false);
 IF p_action='detail' THEN
  IF p_body<>'{}' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  pub:=security.published_asset_guard(p_session,p_tenant,p_id,p_mode);
 ELSE
  IF cursor_id IS NOT NULL THEN
   PERFORM security.published_asset_guard(p_session,p_tenant,cursor_id,p_mode);
  END IF;
 END IF;
 FOR row IN SELECT asset_id FROM portal.asset_publications WHERE tenant_id=p_tenant AND status='published' AND execution_mode=p_mode
 AND (p_action='detail' AND asset_id=p_id OR p_action='list' AND (cursor_id IS NULL OR asset_id>cursor_id)) ORDER BY asset_id LOOP
  BEGIN pub:=security.published_asset_guard(p_session,p_tenant,row.asset_id,p_mode);
  EXCEPTION WHEN SQLSTATE 'A0404' OR SQLSTATE 'D0404' OR SQLSTATE 'B0340' THEN CONTINUE;END;
  SELECT active,revision INTO f_active,f_rev FROM portal.dynamic_agent_favorites WHERE tenant_id=p_tenant AND user_id=u AND asset_id=row.asset_id;
  IF mine_filter AND NOT COALESCE(f_active,false) THEN CONTINUE; END IF;
  SELECT coalesce(jsonb_agg(name ORDER BY name),'[]') INTO variables FROM
  (SELECT DISTINCT x[1] AS name FROM regexp_matches((pub->'profile'->>'system_prompt')||(pub->'profile'->>'developer_prompt')||(pub->'profile'->>'user_template'),'\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}','g') x) names;
  entry:=jsonb_build_object('asset_id',pub->'asset_id','version_id',pub->'version_id','revision',pub->'asset_revision','publication_revision',pub->'publication_revision',
  'name',pub->'config'->>'name','description',pub->'config'->>'description','agent_key',pub->'config'->>'execution_kind','execution_mode',pub->>'execution_mode','variables',variables,
  'available',true,'safe_block_reason',NULL,'favorite',COALESCE(f_active,false),'favorite_revision',COALESCE(f_rev,0));
  IF p_action='detail' THEN RETURN entry;END IF;
  items:=items||jsonb_build_array(entry);EXIT WHEN jsonb_array_length(items)=21;
 END LOOP;
 IF jsonb_array_length(items)>20 THEN items:=items-20;next_id:=(items->19->>'asset_id')::uuid;END IF;
 RETURN jsonb_build_object('items',items,'next_cursor',next_id);
END;