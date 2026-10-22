-- Bind each dynamic Tool revision to its canonical schema and imported source
-- metadata. Registry versions are append-only; review digests can safely refer
-- to this immutable revision boundary. This does not authorize publication.

ALTER TABLE portal.mcp_tool_versions
    ADD COLUMN integrity_digest bytea;

UPDATE portal.mcp_tool_versions
   SET integrity_digest = sha256(convert_to(jsonb_build_object(
       'tenant_id', tenant_id,
       'tool_id', tool_id,
       'revision_number', revision_number,
       'mcp_tool_spec', mcp_tool_spec,
       'raw_source_spec', raw_source_spec
   )::text, 'UTF8'))
 WHERE integrity_digest IS NULL;

ALTER TABLE portal.mcp_tool_versions
    ALTER COLUMN integrity_digest SET NOT NULL,
    ADD CONSTRAINT mcp_tool_version_integrity_digest_length
        CHECK (octet_length(integrity_digest) = 32);

CREATE FUNCTION security.mcp_tool_version_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, portal, pg_temp
AS $function$
DECLARE
    expected_digest bytea;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'MCP_TOOL_VERSION_IMMUTABLE' USING ERRCODE = '23514';
    END IF;

    expected_digest := sha256(convert_to(jsonb_build_object(
        'tenant_id', NEW.tenant_id,
        'tool_id', NEW.tool_id,
        'revision_number', NEW.revision_number,
        'mcp_tool_spec', NEW.mcp_tool_spec,
        'raw_source_spec', NEW.raw_source_spec
    )::text, 'UTF8'));

    IF NEW.integrity_digest IS NULL THEN
        NEW.integrity_digest := expected_digest;
    ELSIF NEW.integrity_digest <> expected_digest THEN
        RAISE EXCEPTION 'MCP_TOOL_VERSION_DIGEST_MISMATCH' USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$function$;

ALTER FUNCTION security.mcp_tool_version_integrity_guard() OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.mcp_tool_version_integrity_guard()
    FROM PUBLIC, ai_web, ai_index, ai_meter;

CREATE TRIGGER mcp_tool_version_integrity_guard
    BEFORE INSERT OR UPDATE OR DELETE ON portal.mcp_tool_versions
    FOR EACH ROW EXECUTE FUNCTION security.mcp_tool_version_integrity_guard();
