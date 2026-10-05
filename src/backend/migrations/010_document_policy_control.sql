-- Control-only metadata can be inspected by the NOLOGIN policy role; no new payload grant.
GRANT USAGE ON SCHEMA rag TO ai_web,ai_index,ai_meter,ai_policy_executor;
GRANT SELECT(tenant_id,document_id,version_id,version_no,payload_purged) ON rag.document_versions TO ai_policy_executor;
GRANT SELECT(tenant_id,document_id,version_id,index_id,state,payload_purged) ON rag.index_builds TO ai_policy_executor;
GRANT SELECT(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind,state,lease_epoch,lease_expires_at) ON rag.jobs TO ai_policy_executor;

CREATE FUNCTION security.document_can_read(p_tenant uuid,p_document uuid,p_version uuid,p_index uuid DEFAULT NULL) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE selected uuid; actor uuid;
BEGIN
 IF session_user<>'ai_web' THEN RETURN false; END IF;
 selected:=nullif(current_setting('app.tenant_id',true),'')::uuid;
 actor:=nullif(current_setting('app.user_id',true),'')::uuid;
 IF selected IS NULL OR actor IS NULL OR NOT security.can_read_agent(selected) THEN RETURN false; END IF;
 RETURN EXISTS(SELECT 1 FROM security.document_access a
  JOIN security.tenants t ON t.tenant_id=a.tenant_id AND t.active
  JOIN security.document_publications p ON (p.tenant_id,p.document_id)=(a.tenant_id,a.document_id)
  JOIN rag.document_versions v ON (v.tenant_id,v.document_id,v.version_id)=(p.tenant_id,p.document_id,p.version_id)
  JOIN rag.index_builds i ON (i.tenant_id,i.document_id,i.version_id,i.index_id)=(p.tenant_id,p.document_id,p.version_id,p.published_index_id)
  WHERE (a.tenant_id,a.document_id,p.version_id)=(p_tenant,p_document,p_version)
   AND a.deleted_at IS NULL AND p.active AND i.state='published' AND NOT i.payload_purged AND NOT v.payload_purged
   AND (p_index IS NULL OR p_index=p.published_index_id)
   AND ((a.tenant_id=selected AND (a.visibility='org' OR a.owner_user_id=actor OR
    EXISTS(SELECT 1 FROM security.private_readers r WHERE (r.tenant_id,r.document_id,r.user_id)=(a.tenant_id,a.document_id,actor))))
    OR (a.visibility='org' AND EXISTS(SELECT 1 FROM security.share_grants g
     WHERE (g.owner_tenant_id,g.document_id,g.version_id,g.recipient_tenant_id)=(a.tenant_id,a.document_id,p.version_id,selected)
      AND g.active AND g.revoked_at IS NULL))));
EXCEPTION WHEN invalid_text_representation THEN RETURN false;
END;$body$;

