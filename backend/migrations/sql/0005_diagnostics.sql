CREATE TABLE research.diagnostic_run (
    id uuid PRIMARY KEY,
    research_run_id uuid NOT NULL REFERENCES research.run(id),
    version_hash text NOT NULL UNIQUE,
    code_hash text NOT NULL,
    protocol jsonb NOT NULL,
    results jsonb NOT NULL,
    artifact_manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX diagnostic_run_parent ON research.diagnostic_run(research_run_id,created_at DESC);
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON research.diagnostic_run FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON research.diagnostic_run FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
