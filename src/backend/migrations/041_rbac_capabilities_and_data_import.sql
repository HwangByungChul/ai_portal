-- Migration 041: RBAC Capabilities, SOD, and Data Import Approval Pipeline
CREATE TABLE IF NOT EXISTS portal.data_imports (
  import_id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  requester_id uuid NOT NULL,
  document_id uuid NOT NULL,
  version_id uuid NOT NULL,
  classification text NOT NULL CHECK(classification IN ('internal', 'confidential', 'restricted')),
  target_scope text NOT NULL CHECK(target_scope IN ('org', 'department', 'team')),
  reason text NOT NULL,
  status text NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
  revision bigint NOT NULL DEFAULT 1 CHECK(revision > 0),
  decided_by uuid,
  decided_at timestamptz,
  comment text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(tenant_id, import_id),
  FOREIGN KEY(tenant_id) REFERENCES security.tenants(tenant_id),
  FOREIGN KEY(tenant_id, requester_id) REFERENCES security.memberships(tenant_id, user_id)
);

ALTER TABLE portal.data_imports OWNER TO ai_owner;
ALTER TABLE portal.data_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.data_imports FORCE ROW LEVEL SECURITY;

REVOKE ALL ON portal.data_imports FROM PUBLIC, ai_web, ai_index, ai_meter;
GRANT SELECT, INSERT, UPDATE ON portal.data_imports TO ai_policy_executor;

DROP POLICY IF EXISTS data_imports_tenant ON portal.data_imports;
CREATE POLICY data_imports_tenant ON portal.data_imports TO ai_policy_executor USING (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
) WITH CHECK (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);

DROP POLICY IF EXISTS audit_data_import_events ON ops.audit_events;
CREATE POLICY audit_data_import_events ON ops.audit_events FOR INSERT TO ai_policy_executor WITH CHECK (
  session_user = 'ai_web' AND scope_kind = 'tenant' AND actor_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  AND action IN ('data_import.request', 'data_import.decide')
);


