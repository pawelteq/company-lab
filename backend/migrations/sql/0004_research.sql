CREATE SCHEMA research;
CREATE TABLE research.run (
    id uuid PRIMARY KEY,
    dataset_id uuid NOT NULL REFERENCES analytics.dataset(id),
    run_hash text NOT NULL UNIQUE,
    code_hash text NOT NULL,
    specification jsonb NOT NULL,
    results jsonb NOT NULL,
    artifact_manifest jsonb NOT NULL,
    inference_class text NOT NULL CHECK (inference_class='exploratory_conditional_association'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX research_run_dataset ON research.run(dataset_id);
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON research.run FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON research.run FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation();
REVOKE ALL ON SCHEMA research FROM PUBLIC;
