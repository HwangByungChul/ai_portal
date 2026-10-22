-- Reserve the built-in Tool namespace without changing existing definitions,
-- revisions, approval state, RLS, or the tenant-authorized registry RPC.
CREATE FUNCTION security.mcp_tool_reject_reserved_id()
RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,security,portal,pg_temp AS $body$
BEGIN
 IF NEW.tool_id IN ('financial_product_lookup','kb_rule_query','data_view_reader') THEN
  RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422';
 END IF;
 RETURN NEW;
END;$body$;
ALTER FUNCTION security.mcp_tool_reject_reserved_id() OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.mcp_tool_reject_reserved_id() FROM PUBLIC,ai_web,ai_index,ai_meter;

-- BEFORE INSERT also covers the INSERT ... ON CONFLICT registration path,
-- including an attempted re-registration of a pre-existing collision.
CREATE TRIGGER mcp_tool_reserved_id_guard
BEFORE INSERT OR UPDATE OF tool_id ON portal.mcp_tool_definitions
FOR EACH ROW EXECUTE FUNCTION security.mcp_tool_reject_reserved_id();