CREATE OR REPLACE FUNCTION security.data_import_request(
  p_session uuid,
  p_trace uuid,
  p_tenant uuid,
  p_document_id uuid,
  p_version_id uuid,
  p_classification text,
  p_target_scope text,
  p_reason text,
  p_client_request_id uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  u uuid := NULLIF(current_setting('app.user_id', true), '')::uuid;
  v_import_id uuid;
  doc_exists boolean;
  res jsonb;
BEGIN
  PERFORM security.run_authorize(p_session, p_tenant, true);
  IF p_client_request_id IS NULL THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  IF p_classification NOT IN ('internal', 'confidential', 'restricted') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  IF p_target_scope NOT IN ('org', 'department', 'team') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;
  IF p_reason IS NULL OR trim(p_reason) = '' THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;

  -- Verify document exists in this tenant
  SELECT EXISTS(
    SELECT 1 FROM rag.documents WHERE tenant_id = p_tenant AND document_id = p_document_id AND version_id = p_version_id
  ) INTO doc_exists;
  IF NOT doc_exists THEN
    RAISE EXCEPTION 'DOCUMENT_NOT_FOUND' USING ERRCODE='A0404';
  END IF;

  v_import_id := p_client_request_id;

  INSERT INTO portal.data_imports(
    import_id, tenant_id, requester_id, document_id, version_id,
    classification, target_scope, reason, status, revision
  ) VALUES (
    v_import_id, p_tenant, u, p_document_id, p_version_id,
    p_classification, p_target_scope, p_reason, 'pending', 1
  ) ON CONFLICT (tenant_id, import_id) DO NOTHING;

  INSERT INTO ops.audit_events (
    event_id, tenant_id, actor_id, action, target_id, details
  ) VALUES (
    gen_random_uuid(), p_tenant, u, 'data_import.request', v_import_id,
    jsonb_build_object(
      'document_id', p_document_id,
      'version_id', p_version_id,
      'classification', p_classification,
      'target_scope', p_target_scope
    )
  );

  res := jsonb_build_object(
    'import_id', v_import_id,
    'status', 'pending',
    'revision', 1,
    'replayed', false
  );
  RETURN res;
END;
$body$;

ALTER FUNCTION security.data_import_request(uuid, uuid, uuid, uuid, uuid, text, text, text, uuid) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.data_import_request(uuid, uuid, uuid, uuid, uuid, text, text, text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.data_import_request(uuid, uuid, uuid, uuid, uuid, text, text, text, uuid) TO ai_web;


CREATE OR REPLACE FUNCTION security.data_import_decide(
  p_session uuid,
  p_trace uuid,
  p_tenant uuid,
  p_import_id uuid,
  p_decision text,
  p_comment text,
  p_expected_revision bigint
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  u uuid := NULLIF(current_setting('app.user_id', true), '')::uuid;
  rec portal.data_imports%ROWTYPE;
  role_name text;
BEGIN
  PERFORM security.run_authorize(p_session, p_tenant, true);
  IF p_decision NOT IN ('approved', 'rejected') THEN RAISE EXCEPTION 'ARGUMENT_REJECTED' USING ERRCODE='A0422'; END IF;

  -- Must be PADMIN or TADMIN
  SELECT m.effective_role INTO role_name
  FROM security.memberships m
  WHERE m.tenant_id = p_tenant AND m.user_id = u AND m.active = true;

  IF role_name NOT IN ('PADMIN', 'TADMIN') THEN
    RAISE EXCEPTION 'PERMISSION_DENIED' USING ERRCODE='A0403';
  END IF;

  SELECT * INTO rec FROM portal.data_imports WHERE tenant_id = p_tenant AND import_id = p_import_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'IMPORT_NOT_FOUND' USING ERRCODE='A0404';
  END IF;

  -- SOD Rule: Requester cannot self-approve
  IF rec.requester_id = u THEN
    RAISE EXCEPTION 'SELF_APPROVAL_FORBIDDEN' USING ERRCODE='A0403';
  END IF;

  IF rec.status <> 'pending' THEN
    RAISE EXCEPTION 'ALREADY_DECIDED' USING ERRCODE='A0409';
  END IF;

  IF rec.revision <> p_expected_revision THEN
    RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='A0409';
  END IF;

  UPDATE portal.data_imports
  SET status = p_decision,
      decided_by = u,
      decided_at = clock_timestamp(),
      comment = p_comment,
      revision = rec.revision + 1,
      updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant AND import_id = p_import_id;

  INSERT INTO ops.audit_events (
    event_id, tenant_id, actor_id, action, target_id, details
  ) VALUES (
    gen_random_uuid(), p_tenant, u, 'data_import.decide', p_import_id,
    jsonb_build_object(
      'decision', p_decision,
      'requester_id', rec.requester_id,
      'document_id', rec.document_id,
      'revision', rec.revision + 1
    )
  );

  RETURN jsonb_build_object(
    'import_id', p_import_id,
    'status', p_decision,
    'revision', rec.revision + 1,
    'decided_by', u,
    'replayed', false
  );
END;
$body$;

ALTER FUNCTION security.data_import_decide(uuid, uuid, uuid, uuid, text, text, bigint) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.data_import_decide(uuid, uuid, uuid, uuid, text, text, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.data_import_decide(uuid, uuid, uuid, uuid, text, text, bigint) TO ai_web;


CREATE OR REPLACE FUNCTION security.data_import_list(
  p_session uuid,
  p_tenant uuid,
  p_status text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, security, pg_temp AS $body$
DECLARE
  u uuid := NULLIF(current_setting('app.user_id', true), '')::uuid;
  items jsonb;
BEGIN
  PERFORM security.run_authorize(p_session, p_tenant, false);

  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'import_id', di.import_id,
      'tenant_id', di.tenant_id,
      'requester_id', di.requester_id,
      'document_id', di.document_id,
      'version_id', di.version_id,
      'classification', di.classification,
      'target_scope', di.target_scope,
      'reason', di.reason,
      'status', di.status,
      'revision', di.revision,
      'decided_by', di.decided_by,
      'decided_at', di.decided_at,
      'comment', di.comment,
      'created_at', di.created_at,
      'updated_at', di.updated_at
    ) ORDER BY di.created_at DESC
  ), '[]'::jsonb) INTO items
  FROM portal.data_imports di
  WHERE di.tenant_id = p_tenant
    AND (p_status IS NULL OR di.status = p_status);

  RETURN jsonb_build_object('items', items);
END;
$body$;

ALTER FUNCTION security.data_import_list(uuid, uuid, text) OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.data_import_list(uuid, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION security.data_import_list(uuid, uuid, text) TO ai_web;
