ALTER TABLE upstream_events
    ADD COLUMN upstream_platform text NOT NULL DEFAULT '',
    ADD COLUMN upstream_region text NOT NULL DEFAULT '',
    ADD COLUMN upstream_origin text NOT NULL DEFAULT '';

CREATE INDEX upstream_events_origin_lookup_idx
    ON upstream_events (upstream_bucket_name, upstream_origin);
