CREATE SCHEMA raw;
CREATE SCHEMA core;

CREATE TABLE raw.ingestion_batch (
    id uuid PRIMARY KEY,
    source_name text NOT NULL,
    source_root text NOT NULL,
    manifest_hash text NOT NULL CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    manifest_payload jsonb NOT NULL,
    parser_version text NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (manifest_hash, parser_version)
);
CREATE TABLE raw.ingestion_event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id uuid NOT NULL REFERENCES raw.ingestion_batch(id),
    status text NOT NULL CHECK (status IN ('started','resumed','completed','failed')),
    detail jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ingestion_event_batch ON raw.ingestion_event(batch_id,id DESC);

CREATE TABLE raw.object (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    storage_uri text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    media_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE raw.capture (
    id uuid PRIMARY KEY,
    batch_id uuid NOT NULL REFERENCES raw.ingestion_batch(id),
    object_sha text NOT NULL REFERENCES raw.object(sha256),
    original_path text NOT NULL,
    source_endpoint text,
    fetched_at timestamptz,
    observed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (batch_id,original_path)
);
CREATE TABLE raw.record (
    id uuid PRIMARY KEY,
    capture_id uuid NOT NULL REFERENCES raw.capture(id),
    locator text NOT NULL,
    parsed_payload jsonb,
    parse_status text NOT NULL CHECK (parse_status IN ('parsed','invalid','opaque')),
    UNIQUE (capture_id,locator),
    CHECK ((parse_status='parsed') = (parsed_payload IS NOT NULL))
);
CREATE TABLE raw.quality_issue (
    id uuid PRIMARY KEY,
    record_id uuid NOT NULL REFERENCES raw.record(id),
    code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info','warning','error')),
    field_path text NOT NULL,
    detail jsonb NOT NULL,
    UNIQUE(record_id,code,field_path)
);
CREATE INDEX quality_issue_code ON raw.quality_issue(code,severity);
CREATE INDEX quality_issue_record ON raw.quality_issue(record_id);
CREATE TABLE core.company (
    company_id uuid PRIMARY KEY,
    krs text NOT NULL UNIQUE CHECK (krs ~ '^[0-9]{10}$'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE core.company_snapshot (
    id uuid PRIMARY KEY,
    company_id uuid NOT NULL REFERENCES core.company(company_id),
    raw_record_id uuid NOT NULL REFERENCES raw.record(id),
    source_kind text NOT NULL,
    name text,
    legal_form text,
    website text,
    provider_entity_id text,
    observed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(company_id,raw_record_id)
);
CREATE INDEX company_snapshot_company ON core.company_snapshot(company_id);

CREATE FUNCTION raw.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only table: %', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
        USING ERRCODE='55000';
END;
$$;
DO $$
DECLARE t record;
BEGIN
    FOR t IN SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('raw','core') LOOP
        EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON %I.%I FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation()',t.schemaname,t.tablename);
        EXECUTE format('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON %I.%I FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation()',t.schemaname,t.tablename);
    END LOOP;
END;
$$;
REVOKE ALL ON SCHEMA raw,core FROM PUBLIC;