CREATE FUNCTION security.document_job_authorized(p_tenant uuid,p_document uuid,p_version uuid,p_index uuid DEFAULT NULL) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE job uuid; epoch bigint; claim bytea; tenant uuid;
BEGIN
 IF session_user<>'ai_index' THEN RETURN false; END IF;
 job:=nullif(current_setting('app.job_id',true),'')::uuid;
 epoch:=nullif(current_setting('app.job_epoch',true),'')::bigint;
 tenant:=nullif(current_setting('app.job_tenant_id',true),'')::uuid;
 IF current_setting('app.job_claim',true) !~ '^[0-9a-f]{64}$' THEN RETURN false; END IF;
 claim:=decode(current_setting('app.job_claim',true),'hex');
 IF job IS NULL OR epoch IS NULL OR tenant IS DISTINCT FROM p_tenant THEN RETURN false; END IF;
 RETURN EXISTS(SELECT 1 FROM security.job_authorizations a
  JOIN rag.jobs j ON (j.tenant_id,j.job_id)=(a.tenant_id,a.job_id)
  JOIN rag.index_builds i ON (i.tenant_id,i.index_id)=(a.tenant_id,a.index_id)
  JOIN rag.document_versions v ON (v.tenant_id,v.document_id,v.version_id)=(a.tenant_id,a.document_id,a.version_id)
  JOIN security.document_access d ON (d.tenant_id,d.document_id)=(a.tenant_id,a.document_id)
  JOIN security.accounts u ON u.user_id=a.initiator_user_id AND u.active
  JOIN security.tenants t ON t.tenant_id=a.tenant_id AND t.active
  JOIN security.memberships m ON (m.tenant_id,m.user_id)=(a.tenant_id,a.initiator_user_id) AND m.active
  WHERE (a.tenant_id,a.job_id,a.document_id,a.version_id)=(p_tenant,job,p_document,p_version)
   AND (p_index IS NULL OR a.index_id=p_index) AND a.action='internal_index' AND j.job_kind='internal_index'
   AND a.revoked_at IS NULL AND a.expires_at>statement_timestamp() AND a.lease_hash=claim AND a.lease_epoch=epoch
   AND j.state='running' AND j.lease_epoch=epoch AND j.lease_expires_at>statement_timestamp()
   AND d.deleted_at IS NULL AND NOT v.payload_purged AND NOT i.payload_purged AND i.state IN ('staging','building')
   AND (m.role='TADMIN' OR EXISTS(SELECT 1 FROM security.platform_access pa JOIN security.managed_tenants mt ON mt.user_id=pa.user_id
     WHERE pa.user_id=u.user_id AND pa.active AND pa.is_padmin AND mt.tenant_id=a.tenant_id AND mt.active)));
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
END;$body$;

CREATE FUNCTION security.document_control_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $body$
DECLARE tenant uuid; doc uuid; visibility text;
BEGIN
 IF TG_TABLE_NAME='document_access' THEN
  IF TG_OP='UPDATE' AND (OLD.tenant_id,OLD.document_id,OLD.owner_user_id,OLD.visibility,OLD.created_at)
     IS DISTINCT FROM (NEW.tenant_id,NEW.document_id,NEW.owner_user_id,NEW.visibility,NEW.created_at) THEN
   RAISE EXCEPTION 'DOCUMENT_ACL_IMMUTABLE' USING ERRCODE='23514'; END IF;
  RETURN NEW;
 END IF;
 IF TG_TABLE_NAME='private_readers' THEN
  tenant:=coalesce(NEW.tenant_id,OLD.tenant_id); doc:=coalesce(NEW.document_id,OLD.document_id);
  SELECT a.visibility INTO visibility FROM security.document_access a WHERE (a.tenant_id,a.document_id)=(tenant,doc);
  IF visibility IS DISTINCT FROM 'private' OR EXISTS(SELECT 1 FROM rag.document_versions v WHERE (v.tenant_id,v.document_id)=(tenant,doc)) THEN
   RAISE EXCEPTION 'PRIVATE_READERS_FROZEN' USING ERRCODE='23514'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
 END IF;
 IF TG_TABLE_NAME='share_grants' THEN
  IF TG_OP='UPDATE' AND (OLD.grant_id,OLD.owner_tenant_id,OLD.document_id,OLD.version_id,OLD.recipient_tenant_id,OLD.issued_by,OLD.issued_at) IS DISTINCT FROM (NEW.grant_id,NEW.owner_tenant_id,NEW.document_id,NEW.version_id,NEW.recipient_tenant_id,NEW.issued_by,NEW.issued_at) THEN RAISE EXCEPTION 'SHARE_IDENTITY_IMMUTABLE' USING ERRCODE='23514'; END IF;
  IF NOT EXISTS(SELECT 1 FROM security.document_access a JOIN security.document_publications p
    ON (p.tenant_id,p.document_id)=(a.tenant_id,a.document_id)
    WHERE (a.tenant_id,a.document_id,p.version_id)=(NEW.owner_tenant_id,NEW.document_id,NEW.version_id)
     AND a.visibility='org' AND (NOT NEW.active OR (a.deleted_at IS NULL AND p.active))) THEN
   RAISE EXCEPTION 'SHARE_TARGET_UNAVAILABLE' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='document_publications' THEN
  IF TG_OP='UPDATE' AND (OLD.tenant_id,OLD.document_id,OLD.version_id) IS DISTINCT FROM (NEW.tenant_id,NEW.document_id,NEW.version_id) THEN RAISE EXCEPTION 'PUBLICATION_IDENTITY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='document_publications' AND NEW.active THEN
  IF NOT EXISTS(SELECT 1 FROM rag.index_builds i JOIN rag.document_versions v
    ON (v.tenant_id,v.document_id,v.version_id)=(i.tenant_id,i.document_id,i.version_id)
    WHERE (i.tenant_id,i.document_id,i.version_id,i.index_id)=(NEW.tenant_id,NEW.document_id,NEW.version_id,NEW.published_index_id)
     AND i.state='published' AND NOT i.payload_purged AND NOT v.payload_purged) THEN
   RAISE EXCEPTION 'PUBLICATION_TARGET_UNAVAILABLE' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END;$body$;

