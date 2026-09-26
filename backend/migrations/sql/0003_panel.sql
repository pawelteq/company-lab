CREATE SCHEMA analytics;
CREATE TABLE analytics.dataset (
    id uuid PRIMARY KEY,
    batch_id uuid NOT NULL REFERENCES raw.ingestion_batch(id),
    version_hash text NOT NULL UNIQUE,
    code_hash text NOT NULL,
    config jsonb NOT NULL,
    maturity text NOT NULL CHECK (maturity='exploratory_reported'),
    research_ready boolean NOT NULL DEFAULT false CHECK (research_ready=false),
    artifact_manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE analytics.feature_definition (
    dataset_id uuid NOT NULL REFERENCES analytics.dataset(id),
    name text NOT NULL,
    definition jsonb NOT NULL,
    PRIMARY KEY(dataset_id,name)
);
CREATE TABLE analytics.selection_candidate (
    dataset_id uuid NOT NULL REFERENCES analytics.dataset(id),
    company_id uuid NOT NULL REFERENCES core.company(company_id),
    year smallint NOT NULL,
    financial_record_id uuid NOT NULL REFERENCES staging.financial_record(id),
    PRIMARY KEY(dataset_id,company_id,year,financial_record_id)
);
CREATE TABLE analytics.company_year (
    dataset_id uuid NOT NULL REFERENCES analytics.dataset(id),
    company_id uuid NOT NULL REFERENCES core.company(company_id),
    year smallint NOT NULL,
    selected_record_id uuid,
    selection_status text NOT NULL CHECK (selection_status IN ('selected_unique','unresolved_multiple','unavailable_standalone')),
    n_years smallint NOT NULL,
    n_selected_years smallint NOT NULL,
    n_annual_years smallint NOT NULL,
    panel_full boolean NOT NULL CHECK (panel_full=true),
    panel_3plus boolean NOT NULL,
    panel_5plus boolean NOT NULL,
    panel_long boolean NOT NULL,
    features jsonb NOT NULL,
    missing_reasons jsonb NOT NULL,
    quality_codes text[] NOT NULL,
    PRIMARY KEY(dataset_id,company_id,year),
    FOREIGN KEY(dataset_id,company_id,year,selected_record_id)
        REFERENCES analytics.selection_candidate(dataset_id,company_id,year,financial_record_id),
    CHECK ((selection_status='selected_unique')=(selected_record_id IS NOT NULL)),
    CHECK (panel_3plus=(n_years>=3) AND panel_5plus=(n_years>=5) AND panel_long=(n_years>=7))
);
CREATE INDEX panel_year ON analytics.company_year(dataset_id,year);
CREATE INDEX candidate_record ON analytics.selection_candidate(financial_record_id);
DO $$
DECLARE t record;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='analytics' LOOP
        EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON analytics.%I FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation()',t.tablename);
        EXECUTE format('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON analytics.%I FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation()',t.tablename);
    END LOOP;
END;
$$;
REVOKE ALL ON SCHEMA analytics FROM PUBLIC;
