-- C01 storage foundation. No RAG agent, upload route or provider dispatch is enabled.
CREATE SCHEMA rag AUTHORIZATION ai_owner;
REVOKE ALL ON SCHEMA rag FROM PUBLIC;
CREATE EXTENSION vector WITH SCHEMA rag VERSION '0.8.6';

CREATE TABLE security.document_access (
 tenant_id uuid NOT NULL REFERENCES security.tenants, document_id uuid NOT NULL,
 owner_user_id uuid NOT NULL, visibility text NOT NULL CHECK(visibility IN ('private','org')),
 acl_revision bigint NOT NULL DEFAULT 1 CHECK(acl_revision>0), deleted_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,document_id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES security.memberships(tenant_id,user_id)
);
CREATE TABLE security.private_readers (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, user_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,document_id,user_id),
 FOREIGN KEY(tenant_id,document_id) REFERENCES security.document_access,
 FOREIGN KEY(tenant_id,user_id) REFERENCES security.memberships
);
CREATE TABLE rag.document_versions (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL,
 version_no integer NOT NULL CHECK(version_no>0), title text,
 source_object_key text, source_sha256 bytea NOT NULL CHECK(octet_length(source_sha256)=32),
 media_type text NOT NULL CHECK(media_type IN ('text/plain','text/markdown')),
 byte_length integer NOT NULL CHECK(byte_length BETWEEN 1 AND 131072),
 character_length integer NOT NULL CHECK(character_length BETWEEN 1 AND 40000),
 ingest_hmac bytea NOT NULL CHECK(octet_length(ingest_hmac)=32), parser_revision text NOT NULL CHECK(parser_revision ~ '^[a-zA-Z0-9._-]{1,64}$'),
 source_mapping jsonb, payload_purged boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,document_id,version_id), UNIQUE(tenant_id,document_id,version_no),
 FOREIGN KEY(tenant_id,document_id) REFERENCES security.document_access,
 CHECK((payload_purged AND title IS NULL AND source_object_key IS NULL AND source_mapping IS NULL) OR
  (NOT payload_purged AND title IS NOT NULL AND source_object_key IS NOT NULL AND char_length(title) BETWEEN 1 AND 200 AND btrim(title)<>'' AND source_mapping IS NOT NULL AND jsonb_typeof(source_mapping)='object' AND
   source_object_key='tenants/'||tenant_id::text||'/documents/'||document_id::text||'/'||version_id::text||'/source'))
);
CREATE TABLE rag.index_builds (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL,
 execution_mode text NOT NULL CHECK(execution_mode IN ('mock','real')), pipeline_revision text NOT NULL CHECK(pipeline_revision ~ '^[a-zA-Z0-9._-]{1,64}$'),
 source_fingerprint bytea NOT NULL CHECK(octet_length(source_fingerprint)=32),
 embedding_model text NOT NULL DEFAULT 'text-embedding-3-small' CHECK(embedding_model='text-embedding-3-small'),
 embedding_dimensions integer NOT NULL DEFAULT 1536 CHECK(embedding_dimensions=1536), schema_revision integer NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 state text NOT NULL DEFAULT 'staging' CHECK(state IN ('staging','building','validated','published','failed','interrupted')),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), expected_batches integer NOT NULL DEFAULT 0 CHECK(expected_batches BETWEEN 0 AND 16),
 completed_batches integer NOT NULL DEFAULT 0 CHECK(completed_batches BETWEEN 0 AND expected_batches),
 checkpoint_summary jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(checkpoint_summary)='object'),
 coverage jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(coverage)='object'), payload_purged boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,index_id), UNIQUE(tenant_id,document_id,version_id,index_id),
 UNIQUE(tenant_id,document_id,version_id,pipeline_revision,execution_mode),
 FOREIGN KEY(tenant_id,document_id,version_id) REFERENCES rag.document_versions
);
CREATE TABLE rag.jobs (
 tenant_id uuid NOT NULL, job_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL,
 initiator_user_id uuid NOT NULL, job_kind text NOT NULL CHECK(job_kind IN ('internal_index','internal_cleanup')),
 execution_mode text NOT NULL CHECK(execution_mode IN ('mock','real')),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','completed','failed','blocked','interrupted','needs_review')),
 stage text NOT NULL DEFAULT 'validate_source' CHECK(stage IN ('validate_source','parse_plan','embed_batches','validate_index','publish','cleanup','terminal')),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), retry_of uuid, attempt integer NOT NULL DEFAULT 1 CHECK(attempt>0),
 safe_error_code text CHECK(safe_error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'), heartbeat_at timestamptz,
 lease_epoch bigint NOT NULL DEFAULT 1 CHECK(lease_epoch>0), lease_expires_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), ended_at timestamptz,
 PRIMARY KEY(tenant_id,job_id), UNIQUE(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind),
 FOREIGN KEY(tenant_id,document_id,version_id,index_id) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id),
 FOREIGN KEY(tenant_id,initiator_user_id) REFERENCES security.memberships,
 FOREIGN KEY(tenant_id,retry_of) REFERENCES rag.jobs(tenant_id,job_id),
 CHECK((state IN ('completed','failed','blocked','interrupted','needs_review'))=(ended_at IS NOT NULL)),
 CHECK((stage='terminal')=(ended_at IS NOT NULL)), CHECK(lease_expires_at IS NULL OR heartbeat_at IS NOT NULL)
);
CREATE UNIQUE INDEX jobs_one_active_index ON rag.jobs(tenant_id,index_id) WHERE state IN ('queued','running');
CREATE TABLE security.document_publications (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, published_index_id uuid,
 active boolean NOT NULL DEFAULT false, revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 PRIMARY KEY(tenant_id,document_id,version_id),
 FOREIGN KEY(tenant_id,document_id,version_id) REFERENCES rag.document_versions,
 FOREIGN KEY(tenant_id,document_id,version_id,published_index_id) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id),
 CHECK(NOT active OR published_index_id IS NOT NULL)
);
CREATE TABLE security.share_grants (
 grant_id uuid PRIMARY KEY, owner_tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL,
 recipient_tenant_id uuid NOT NULL REFERENCES security.tenants, active boolean NOT NULL DEFAULT true,
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), issued_by uuid NOT NULL,
 issued_at timestamptz NOT NULL DEFAULT clock_timestamp(), revoked_at timestamptz,
 FOREIGN KEY(owner_tenant_id,document_id,version_id) REFERENCES security.document_publications,
 FOREIGN KEY(owner_tenant_id,issued_by) REFERENCES security.memberships,
 CHECK(owner_tenant_id<>recipient_tenant_id), CHECK(NOT active OR revoked_at IS NULL)
);
CREATE UNIQUE INDEX share_grants_one_active ON security.share_grants(owner_tenant_id,document_id,version_id,recipient_tenant_id) WHERE active;
CREATE TABLE security.job_authorizations (
 tenant_id uuid NOT NULL, job_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL,
 initiator_user_id uuid NOT NULL, action text NOT NULL CHECK(action IN ('internal_index','internal_cleanup')),
 deletion_revision bigint CHECK(deletion_revision>0), lease_hash bytea NOT NULL CHECK(octet_length(lease_hash)=32),
 lease_epoch bigint NOT NULL CHECK(lease_epoch>0), expires_at timestamptz NOT NULL, revoked_at timestamptz,
 PRIMARY KEY(tenant_id,job_id),
 FOREIGN KEY(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,action)
  REFERENCES rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id,job_kind),
 CHECK((action='internal_cleanup')=(deletion_revision IS NOT NULL))
);
ALTER TABLE rag.jobs ADD CONSTRAINT jobs_receipt_binding UNIQUE(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id);
CREATE TABLE security.operation_receipts (
 tenant_id uuid NOT NULL, initiator_user_id uuid NOT NULL, operation_kind text NOT NULL CHECK(operation_kind IN ('upload','retry')),
 client_operation_id uuid NOT NULL, request_hash bytea NOT NULL CHECK(octet_length(request_hash)=32),
 document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL, job_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,initiator_user_id,operation_kind,client_operation_id),
 FOREIGN KEY(tenant_id,initiator_user_id) REFERENCES security.memberships,
 FOREIGN KEY(tenant_id,document_id,version_id,index_id) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id),
 FOREIGN KEY(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id) REFERENCES rag.jobs(tenant_id,job_id,document_id,version_id,index_id,initiator_user_id)
);
ALTER TABLE rag.document_versions ADD CONSTRAINT version_hash_binding UNIQUE(tenant_id,document_id,version_id,source_sha256);
CREATE TABLE rag.chunks (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL, chunk_id uuid NOT NULL,
 ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 127), text text, location jsonb,
 embedding rag.vector(1536), source_sha256 bytea NOT NULL CHECK(octet_length(source_sha256)=32),
 batch_ordinal integer NOT NULL CHECK(batch_ordinal BETWEEN 0 AND 15), call_id uuid,
 payload_purged boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,index_id,chunk_id), UNIQUE(tenant_id,index_id,ordinal),
 UNIQUE(tenant_id,document_id,version_id,index_id,chunk_id),
 FOREIGN KEY(tenant_id,document_id,version_id,index_id) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id),
 FOREIGN KEY(tenant_id,document_id,version_id,source_sha256) REFERENCES rag.document_versions(tenant_id,document_id,version_id,source_sha256),
 FOREIGN KEY(tenant_id,call_id) REFERENCES ops.call_attempts,
 CHECK((payload_purged AND text IS NULL AND location IS NULL AND embedding IS NULL) OR
       (NOT payload_purged AND text IS NOT NULL AND btrim(text)<>'' AND location IS NOT NULL AND jsonb_typeof(location)='object' AND embedding IS NOT NULL))
);
CREATE TABLE rag.entities (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL, entity_id uuid NOT NULL,
 semantic_key text NOT NULL CHECK(char_length(semantic_key) BETWEEN 1 AND 200),
 entity_type text NOT NULL CHECK(entity_type IN ('PROCESS','TEAM','ARTIFACT','DURATION','SCHEDULE','PERSON')),
 label text, properties jsonb, payload_purged boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,index_id,entity_id), UNIQUE(tenant_id,index_id,semantic_key),
 FOREIGN KEY(tenant_id,document_id,version_id,index_id) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id),
 CHECK((payload_purged AND label IS NULL AND properties IS NULL) OR
       (NOT payload_purged AND label IS NOT NULL AND char_length(label) BETWEEN 1 AND 200 AND properties IS NOT NULL AND jsonb_typeof(properties)='object'))
);
CREATE TABLE rag.relations (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL, relation_id uuid NOT NULL,
 from_entity_id uuid NOT NULL, to_entity_id uuid NOT NULL, relation_type text NOT NULL CHECK(char_length(relation_type) BETWEEN 1 AND 64),
 properties jsonb, payload_purged boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,index_id,relation_id),
 FOREIGN KEY(tenant_id,document_id,version_id,index_id) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id),
 FOREIGN KEY(tenant_id,index_id,from_entity_id) REFERENCES rag.entities,
 FOREIGN KEY(tenant_id,index_id,to_entity_id) REFERENCES rag.entities,
 CHECK((payload_purged AND properties IS NULL) OR (NOT payload_purged AND properties IS NOT NULL AND jsonb_typeof(properties)='object'))
);
CREATE TABLE rag.evidence (
 tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL, evidence_id uuid NOT NULL, chunk_id uuid NOT NULL,
 start_offset integer NOT NULL CHECK(start_offset>=0), end_offset integer NOT NULL CHECK(end_offset>start_offset),
 line_start integer NOT NULL CHECK(line_start>0), line_end integer NOT NULL CHECK(line_end>=line_start),
 exact_quote text, source_sha256 bytea NOT NULL CHECK(octet_length(source_sha256)=32), payload_purged boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,index_id,evidence_id), UNIQUE(tenant_id,document_id,version_id,index_id,evidence_id),
 FOREIGN KEY(tenant_id,document_id,version_id,index_id,chunk_id) REFERENCES rag.chunks(tenant_id,document_id,version_id,index_id,chunk_id),
 FOREIGN KEY(tenant_id,document_id,version_id,source_sha256) REFERENCES rag.document_versions(tenant_id,document_id,version_id,source_sha256),
 CHECK((payload_purged AND exact_quote IS NULL) OR (NOT payload_purged AND exact_quote IS NOT NULL AND char_length(exact_quote)=end_offset-start_offset))
);
CREATE TABLE rag.relation_evidence (
 tenant_id uuid NOT NULL, index_id uuid NOT NULL, relation_id uuid NOT NULL, evidence_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,index_id,relation_id,evidence_id),
 FOREIGN KEY(tenant_id,index_id,relation_id) REFERENCES rag.relations,
 FOREIGN KEY(tenant_id,index_id,evidence_id) REFERENCES rag.evidence
);
CREATE TABLE portal.answer_evidence (
 tenant_id uuid NOT NULL, run_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 1023),
 source_tenant_id uuid NOT NULL, document_id uuid NOT NULL, version_id uuid NOT NULL, index_id uuid NOT NULL, evidence_id uuid NOT NULL,
 source_sha256 bytea NOT NULL CHECK(octet_length(source_sha256)=32), location_snapshot jsonb, quote_snapshot text, payload_purged boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,run_id,ordinal), FOREIGN KEY(tenant_id,run_id) REFERENCES portal.runs,
 FOREIGN KEY(source_tenant_id,document_id,version_id,index_id,evidence_id) REFERENCES rag.evidence(tenant_id,document_id,version_id,index_id,evidence_id),
 FOREIGN KEY(source_tenant_id,document_id,version_id,source_sha256) REFERENCES rag.document_versions(tenant_id,document_id,version_id,source_sha256),
 CHECK((payload_purged AND location_snapshot IS NULL AND quote_snapshot IS NULL) OR
       (NOT payload_purged AND location_snapshot IS NOT NULL AND jsonb_typeof(location_snapshot)='object' AND quote_snapshot IS NOT NULL AND btrim(quote_snapshot)<>''))
);
-- UUID identities, source provenance, mode and pipeline are immutable. Purge is a later fixed control operation.
CREATE FUNCTION rag.guard_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $body$
DECLARE fields text[];
BEGIN
 fields := CASE TG_TABLE_NAME
  WHEN 'document_versions' THEN ARRAY['tenant_id','document_id','version_id','version_no','source_sha256','media_type','byte_length','character_length','ingest_hmac','parser_revision','created_at']
  WHEN 'index_builds' THEN ARRAY['tenant_id','document_id','version_id','index_id','execution_mode','pipeline_revision','source_fingerprint','embedding_model','embedding_dimensions','schema_revision','created_at']
  WHEN 'jobs' THEN ARRAY['tenant_id','job_id','document_id','version_id','index_id','initiator_user_id','job_kind','execution_mode','retry_of','attempt','created_at'] END;
 IF EXISTS(SELECT 1 FROM unnest(fields) f WHERE to_jsonb(OLD)->f IS DISTINCT FROM to_jsonb(NEW)->f) THEN
  RAISE EXCEPTION 'DOCUMENT_IDENTITY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='document_versions' AND NOT (to_jsonb(NEW)->>'payload_purged')::boolean AND
  (to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW)) THEN RAISE EXCEPTION 'SOURCE_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF (to_jsonb(OLD)->>'payload_purged')::boolean AND NOT (to_jsonb(NEW)->>'payload_purged')::boolean THEN
  RAISE EXCEPTION 'PAYLOAD_PURGE_IRREVERSIBLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;$body$;
