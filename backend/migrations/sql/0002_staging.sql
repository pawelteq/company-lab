CREATE SCHEMA staging;
CREATE TABLE staging.financial_record (
    id uuid PRIMARY KEY,
    company_id uuid NOT NULL REFERENCES core.company(company_id),
    raw_record_id uuid NOT NULL REFERENCES raw.record(id),
    source_pointer text NOT NULL,
    provider_metric_id text,
    provider_document_id text,
    provider_entity_id text,
    period_start date,
    period_end date,
    fiscal_year smallint,
    duration_days integer,
    period_resolution_method text NOT NULL,
    consolidation_scope text NOT NULL CHECK (consolidation_scope IN ('standalone','consolidated','unknown')),
    currency text,
    reported_unit_scale numeric,
    extracted_at timestamptz,
    reported_metrics jsonb NOT NULL,
    statement_profile jsonb NOT NULL,
    quality_codes text[] NOT NULL,
    UNIQUE (raw_record_id,source_pointer),
    CHECK (period_start IS NULL OR period_end IS NULL OR period_end>=period_start)
);
CREATE INDEX financial_company_year ON staging.financial_record(company_id,fiscal_year,consolidation_scope);
CREATE INDEX financial_record_source ON staging.financial_record(raw_record_id);
CREATE INDEX financial_provider_id ON staging.financial_record(provider_metric_id);
CREATE TABLE staging.relationship_snapshot (
    id uuid PRIMARY KEY,
    company_id uuid NOT NULL REFERENCES core.company(company_id),
    raw_record_id uuid NOT NULL UNIQUE REFERENCES raw.record(id),
    people_count integer NOT NULL,
    related_company_count integer NOT NULL,
    graph_node_count integer NOT NULL,
    graph_edge_count integer NOT NULL,
    historical_validity_known boolean NOT NULL DEFAULT false CHECK (historical_validity_known=false)
);
CREATE INDEX relationship_snapshot_company ON staging.relationship_snapshot(company_id);
DO $$
DECLARE t record;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='staging' LOOP
        EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON staging.%I FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation()',t.tablename);
        EXECUTE format('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON staging.%I FOR EACH STATEMENT EXECUTE FUNCTION raw.reject_mutation()',t.tablename);
    END LOOP;
END;
$$;
REVOKE ALL ON SCHEMA staging FROM PUBLIC;

CREATE VIEW staging.company_year_conflicts AS
SELECT c.batch_id,f.company_id,co.krs,f.fiscal_year,
       count(*) AS candidate_count,
       count(DISTINCT f.consolidation_scope) AS scope_count,
       array_agg(f.id ORDER BY f.id) AS candidates
FROM staging.financial_record f
JOIN core.company co USING(company_id)
JOIN raw.record r ON r.id=f.raw_record_id
JOIN raw.capture c ON c.id=r.capture_id
WHERE f.fiscal_year IS NOT NULL
GROUP BY c.batch_id,f.company_id,co.krs,f.fiscal_year
HAVING count(*)>1;
