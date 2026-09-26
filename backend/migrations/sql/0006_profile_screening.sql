CREATE TABLE core.profile_collection (
    id uuid PRIMARY KEY,
    fingerprint text NOT NULL UNIQUE,
    rule_version text NOT NULL,
    summary jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE core.profile_screening (
    collection_id uuid NOT NULL REFERENCES core.profile_collection(id),
    krs text NOT NULL CHECK (krs ~ '^[0-9]{10}$'),
    name text,
    city text,
    region text,
    status text NOT NULL CHECK (status IN ('developer_candidate','other_activity','review','missing_summary')),
    profile jsonb NOT NULL,
    PRIMARY KEY (collection_id,krs)
);
CREATE INDEX profile_screening_status ON core.profile_screening(collection_id,status,krs);
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON core.profile_collection FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON core.profile_collection FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON core.profile_screening FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON core.profile_screening FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
