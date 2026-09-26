-- Keep catalogue search responsive as the profile collection grows.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS profile_screening_name_trgm
    ON core.profile_screening USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS profile_screening_city_trgm
    ON core.profile_screening USING gin (city gin_trgm_ops);
CREATE INDEX IF NOT EXISTS profile_screening_collection_status_name
    ON core.profile_screening(collection_id, status, lower(name));
