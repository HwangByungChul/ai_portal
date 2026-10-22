-- Narrow server-side boundary for tenant-scoped dynamic MCP registry access.
-- Credentials are intentionally excluded; external execution remains disabled.
CREATE FUNCTION security.mcp_tool_registry_control(
 p_session uuid,p_tenant uuid,p_action text,p_tool text,p_name text,p_description text,
 p_source text,p_input jsonb,p_raw jsonb,p_dev jsonb,p_prd jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog,security,portal,pg_temp AS $body$
DECLARE u uuid; rev bigint; spec jsonb; items jsonb;
BEGIN
 u:=security.operations_authorize(p_session,p_tenant,'agent_admin',p_action='register');
 IF p_action NOT IN ('register','list','simulation_get') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 IF p_action='simulation_get' THEN
  IF p_tool IS NULL OR p_name IS NOT NULL OR p_description IS NOT NULL OR p_source IS NOT NULL OR p_input IS NOT NULL OR p_raw IS NOT NULL OR p_dev IS NOT NULL OR p_prd IS NOT NULL THEN
   RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT jsonb_build_object('tool_id',d.tool_id,'name',d.name,'description',d.description,
    'source_type',d.source_type,'enabled',d.enabled,'input_schema',v.mcp_tool_spec->'inputSchema',
    'raw_meta',v.raw_source_spec,
    'dev_profile',jsonb_build_object('protocol_type',pd.protocol_type,'base_endpoint_url',pd.base_endpoint_url),
    'prd_profile',jsonb_build_object('protocol_type',pp.protocol_type,'base_endpoint_url',pp.base_endpoint_url))
  INTO items FROM portal.mcp_tool_definitions d
  JOIN LATERAL (SELECT mcp_tool_spec,raw_source_spec FROM portal.mcp_tool_versions
    WHERE tenant_id=d.tenant_id AND tool_id=d.tool_id ORDER BY revision_number DESC LIMIT 1) v ON true
  LEFT JOIN portal.mcp_tool_endpoint_profiles pd ON pd.tenant_id=d.tenant_id AND pd.tool_id=d.tool_id AND pd.target_env='development' AND pd.active
  LEFT JOIN portal.mcp_tool_endpoint_profiles pp ON pp.tenant_id=d.tenant_id AND pp.tool_id=d.tool_id AND pp.target_env='production' AND pp.active
  WHERE d.tenant_id=p_tenant AND d.tool_id=p_tool AND d.enabled;
  IF items IS NULL THEN RAISE EXCEPTION 'NOT_FOUND' USING ERRCODE='A0404';END IF;
  RETURN items;
 END IF;
 IF p_action='list' THEN
  IF p_tool IS NOT NULL OR p_name IS NOT NULL OR p_description IS NOT NULL OR p_source IS NOT NULL OR p_input IS NOT NULL OR p_raw IS NOT NULL OR p_dev IS NOT NULL OR p_prd IS NOT NULL THEN
   RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object(
   'tool_id',d.tool_id,'name',d.name,'description',d.description,'source_type',d.source_type,
   'input_schema',coalesce(v.mcp_tool_spec->'inputSchema','{}'::jsonb),
   'revision_number',v.revision_number,'enabled',d.enabled,
   'has_dev_profile',EXISTS(SELECT 1 FROM portal.mcp_tool_endpoint_profiles pd
     WHERE pd.tenant_id=d.tenant_id AND pd.tool_id=d.tool_id AND pd.target_env='development' AND pd.active),
   'has_prd_profile',EXISTS(SELECT 1 FROM portal.mcp_tool_endpoint_profiles pp
     WHERE pp.tenant_id=d.tenant_id AND pp.tool_id=d.tool_id AND pp.target_env='production' AND pp.active)
  ) ORDER BY d.name,d.tool_id),'[]'::jsonb) INTO items
  FROM portal.mcp_tool_definitions d
  LEFT JOIN LATERAL (SELECT revision_number,mcp_tool_spec FROM portal.mcp_tool_versions
   WHERE tenant_id=d.tenant_id AND tool_id=d.tool_id ORDER BY revision_number DESC LIMIT 1) v ON true
  WHERE d.tenant_id=p_tenant AND d.enabled
  GROUP BY d.tool_id,d.name,d.description,d.source_type,d.enabled,v.mcp_tool_spec,v.revision_number;
  RETURN jsonb_build_object('items',coalesce(items,'[]'::jsonb));
 END IF;
 IF p_tool IS NULL OR p_tool !~ '^[a-zA-Z][a-zA-Z0-9_-]{1,99}$' OR p_name IS NULL OR length(p_name) NOT BETWEEN 1 AND 160
  OR p_description IS NULL OR length(p_description)>2000 OR p_source NOT IN ('openapi','wsdl','jdbc','financial_packet','custom_mcp')
  OR jsonb_typeof(p_input) IS DISTINCT FROM 'object' OR jsonb_typeof(p_raw) IS DISTINCT FROM 'object'
  OR jsonb_typeof(p_dev) IS DISTINCT FROM 'object' OR jsonb_typeof(p_prd) IS DISTINCT FROM 'object'
  OR p_dev-ARRAY['protocol_type','base_endpoint_url']::text[]<>'{}' OR p_prd-ARRAY['protocol_type','base_endpoint_url']::text[]<>'{}'
  OR coalesce(p_dev->>'protocol_type','') NOT IN ('mcp_http_sse','rest_http','soap_xml','tcp_socket','jdbc_view')
  OR coalesce(p_prd->>'protocol_type','') NOT IN ('mcp_http_sse','rest_http','soap_xml','tcp_socket','jdbc_view')
  OR coalesce(p_dev->>'base_endpoint_url','') !~ '^https://[^[:space:]]+$'
  OR coalesce(p_prd->>'base_endpoint_url','') !~ '^https://[^[:space:]]+$'
 THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text||':'||p_tool,0));
 INSERT INTO portal.mcp_tool_definitions(tenant_id,tool_id,name,description,source_type,created_by)
 VALUES(p_tenant,p_tool,p_name,p_description,p_source,u)
 ON CONFLICT(tenant_id,tool_id) DO UPDATE SET name=EXCLUDED.name,description=EXCLUDED.description,
  source_type=EXCLUDED.source_type,updated_at=clock_timestamp();
 SELECT coalesce(max(revision_number),0)+1 INTO rev FROM portal.mcp_tool_versions WHERE tenant_id=p_tenant AND tool_id=p_tool;
 spec:=jsonb_build_object('name',p_name,'description',p_description,'inputSchema',p_input,'sourceType',p_source);
 INSERT INTO portal.mcp_tool_versions(tenant_id,tool_id,revision_number,mcp_tool_spec,raw_source_spec)
 VALUES(p_tenant,p_tool,rev,spec,p_raw);
 INSERT INTO portal.mcp_tool_endpoint_profiles(tenant_id,tool_id,target_env,protocol_type,base_endpoint_url,updated_by)
 VALUES(p_tenant,p_tool,'development',p_dev->>'protocol_type',p_dev->>'base_endpoint_url',u),
       (p_tenant,p_tool,'production',p_prd->>'protocol_type',p_prd->>'base_endpoint_url',u)
 ON CONFLICT(tenant_id,tool_id,target_env) DO UPDATE SET protocol_type=EXCLUDED.protocol_type,
  base_endpoint_url=EXCLUDED.base_endpoint_url,active=true,
  updated_by=EXCLUDED.updated_by,updated_at=clock_timestamp();
 RETURN jsonb_build_object('tool_id',p_tool,'name',p_name,'description',p_description,
  'source_type',p_source,'input_schema',p_input,'revision_number',rev,'enabled',true);
END;$body$;
ALTER FUNCTION security.mcp_tool_registry_control(uuid,uuid,text,text,text,text,text,jsonb,jsonb,jsonb,jsonb) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.mcp_tool_registry_control(uuid,uuid,text,text,text,text,text,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.mcp_tool_registry_control(uuid,uuid,text,text,text,text,text,jsonb,jsonb,jsonb,jsonb) TO ai_web;
