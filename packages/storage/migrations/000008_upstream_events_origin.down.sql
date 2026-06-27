DROP INDEX IF EXISTS upstream_events_origin_lookup_idx;

ALTER TABLE upstream_events
    DROP COLUMN IF EXISTS upstream_platform,
    DROP COLUMN IF EXISTS upstream_region,
    DROP COLUMN IF EXISTS upstream_origin;