ALTER FUNCTION rag.guard_identity() OWNER TO ai_owner;
REVOKE ALL ON FUNCTION rag.guard_identity() FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
CREATE TRIGGER versions_identity BEFORE UPDATE ON rag.document_versions FOR EACH ROW EXECUTE FUNCTION rag.guard_identity();
CREATE TRIGGER indexes_identity BEFORE UPDATE ON rag.index_builds FOR EACH ROW EXECUTE FUNCTION rag.guard_identity();
CREATE TRIGGER jobs_identity BEFORE UPDATE ON rag.jobs FOR EACH ROW EXECUTE FUNCTION rag.guard_identity();

ALTER TABLE rag.index_builds ADD CONSTRAINT index_mode_binding UNIQUE(tenant_id,document_id,version_id,index_id,execution_mode);
ALTER TABLE rag.jobs ADD CONSTRAINT job_mode_binding FOREIGN KEY(tenant_id,document_id,version_id,index_id,execution_mode) REFERENCES rag.index_builds(tenant_id,document_id,version_id,index_id,execution_mode);
ALTER TABLE security.document_access OWNER TO ai_policy_executor;
REVOKE ALL ON security.document_access FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER TABLE security.private_readers OWNER TO ai_policy_executor;
REVOKE ALL ON security.private_readers FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER TABLE security.document_publications OWNER TO ai_policy_executor;
REVOKE ALL ON security.document_publications FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER TABLE security.share_grants OWNER TO ai_policy_executor;
REVOKE ALL ON security.share_grants FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER TABLE security.job_authorizations OWNER TO ai_policy_executor;
REVOKE ALL ON security.job_authorizations FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER TABLE security.operation_receipts OWNER TO ai_policy_executor;
REVOKE ALL ON security.operation_receipts FROM PUBLIC,ai_web,ai_index,ai_meter;
ALTER TABLE rag.document_versions OWNER TO ai_owner;
ALTER TABLE rag.document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.document_versions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.document_versions FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE rag.index_builds OWNER TO ai_owner;
ALTER TABLE rag.index_builds ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.index_builds FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.index_builds FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE rag.jobs OWNER TO ai_owner;
ALTER TABLE rag.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.jobs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.jobs FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE rag.chunks OWNER TO ai_owner;
ALTER TABLE rag.chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.chunks FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.chunks FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE rag.entities OWNER TO ai_owner;
ALTER TABLE rag.entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.entities FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.entities FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE rag.relations OWNER TO ai_owner;
ALTER TABLE rag.relations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.relations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.relations FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE rag.evidence OWNER TO ai_owner;
ALTER TABLE rag.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.evidence FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.evidence FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE rag.relation_evidence OWNER TO ai_owner;
ALTER TABLE rag.relation_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.relation_evidence FORCE ROW LEVEL SECURITY;
REVOKE ALL ON rag.relation_evidence FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
ALTER TABLE portal.answer_evidence OWNER TO ai_owner;
ALTER TABLE portal.answer_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal.answer_evidence FORCE ROW LEVEL SECURITY;
REVOKE ALL ON portal.answer_evidence FROM PUBLIC,ai_web,ai_index,ai_meter,ai_policy_executor;