ALTER FUNCTION security.document_can_read(uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.document_job_authorized(uuid,uuid,uuid,uuid) OWNER TO ai_policy_executor;
ALTER FUNCTION security.document_control_guard() OWNER TO ai_policy_executor;
REVOKE ALL ON FUNCTION security.document_can_read(uuid,uuid,uuid,uuid),security.document_job_authorized(uuid,uuid,uuid,uuid),security.document_control_guard() FROM PUBLIC,ai_web,ai_index,ai_meter;
GRANT EXECUTE ON FUNCTION security.document_can_read(uuid,uuid,uuid,uuid) TO ai_web;
GRANT EXECUTE ON FUNCTION security.document_job_authorized(uuid,uuid,uuid,uuid) TO ai_index;
CREATE TRIGGER access_identity BEFORE UPDATE ON security.document_access FOR EACH ROW EXECUTE FUNCTION security.document_control_guard();
CREATE TRIGGER private_readers_frozen BEFORE INSERT OR UPDATE OR DELETE ON security.private_readers FOR EACH ROW EXECUTE FUNCTION security.document_control_guard();
CREATE TRIGGER share_org_only BEFORE INSERT OR UPDATE ON security.share_grants FOR EACH ROW EXECUTE FUNCTION security.document_control_guard();
CREATE TRIGGER publication_ready BEFORE INSERT OR UPDATE ON security.document_publications FOR EACH ROW EXECUTE FUNCTION security.document_control_guard();
CREATE POLICY document_versions_control_metadata ON rag.document_versions FOR SELECT TO ai_policy_executor USING(true);
CREATE POLICY index_builds_control_metadata ON rag.index_builds FOR SELECT TO ai_policy_executor USING(true);
CREATE POLICY jobs_control_metadata ON rag.jobs FOR SELECT TO ai_policy_executor USING(true);
CREATE POLICY document_versions_current_reader ON rag.document_versions FOR SELECT TO ai_web USING(NOT payload_purged AND security.document_can_read(tenant_id,document_id,version_id,NULL));
CREATE POLICY document_versions_job_reader ON rag.document_versions FOR SELECT TO ai_index USING(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,NULL));
GRANT SELECT(tenant_id,document_id,version_id,version_no,title,source_object_key,source_sha256,media_type,byte_length,character_length,parser_revision,source_mapping,payload_purged,created_at) ON rag.document_versions TO ai_web;
GRANT SELECT ON rag.document_versions TO ai_index;
CREATE POLICY index_builds_current_reader ON rag.index_builds FOR SELECT TO ai_web USING(NOT payload_purged AND security.document_can_read(tenant_id,document_id,version_id,index_id));
CREATE POLICY index_builds_job_reader ON rag.index_builds FOR SELECT TO ai_index USING(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
GRANT SELECT ON rag.index_builds TO ai_web,ai_index;
CREATE POLICY chunks_current_reader ON rag.chunks FOR SELECT TO ai_web USING(NOT payload_purged AND security.document_can_read(tenant_id,document_id,version_id,index_id));
CREATE POLICY chunks_job_reader ON rag.chunks FOR SELECT TO ai_index USING(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
CREATE POLICY chunks_job_insert ON rag.chunks FOR INSERT TO ai_index WITH CHECK(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
GRANT INSERT ON rag.chunks TO ai_index;
GRANT SELECT ON rag.chunks TO ai_web,ai_index;
CREATE POLICY entities_current_reader ON rag.entities FOR SELECT TO ai_web USING(NOT payload_purged AND security.document_can_read(tenant_id,document_id,version_id,index_id));
CREATE POLICY entities_job_reader ON rag.entities FOR SELECT TO ai_index USING(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
CREATE POLICY entities_job_insert ON rag.entities FOR INSERT TO ai_index WITH CHECK(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
GRANT INSERT ON rag.entities TO ai_index;
GRANT SELECT ON rag.entities TO ai_web,ai_index;
CREATE POLICY relations_current_reader ON rag.relations FOR SELECT TO ai_web USING(NOT payload_purged AND security.document_can_read(tenant_id,document_id,version_id,index_id));
CREATE POLICY relations_job_reader ON rag.relations FOR SELECT TO ai_index USING(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
CREATE POLICY relations_job_insert ON rag.relations FOR INSERT TO ai_index WITH CHECK(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
GRANT INSERT ON rag.relations TO ai_index;
GRANT SELECT ON rag.relations TO ai_web,ai_index;
CREATE POLICY evidence_current_reader ON rag.evidence FOR SELECT TO ai_web USING(NOT payload_purged AND security.document_can_read(tenant_id,document_id,version_id,index_id));
CREATE POLICY evidence_job_reader ON rag.evidence FOR SELECT TO ai_index USING(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
CREATE POLICY evidence_job_insert ON rag.evidence FOR INSERT TO ai_index WITH CHECK(NOT payload_purged AND security.document_job_authorized(tenant_id,document_id,version_id,index_id));
GRANT INSERT ON rag.evidence TO ai_index;
GRANT SELECT ON rag.evidence TO ai_web,ai_index;

CREATE POLICY relation_evidence_current_reader ON rag.relation_evidence FOR SELECT TO ai_web USING(
 EXISTS(SELECT 1 FROM rag.relations r WHERE (r.tenant_id,r.index_id,r.relation_id)=(relation_evidence.tenant_id,relation_evidence.index_id,relation_evidence.relation_id)) AND
 EXISTS(SELECT 1 FROM rag.evidence e WHERE (e.tenant_id,e.index_id,e.evidence_id)=(relation_evidence.tenant_id,relation_evidence.index_id,relation_evidence.evidence_id)));
CREATE POLICY relation_evidence_job_reader ON rag.relation_evidence FOR SELECT TO ai_index USING(
 EXISTS(SELECT 1 FROM rag.relations r WHERE (r.tenant_id,r.index_id,r.relation_id)=(relation_evidence.tenant_id,relation_evidence.index_id,relation_evidence.relation_id)) AND
 EXISTS(SELECT 1 FROM rag.evidence e WHERE (e.tenant_id,e.index_id,e.evidence_id)=(relation_evidence.tenant_id,relation_evidence.index_id,relation_evidence.evidence_id)));
CREATE POLICY relation_evidence_job_insert ON rag.relation_evidence FOR INSERT TO ai_index WITH CHECK(
 EXISTS(SELECT 1 FROM rag.relations r WHERE (r.tenant_id,r.index_id,r.relation_id)=(relation_evidence.tenant_id,relation_evidence.index_id,relation_evidence.relation_id)) AND
 EXISTS(SELECT 1 FROM rag.evidence e WHERE (e.tenant_id,e.index_id,e.evidence_id)=(relation_evidence.tenant_id,relation_evidence.index_id,relation_evidence.evidence_id)));
GRANT SELECT ON rag.relation_evidence TO ai_web,ai_index;
GRANT INSERT ON rag.relation_evidence TO ai_index;
CREATE POLICY answer_evidence_current_reader ON portal.answer_evidence FOR SELECT TO ai_web USING(NOT payload_purged AND
 EXISTS(SELECT 1 FROM portal.runs r WHERE (r.tenant_id,r.run_id)=(answer_evidence.tenant_id,answer_evidence.run_id) AND security.can_read_own_conversation(r.tenant_id,r.owner_user_id))
 AND security.document_can_read(source_tenant_id,document_id,version_id,index_id));
GRANT SELECT ON portal.answer_evidence TO ai_web;
-- No answer provenance writes or embedding ledger changes until C03/C04.
